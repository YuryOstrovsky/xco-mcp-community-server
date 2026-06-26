"""Real MCP protocol transport (JSON-RPC 2.0 over Streamable HTTP).

A standards-compliant MCP endpoint (`initialize` / `tools/list` / `tools/call`)
so MCP Inspector, Claude Desktop, and any standard MCP client connect with ZERO
shim — alongside, never instead of, the existing `POST /invoke` REST front door.

Design (additive / non-breaking):
- The registry (`MCPServer`) is the single source of truth. `tools/call` routes
  through the SAME `mcp.invoke(...)` path as `/invoke` — same audit log — so the
  two front doors can never diverge.
- `tools/list` is the served catalog (`generated/mcp_tools.json`), mapped into
  MCP `Tool` objects.

Transport mode: stateful sessions, `json_response=True`. The app's middlewares
are all BaseHTTPMiddleware (which buffer responses and would break SSE); JSON
responses sidestep that entirely and are fully Streamable-HTTP conformant for
request/response methods. No server-initiated streaming by default.

This community edition is auth-free: there is no scope enforcement and no caller
identity — `tools/call` dispatches straight through `mcp.invoke(...)`, exactly
like `POST /invoke`.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import re

import anyio
import mcp.types as mcp_types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from mcp_runtime.payload_normalize import normalize_result
from mcp_runtime.catalog_version import compute_catalog_version

log = logging.getLogger("mcp.transport")

_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generated", "mcp_tools.json",
)


def _load_catalog() -> List[Dict[str, Any]]:
    try:
        with open(_CATALOG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else data.get("tools", [])
    except Exception as e:  # noqa: BLE001
        log.error("MCP transport: failed to load catalog: %s", e)
        return []


# Standard XCO MCP response envelope — what a `tools/call` returns as the
# TextContent JSON body.  Attached as `outputSchema` so a client can validate
# the wrapper without per-tool authoring.
_OUTPUT_ENVELOPE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": "Standard XCO MCP response envelope. Payload keys are "
                   "snake_case (hyphenated/camelCase keys carry snake_case "
                   "aliases); identifier fields are never null.",
    "properties": {
        "tool": {"type": "string"},
        "status": {"type": "integer", "description": "HTTP-style status (200 = ok)."},
        # payload shape is tool-specific (and an error payload may be a string),
        # so it is left untyped here — the wrapper is what we pin.
        "payload": {"description": "Tool-specific result data (snake_case keys)."},
        "meta": {"type": "object", "description": "request_id, correlation_id, risk, …"},
    },
    "required": ["status"],
}

# Tools that surface execution/MCP telemetry rather than operator data — clients
# may skip these for user-facing dashboards (annotations.audience server).
_TELEMETRY_TOOLS = {
    "notification_get_recent_events_filtered",
    "monitor_get_consumer_activity",
}

# Liveness heartbeat interval (seconds) for progress notifications.
_PROGRESS_HEARTBEAT_S = 2.5


# p50 wall-clock ESTIMATE (seconds) so a client can pick blocking vs spinner UX
# without a profiling pass. Heuristic by method/role — refine per-tool from real
# telemetry later.
def _estimated_seconds(entry: Dict[str, Any]) -> float:
    name = entry.get("name", "")
    method = (entry.get("method") or "").upper()
    risk = (entry.get("policy") or {}).get("risk", "")
    if "platform_health" in name:
        return 10.0           # 13-probe fan-out
    if method == "COMPOSITE":
        return 8.0            # multi-switch composites
    if method in ("SSH_READ", "SSH"):
        return 3.0
    if risk in ("HIGH", "DESTRUCTIVE"):
        return 5.0
    if method == "GET":
        return 0.8
    return 1.5


def _category(entry: Dict[str, Any]) -> str:
    """Stable de-facto namespace (prefix-derived) for client-side triage."""
    cat = entry.get("category")
    if cat:
        return str(cat)
    name = entry.get("name", "")
    return name.split("_", 1)[0] if "_" in name else (name or "misc")


def _concise_description(entry: Dict[str, Any]) -> str:
    """One-line, LLM-pickable description: the `summary` if present, else the
    first sentence of the prose `description`."""
    s = (entry.get("summary") or "").strip()
    if s:
        return s
    d = (entry.get("description") or "").strip()
    first = re.split(r"(?<=[.!?])\s+", d, maxsplit=1)[0] if d else ""
    return (first[:240]).strip() or d[:240].strip()


def _title(entry: Dict[str, Any]) -> str:
    return entry.get("name", "").replace("_", " ").title()


def _tool_to_mcp(entry: Dict[str, Any]) -> mcp_types.Tool:
    """Map a served-catalog entry → an MCP Tool object with title, one-line
    description (full prose moved to meta.details), outputSchema, and rich
    annotations (category, audience, estimated_seconds, idempotentHint)."""
    schema = entry.get("input_schema") or {"type": "object", "properties": {}}
    risk = (entry.get("policy") or {}).get("risk", "")
    is_read = risk == "SAFE_READ"

    annotations = mcp_types.ToolAnnotations(
        title=_title(entry),
        readOnlyHint=is_read,
        destructiveHint=(risk in ("HIGH", "DESTRUCTIVE")),
        idempotentHint=is_read,
        # extra fields (ToolAnnotations allows extra; they survive model_dump)
        category=_category(entry),
        audience=(["server"] if entry.get("name") in _TELEMETRY_TOOLS
                  or (entry.get("name", "").startswith("monitor_"))
                  else ["user"]),
        estimated_seconds=_estimated_seconds(entry),
    )

    full_desc = entry.get("description") or entry.get("summary") or ""
    tool_kwargs: Dict[str, Any] = dict(
        name=entry["name"],
        title=_title(entry),
        description=_concise_description(entry) or full_desc,
        inputSchema=schema,
        annotations=annotations,
    )
    # outputSchema on read / composite tools (envelope wrapper).
    if is_read or (entry.get("method") == "COMPOSITE"):
        tool_kwargs["outputSchema"] = _OUTPUT_ENVELOPE_SCHEMA
    tool = mcp_types.Tool(**tool_kwargs)
    # full prose moves to `_meta.details` (the field uses the `_meta` alias);
    # set post-construction so it populates the real field, not extras.
    tool.meta = {"details": full_desc, "category": _category(entry)}
    return tool


class MCPTransport:
    """Holds the SDK Server + session manager, exposes an ASGI handler + a
    lifespan hook for mounting into the FastAPI app."""

    def __init__(self, mcp_runtime: Any, *, server_version: str = "1.0"):
        self._runtime = mcp_runtime
        # Serve the registry's catalog (the single source of truth) so /mcp
        # tools/list matches GET /tools exactly — same tool set, same advertised
        # catalog_version — and we never advertise an unregistered tool that
        # tools/call would then reject as 'not found'.  Fall back to the raw
        # catalog file only if the registry can't be enumerated.
        try:
            self._catalog = self._runtime.list_tools()
        except Exception:  # noqa: BLE001
            self._catalog = _load_catalog()
        self._catalog_version = compute_catalog_version(self._catalog)
        # Progress notifications — DEFAULT OFF. When off the transport behaves
        # exactly as a plain json_response=True endpoint (no streaming). When
        # on, responses stream as SSE with a heartbeat during long tool calls —
        # but that requires the `/mcp` mount to stream through the app's
        # BaseHTTPMiddleware (which today buffer SSE), so validate with the MCP
        # conformance harness before flipping the default.
        self._progress_enabled = os.environ.get(
            "MCP_PROGRESS_NOTIFICATIONS", "false").lower() in ("1", "true", "yes", "on")
        self._server: Server = Server(
            "xco-mcp",
            version=server_version,
            instructions=(
                "Extreme XCO / SLX data-centre control surface. Read-only "
                "visibility into fabric, tenant, inventory, fault, and firmware "
                "state via the same registry as POST /invoke; see each tool's "
                "annotations for category and estimated runtime."
            ),
        )
        self._register_handlers()
        self._advertise_catalog_version()
        # The session manager's .run() is one-shot per instance, so it is built
        # fresh per lifespan (see lifespan()).  The Server itself is reusable.
        self._sessions: StreamableHTTPSessionManager | None = None

    def _new_session_manager(self) -> StreamableHTTPSessionManager:
        # Stateful sessions (Mcp-Session-Id) — what Inspector / Claude Desktop
        # expect.  json_response=True keeps responses plain application/json (the
        # app's BaseHTTPMiddleware buffer/break SSE); MCP_PROGRESS_NOTIFICATIONS
        # flips it to SSE so progress can stream.
        return StreamableHTTPSessionManager(
            self._server, stateless=False,
            json_response=not self._progress_enabled)

    def _advertise_catalog_version(self) -> None:
        """Surface `catalog_version` in `initialize` (experimental capability)
        and advertise `tools.listChanged` so a client can short-circuit
        re-discovery.  The session manager calls `create_initialization_options()`
        with no args, so we override the instance method to inject our options."""
        from mcp.server.lowlevel.server import NotificationOptions
        _orig = self._server.create_initialization_options

        def _patched(notification_options=None, experimental_capabilities=None):
            return _orig(
                notification_options=NotificationOptions(tools_changed=True),
                experimental_capabilities={
                    "catalog": {"version": self._catalog_version},
                },
            )
        self._server.create_initialization_options = _patched  # type: ignore[assignment]

    # -- MCP method handlers --------------------------------------------
    def _register_handlers(self) -> None:
        @self._server.list_tools()
        async def _list_tools() -> List[mcp_types.Tool]:  # noqa: ANN202
            return [_tool_to_mcp(e) for e in self._catalog if e.get("name")]

        @self._server.call_tool()
        async def _call_tool(
            name: str, arguments: Dict[str, Any],
        ) -> List[mcp_types.ContentBlock]:  # noqa: ANN202
            return await self._dispatch_tool(name, arguments or {})

    async def _dispatch_tool(
        self, name: str, arguments: Dict[str, Any],
    ) -> List[mcp_types.ContentBlock]:
        """Route a tools/call through the SAME path as /invoke (audit lives
        there). Auth-free community edition: no scope enforcement."""
        from mcp_runtime.errors import ToolNotFound

        reg = self._runtime.registry
        if name not in reg.tools:
            raise ToolNotFound(f"Tool '{name}' not found")

        inputs = arguments
        # mcp.invoke is synchronous (tools do blocking SSH/HTTP) — run off the
        # event loop, optionally with a progress heartbeat (flag-gated).
        result = await self._invoke_with_optional_progress(name, inputs)

        # snake_case-normalise the payload at the boundary (same as /invoke) so
        # MCP clients consume one canonical, hyphen-free shape.
        result = normalize_result(result)
        text = json.dumps(result, ensure_ascii=False, default=str)
        content: List[mcp_types.ContentBlock] = [
            mcp_types.TextContent(type="text", text=text)]
        # Also return the envelope as STRUCTURED content (JSON round-tripped so
        # it is plain JSON for jsonschema validation) — tools that declare an
        # outputSchema require it, and structured output is what modern MCP
        # clients prefer.  Harmless for tools without an outputSchema.
        structured = json.loads(text) if isinstance(result, dict) else None
        if structured is not None:
            return content, structured
        return content

    # -- progress heartbeat (flag-gated) ---------------------------------
    def _progress_target(self):
        """Return (progress_token, session) if progress is enabled AND this
        request carried a progressToken; else (None, None).  Best-effort —
        never raises into the call path."""
        if not self._progress_enabled:
            return None, None
        try:
            ctx = self._server.request_context
            meta = getattr(ctx, "meta", None)
            token = getattr(meta, "progressToken", None) if meta else None
            return (token, ctx.session) if token is not None else (None, None)
        except Exception:  # noqa: BLE001
            return None, None

    async def _invoke_with_optional_progress(self, name, inputs):
        """Run the (blocking) tool off the event loop.  When progress is enabled
        and the client sent a progressToken, emit a liveness heartbeat
        (`notifications/progress`) every few seconds until it completes — so a
        UI doesn't look hung on a long fan-out."""
        def _invoke():
            return self._runtime.invoke(tool_name=name, inputs=inputs,
                                        context=None, session=None)

        token, session = self._progress_target()
        if token is None:
            return await anyio.to_thread.run_sync(_invoke)

        import time
        holder: Dict[str, Any] = {}

        async def _run():
            holder["r"] = await anyio.to_thread.run_sync(_invoke)

        async def _heartbeat():
            t0 = time.monotonic()
            n = 0
            try:
                await session.send_progress_notification(
                    progress_token=token, progress=0.0,
                    message=f"starting {name}…")
                while True:
                    await anyio.sleep(_PROGRESS_HEARTBEAT_S)
                    n += 1
                    await session.send_progress_notification(
                        progress_token=token, progress=float(n),
                        message=f"running {name}… {time.monotonic() - t0:.0f}s")
            except Exception:  # noqa: BLE001
                return  # heartbeat is best-effort; never affect the result

        async with anyio.create_task_group() as tg:
            tg.start_soon(_heartbeat)
            await _run()
            tg.cancel_scope.cancel()
        return holder["r"]

    # -- ASGI plumbing ---------------------------------------------------
    async def handle_asgi(self, scope, receive, send) -> None:
        """ASGI entry point for the /mcp mount.  Auth-free: just hand the request
        to the streamable-HTTP session manager."""
        sessions = self._sessions
        if sessions is None:  # lifespan not active (shouldn't happen in prod)
            from starlette.responses import PlainTextResponse
            await PlainTextResponse("MCP transport not ready", status_code=503)(
                scope, receive, send)
            return
        await sessions.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan(self):
        """Run a FRESH session manager's task group for the app's lifetime.
        Fresh per lifespan because SessionManager.run() is one-shot per instance
        (lets multiple test-client lifespans coexist in one process)."""
        self._sessions = self._new_session_manager()
        try:
            async with self._sessions.run():
                log.info("MCP transport ready (streamable-http, json) at /mcp")
                yield
        finally:
            self._sessions = None
