# mcp_runtime/transport.py

import time
import requests
import urllib3

from mcp_runtime.auth import AuthManager, AuthError
from mcp_runtime.logging import setup_logging, get_logger

# --------------------------------------------------
# Logging
# --------------------------------------------------
setup_logging()
logger = get_logger("mcp.transport")

# --------------------------------------------------
# TLS warnings
# --------------------------------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --------------------------------------------------
# HTTP method allowlist
# --------------------------------------------------
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}

# --------------------------------------------------
# sensitive-value redaction for log lines
# --------------------------------------------------
_REDACT_KEYS = {"password", "token", "secret", "key", "api_key", "access_token"}


def _redact(params: dict) -> dict:
    """Return a copy of params with sensitive values masked."""
    return {k: "***" if k.lower() in _REDACT_KEYS else v for k, v in params.items()}


class XCOTransport:
    """
    Low-level HTTPS transport for XCO REST calls.

    Responsibilities:
    - Token lifecycle via AuthManager
    - HTTPS enforcement
    - Context → query param injection
    - Retry once on 401 (token refresh)
    - Structured logging (with sensitive-value redaction)
    - persistent Session for TCP connection reuse / pooling
    """

    def __init__(self, host, auth: AuthManager, verify_tls=False, timeout=20):
        if not host:
            raise ValueError("XCO host is not defined")

        self.host = host
        self.auth = auth
        self.verify_tls = verify_tls
        self.timeout = timeout

        # one Session shared across all requests so urllib3 can
        # pool and reuse the underlying TCP/TLS connection to XCO.
        self._session = requests.Session()
        self._session.verify = verify_tls

        logger.info(
            "XCOTransport initialized host=%s verify_tls=%s timeout=%ss",
            self.host,
            self.verify_tls,
            self.timeout,
        )

    # --------------------------------------------------
    # REQUEST
    # --------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        port: int | None = None,
        context: dict | None = None,
        correlation_id: str | None = None,
        body: dict | None = None,           # JSON request body (POST/PUT/PATCH)
        timeout: int | None = None,         # optional per-call timeout override
    ):
        # reject methods not in the allowlist
        method = method.upper()
        if method not in _ALLOWED_METHODS:
            raise ValueError(
                f"HTTP method '{method}' is not allowed. "
                f"Permitted: {', '.join(sorted(_ALLOWED_METHODS))}"
            )

        start_ts = time.time()

        # ---- Base params ----
        effective_params = params.copy() if params else {}

        # ---- Context → API param injection (SAFE DEFAULTS)
        # IMPORTANT:
        # - transport NEVER guesses param names
        # - it only injects *IDs*
        # - name-based params are handled at invoke() layer
        if context:
            if "fabric" in context and "id" in context["fabric"]:
                if "fabric-id" not in effective_params:
                    effective_params["fabric-id"] = context["fabric"]["id"]

            if "tenant" in context and "id" in context["tenant"]:
                if "tenant-id" not in effective_params:
                    effective_params["tenant-id"] = context["tenant"]["id"]

            if "device" in context and "id" in context["device"]:
                if "id" not in effective_params:
                    effective_params["id"] = context["device"]["id"]

        # ---- URL construction ----
        scheme = "https"
        effective_port = port or 443
        url = f"{scheme}://{self.host}:{effective_port}{path}"

        logger.debug(
            "XCO request start method=%s url=%s params=%s correlation_id=%s",
            method,
            url,
            _redact(effective_params),   # mask sensitive fields
            correlation_id,
        )

        # ---- Auth + headers ----
        headers = {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json",
        }
        # forward correlation ID so XCO-side logs can be correlated
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        # ---- Perform request (use persistent session) ----
        _timeout = timeout or self.timeout
        try:
            resp = self._session.request(
                method=method,
                url=url,
                headers=headers,
                params=effective_params,
                json=body if body is not None else None,
                timeout=_timeout,
            )
        except Exception as e:
            logger.exception(
                "XCO request failed (network) method=%s url=%s error=%s",
                method,
                url,
                str(e),
            )
            raise

        # ---- Retry once on 401 ----
        # Fix: was calling self.auth.refresh_token() which does not exist;
        # correct call is invalidate() + get_token().
        if resp.status_code == 401:
            logger.warning(
                "XCO 401 received, refreshing token and retrying url=%s",
                url,
            )
            try:
                self.auth.invalidate()
                headers["Authorization"] = f"Bearer {self.auth.get_token()}"

                resp = self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=effective_params,
                    json=body if body is not None else None,
                    timeout=_timeout,
                )
            except AuthError:
                logger.exception("XCO auth refresh failed")
                raise
            except Exception as e:
                logger.exception(
                    "XCO retry failed method=%s url=%s error=%s",
                    method,
                    url,
                    str(e),
                )
                raise

        # ---- Payload handling ----
        payload = None
        content_type = resp.headers.get("Content-Type", "")

        if resp.content:
            if "application/json" in content_type:
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {
                        "_raw": resp.text,
                        "_warning": "Response was not valid JSON",
                    }
                    logger.warning(
                        "Invalid JSON response url=%s status=%s",
                        url,
                        resp.status_code,
                    )
            else:
                # Non-JSON response. For known-binary types (ZIP/XLSX/PDF/images),
                # skip the text decode (it mangles binary and bloats the payload);
                # keep raw bytes for internal Tier-2 parsers — the HTTP boundary
                # base64-encodes them. Text-ish responses keep the decoded _raw.
                ct = content_type.lower()
                is_binary = any(tok in ct for tok in (
                    "octet-stream", "zip", "excel", "spreadsheet",
                    "pdf", "image/", "vnd.openxmlformats",
                ))
                if is_binary:
                    payload = {
                        "_raw_bytes": resp.content,
                        "_content_type": content_type,
                        "_size_bytes": len(resp.content),
                    }
                else:
                    payload = {
                        "_raw": resp.text,
                        "_raw_bytes": resp.content,
                        "_content_type": content_type,
                    }

        duration_ms = int((time.time() - start_ts) * 1000)

        logger.info(
            "XCO request done method=%s status=%s duration_ms=%s url=%s correlation_id=%s",
            method,
            resp.status_code,
            duration_ms,
            url,
            correlation_id,
        )

        return {
            "status": resp.status_code,
            "payload": payload,
            "url": url,
            "effective_port": effective_port,
            "params": effective_params,
        }
