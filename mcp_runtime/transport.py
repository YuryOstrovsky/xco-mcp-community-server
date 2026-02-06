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


class XCOTransport:
    """
    Low-level HTTPS transport for XCO REST calls.

    Responsibilities:
    - Token lifecycle via AuthManager
    - HTTPS enforcement
    - Context → query param injection
    - Retry once on 401 (token refresh)
    - Structured logging
    """

    def __init__(self, host, auth: AuthManager, verify_tls=False, timeout=20):
        if not host:
            raise ValueError("XCO host is not defined")

        self.host = host
        self.auth = auth
        self.verify_tls = verify_tls
        self.timeout = timeout

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
    ):
        start_ts = time.time()

        # ---- Base params ----
        effective_params = params.copy() if params else {}

        # ---- Context → API param injection (SAFE DEFAULTS)
        # IMPORTANT:
        #   - transport NEVER guesses param names
        #   - it only injects *IDs*
        #   - name-based params are handled at invoke() layer
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
            "XCO request start method=%s url=%s params=%s",
            method,
            url,
            effective_params,
        )

        # ---- Auth header ----
        headers = {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json",
        }

        # ---- Perform request ----
        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=effective_params,
                verify=self.verify_tls,
                timeout=self.timeout,
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
        if resp.status_code == 401:
            logger.warning(
                "XCO 401 received, refreshing token and retrying url=%s",
                url,
            )
            try:
                self.auth.refresh_token()
                headers["Authorization"] = f"Bearer {self.auth.get_token()}"

                resp = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=effective_params,
                    verify=self.verify_tls,
                    timeout=self.timeout,
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
                payload = {
                    "_raw": resp.text,
                    "_content_type": content_type,
                }

        duration_ms = int((time.time() - start_ts) * 1000)

        logger.info(
            "XCO request done method=%s status=%s duration_ms=%s url=%s",
            method,
            resp.status_code,
            duration_ms,
            url,
        )

        return {
            "status": resp.status_code,
            "payload": payload,
            "url": url,
            "effective_port": effective_port,
            "params": effective_params,
        }
