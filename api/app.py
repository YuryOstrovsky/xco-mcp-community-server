# api/app.py

import concurrent.futures
import os
import re
import threading
import time
import uuid as _uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Dict, Any

from mcp_runtime.server import MCPServer
from mcp_runtime.session_store import SessionStore
from mcp_runtime.errors import ToolNotFound
from mcp_runtime.policy import PolicyViolation
from mcp_runtime.payload_normalize import normalize_result
from mcp_runtime.catalog_version import compute_catalog_version
from mcp_runtime.logging import get_logger
from api.docs_routes import router as docs_router

logger = get_logger("mcp.api")

# Security: strip control characters from user-controlled values before logging
# (prevents log-injection / forged log lines).
_CONTROL_CHAR_RE = re.compile(r'[\n\r\t\x00-\x1f\x7f]')


def _safe_log(value, max_len: int = 128) -> str:
    return _CONTROL_CHAR_RE.sub('_', str(value)[:max_len])

# -------------------------------------------------
# App & MCP initialization
# -------------------------------------------------

# MCP JSON-RPC transport (set after `mcp` is created, below) — the lifespan
# runs its streamable-HTTP session manager for the app's lifetime when mounted.
_mcp_transport = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if _mcp_transport is not None:
        async with _mcp_transport.lifespan():
            yield
    else:
        yield


app = FastAPI(title="XCO MCP Server", lifespan=_lifespan)

# Fix #24: CORS — restrictive by default; set CORS_ORIGINS env var to allow
# specific origins (comma-separated), or "*" for any origin.
_cors_origins_raw = os.environ.get("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-MCP-Session"],
)

# -------------------------------------------------
# Security headers + API version on every response
# -------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers and API version to every response."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-API-Version"] = "v1"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# -------------------------------------------------
# Global exception handlers — consistent error envelope + error_id
# -------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    error_id = f"err-{_uuid.uuid4().hex[:8]}"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_id": error_id},
        headers=getattr(exc, "headers", None),  # preserve e.g. Retry-After on 429
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = f"err-{_uuid.uuid4().hex[:8]}"
    logger.exception("unhandled error error_id=%s path=%s", error_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_id": error_id},
    )

# -------------------------------------------------
# Fix #21: Request / response logging middleware
# -------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "http method=%s path=%s status=%s duration_ms=%d",
            request.method,
            _safe_log(request.url.path),
            response.status_code,
            duration_ms,
        )
        return response

app.add_middleware(RequestLoggingMiddleware)

# -------------------------------------------------
# Fix #16: Request body size limit
# -------------------------------------------------
_MAX_BODY_BYTES = int(os.environ.get("MCP_MAX_BODY_SIZE", str(1 * 1024 * 1024)))  # default 1 MB


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            return Response(
                content=f"Request body too large (max {_MAX_BODY_BYTES} bytes)",
                status_code=413,
            )
        return await call_next(request)

app.add_middleware(BodySizeLimitMiddleware)

app.include_router(docs_router)
mcp = MCPServer(auto_mode=False)
session_store = SessionStore()

# -------------------------------------------------
# MCP JSON-RPC transport at /mcp (Streamable HTTP) — JSON-RPC 2.0
# (initialize / tools/list / tools/call) ALONGSIDE POST /invoke, so standard
# MCP clients (Inspector, Claude Desktop) connect with no shim. Routes through
# the same mcp.invoke() path. Auth-free (community). Env-gated (default on);
# its session manager is run by the app lifespan defined above.
# -------------------------------------------------
if os.environ.get("MCP_TRANSPORT_ENABLED", "true").lower() in (
        "1", "true", "yes", "on"):
    try:
        from api.mcp_transport import MCPTransport
        _mcp_transport = MCPTransport(mcp)
        app.mount("/mcp", app=_mcp_transport.handle_asgi)
        logger.info("MCP transport mounted at /mcp")
    except Exception:
        logger.exception("MCP transport failed to initialise; /mcp disabled")
        _mcp_transport = None

# -------------------------------------------------
# Fix #13: In-memory rate limiter (sliding window per IP)
# -------------------------------------------------
_RATE_LIMIT_RPM = int(os.environ.get("MCP_RATE_LIMIT_RPM", "60"))  # requests/minute/IP
_rate_store: dict[str, deque] = {}
_rate_lock = threading.Lock()
_RATE_GC_INTERVAL = 300.0  # garbage-collect stale keys every 5 min
_rate_last_gc = 0.0


def _is_rate_limited(ip: str) -> bool:
    global _rate_last_gc
    now = time.monotonic()
    window = 60.0
    with _rate_lock:
        # Periodic GC of stale keys so _rate_store doesn't grow unbounded with
        # one entry per ever-seen IP.
        if now - _rate_last_gc > _RATE_GC_INTERVAL:
            expired = [k for k, dq in _rate_store.items()
                       if not dq or now - dq[-1] > window]
            for k in expired:
                del _rate_store[k]
            _rate_last_gc = now

        if ip not in _rate_store:
            _rate_store[ip] = deque()
        q = _rate_store[ip]
        # evict timestamps outside the sliding window
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= _RATE_LIMIT_RPM:
            try:
                from mcp_runtime.metrics import MCP_RATE_LIMIT_HITS
                MCP_RATE_LIMIT_HITS.labels(type="ip").inc()
            except Exception:
                pass
            return True
        q.append(now)
        return False


# -------------------------------------------------
# Models
# -------------------------------------------------

class InvokeRequest(BaseModel):
    tool: str
    inputs: Dict[str, Any] = {}
    context: Optional[Dict[str, Any]] = None


# -------------------------------------------------
# Catalog version (process-cached) — additive X-Catalog-Version header
# -------------------------------------------------

_catalog_version_cache: Optional[str] = None


def _catalog_version() -> str:
    """Stable short fingerprint of the served catalog, computed once per
    process. Lets clients short-circuit re-discovery when unchanged."""
    global _catalog_version_cache
    if _catalog_version_cache is None:
        _catalog_version_cache = compute_catalog_version(mcp.list_tools())
    return _catalog_version_cache


# -------------------------------------------------
# Endpoints
# -------------------------------------------------

@app.post("/invoke")
def invoke_tool(
    request: Request,
    req: InvokeRequest,
    x_mcp_session: Optional[str] = Header(default=None),
):
    """
    Invoke an MCP tool with optional session support.

    - Session is carried via X-MCP-Session header
    - If missing, a new session is created
    """
    # Fix #13: rate limit per client IP
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({_RATE_LIMIT_RPM} requests/minute)",
            headers={"Retry-After": "60"},
        )

    # Fix #3: validate tool name against registry before invoking
    if req.tool not in mcp.registry.tools:
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool}' not found")

    try:
        session = session_store.get_or_create(x_mcp_session)

        result = mcp.invoke(
            tool_name=req.tool,
            inputs=req.inputs,
            context=req.context,
            session=session,
        )

        return {
            "session_id": session.session_id,
            "result": normalize_result(result),
        }

    # Fix #4: map specific exceptions to correct HTTP codes
    except ToolNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools")
def list_tools(response: Response):
    response.headers["X-Catalog-Version"] = _catalog_version()
    return mcp.list_tools()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "xco-mcp",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
    }

@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

# Fix #9: per-check timeout so /ready cannot hang indefinitely
_READY_TIMEOUT = 10  # seconds

@app.get("/ready")
def readiness_check(response: Response):
    """
    Readiness probe:
    - registry loaded
    - auth token available
    - XCO reachable (bounded by _READY_TIMEOUT)
    """

    checks = {
        "registry": False,
        "auth": False,
        "xco": False,
    }

    errors = []

    # ----------------------------------
    # 1) Registry check
    # ----------------------------------
    try:
        tools = mcp.list_tools()
        if tools and isinstance(tools, list):
            checks["registry"] = True
        else:
            errors.append("registry_empty")
    except Exception as e:
        errors.append(f"registry_error: {e}")

    # ----------------------------------
    # 2) Auth check (token fetch)
    # ----------------------------------
    try:
        token = mcp.auth.get_token()
        if token:
            checks["auth"] = True
        else:
            errors.append("auth_token_empty")
    except Exception as e:
        errors.append(f"auth_error: {e}")

    # ----------------------------------
    # 3) XCO connectivity check
    # Fix #9: wrap in a thread with timeout so it cannot hang indefinitely
    # ----------------------------------
    def _xco_probe():
        return mcp.transport.request(
            method="GET",
            path="/v1/fabric/fabrics",
            params={},
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_xco_probe)
            res = future.result(timeout=_READY_TIMEOUT)

        if res["status"] == 200:
            checks["xco"] = True
        else:
            errors.append(f"xco_status_{res['status']}")
    except concurrent.futures.TimeoutError:
        errors.append(f"xco_timeout_after_{_READY_TIMEOUT}s")
    except Exception as e:
        errors.append(f"xco_error: {e}")

    # ----------------------------------
    # Final decision
    # ----------------------------------
    if all(checks.values()):
        return {
            "status": "ready",
            "checks": checks,
        }

    response.status_code = 503
    return {
        "status": "not_ready",
        "checks": checks,
        "errors": errors,
    }
