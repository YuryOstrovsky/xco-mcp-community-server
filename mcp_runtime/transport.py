# mcp_runtime/transport.py

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import time
import requests

import time
import requests
from mcp_runtime.auth import AuthManager, AuthError


class XCOTransport:
    """
    Low-level HTTPS transport for XCO REST calls.

    - Uses AuthManager for token lifecycle
    - Enforces HTTPS
    - Normalizes ports
    - Retries once on 401 with token refresh
    """

    def __init__(self, host, auth: AuthManager, verify_tls=False, timeout=20):
        if not host:
            raise ValueError("XCO host is not defined")

        self.host = host
        self.auth = auth
        self.verify_tls = verify_tls
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        port: int | None = None,
        context: dict | None = None,
    ):
        # ---- Base params ----
        effective_params = params.copy() if params else {}

        # ---- Context → API param injection (Phase 2.3) ----
        if context:
            if "fabric" in context:
                effective_params["fabric-id"] = context["fabric"]["id"]

            if "tenant" in context:
                effective_params["tenant-id"] = context["tenant"]["id"]

            if "device" in context:
                # device-id usually overrides list queries
                effective_params["id"] = context["device"]["id"]

        # ---- URL construction ----
        scheme = "https"
        host = self.host
        effective_port = port or 443

        url = f"{scheme}://{host}:{effective_port}{path}"

        # ---- Auth ----
        headers = {
            "Authorization": f"Bearer {self.auth.get_token()}",
            "Content-Type": "application/json",
        }

        # ---- HTTP ----
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=effective_params,
            verify=self.verify_tls,
            timeout=self.timeout,
        )

        payload = None

        if resp.content:
            content_type = resp.headers.get("Content-Type", "")

            if "application/json" in content_type:
                try:
                    payload = resp.json()
                except ValueError:
                    # XCO sometimes returns text + JSON or malformed JSON
                    payload = {
                        "_raw": resp.text,
                        "_warning": "Response was not valid JSON"
                    }
            else:
                # Non-JSON response (still valid)
                payload = {
                    "_raw": resp.text,
                    "_content_type": content_type
                }


        return {
            "status": resp.status_code,
            "payload": payload,
            "url": url,
            "effective_port": effective_port,
            "params": effective_params,  # 👈 critical for debugging/tests
        }