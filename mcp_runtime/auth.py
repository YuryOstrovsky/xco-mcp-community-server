# mcp_runtime/auth.py

import os
import time
import json
import base64
import requests
from threading import Lock
from mcp_runtime.logging import get_logger

logger = get_logger(__name__)


class AuthError(Exception):
    pass


class AuthManager:
    """
    Centralized XCO authentication manager.

    Responsibilities:
    - Obtain access token
    - Cache token in memory
    - Track expiration (JWT exp)
    - Refresh token automatically
    """

    def __init__(self):
        self.host = os.environ.get("XCO_HOST")
        self.username = os.environ.get("XCO_USERNAME")
        self.password = os.environ.get("XCO_PASSWORD")
        self.verify_tls = os.environ.get("XCO_VERIFY_TLS", "false").lower() == "true"

        if not self.host or not self.username or not self.password:
            raise AuthError("XCO auth environment variables are not fully defined")

        self._token = None
        self._token_expiry = 0
        self._lock = Lock()

    # ---------- Public API ----------

    def get_token(self) -> str:
        """
        Return a valid access token.
        Automatically refreshes if expired or missing.
        """
        with self._lock:
            if self._token is None or self._is_expired():
                self._login()
            return self._token

    def invalidate(self):
        """Force token refresh on next request."""
        with self._lock:
            self._token = None
            self._token_expiry = 0

    # ---------- Internal ----------

    def _is_expired(self) -> bool:
        # refresh 60 seconds before expiry
        return time.time() >= (self._token_expiry - 60)

    def _login(self):
        url = f"https://{self.host}/v1/auth/token/access-token"

        resp = requests.post(
            url,
            json={
                "username": self.username,
                "password": self.password,
            },
            headers={"Content-Type": "application/json"},
            verify=self.verify_tls,
            timeout=15,
        )

        if resp.status_code != 200:
            raise AuthError(
                f"Auth failed ({resp.status_code}): {resp.text}"
            )

        data = resp.json()
        token = data.get("access-token")

        if not token:
            raise AuthError("Auth response missing access-token")

        self._token = token
        self._token_expiry = self._decode_exp(token)

    def _decode_exp(self, jwt_token: str) -> int:
        """
        Decode JWT 'exp' without verifying signature.
        """
        try:
            payload = jwt_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            return int(decoded.get("exp", 0))
        except Exception as e:
            logger.warning("JWT decode failed, forcing early refresh: %s", e)
            return int(time.time()) + 300

