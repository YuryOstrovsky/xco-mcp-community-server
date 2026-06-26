# mcp_runtime/auth.py

import os
import time
import requests
import jwt  # PyJWT — proper JWT decode
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
        # .strip() these: Docker `--env-file` passes values literally (including
        # stray trailing whitespace), unlike python-dotenv which strips unquoted
        # values. A trailing space in XCO_HOST otherwise URL-encodes to %20 and
        # breaks DNS resolution.
        self.host = (os.environ.get("XCO_HOST") or "").strip()
        self.username = (os.environ.get("XCO_USERNAME") or "").strip()
        self.password = (os.environ.get("XCO_PASSWORD") or "").strip()
        self.verify_tls = os.environ.get("XCO_VERIFY_TLS", "false").strip().lower() == "true"

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

        double-checked locking — fast path avoids lock overhead for
        the common case where the token is already valid.
        """
        # Fast path: no lock needed when token is clearly still valid
        if self._token is not None and not self._is_expired():
            return self._token
        # Slow path: take lock, re-check (another thread may have refreshed
        # between the two checks above), then refresh only if still needed
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
        Decode JWT 'exp' using PyJWT without signature verification.

        replaces hand-rolled base64 split with PyJWT, which handles
        padding, encoding edge-cases, and malformed tokens more robustly.
        Signature verification is intentionally skipped — we are a consumer
        of XCO-issued tokens and do not hold the signing secret.
        """
        try:
            decoded = jwt.decode(
                jwt_token,
                options={"verify_signature": False},
                algorithms=["HS256", "RS256", "ES256"],
            )
            return int(decoded.get("exp", 0))
        except Exception as e:
            logger.warning("JWT decode failed, forcing early refresh: %s", e)
            return int(time.time()) + 300
