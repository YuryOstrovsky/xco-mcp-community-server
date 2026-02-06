import os
import requests


class XCOClient:
    def __init__(self):
        self.base_url = os.getenv("XCO_BASE_URL")
        self.username = os.getenv("XCO_USERNAME")
        self.password = os.getenv("XCO_PASSWORD")
        self.timeout = int(os.getenv("XCO_TIMEOUT_SECONDS", "20"))
        self.read_only = os.getenv("XCO_READ_ONLY", "1") in ("1", "true", "True", "yes")

        if not self.base_url:
            raise RuntimeError("XCO_BASE_URL not set")
        if not self.username or not self.password:
            raise RuntimeError("XCO credentials not set")

        self.session = requests.Session()
        self.session.verify = False  # internal certs
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        # Basic Auth (XCO supports this)
        self.session.auth = (self.username, self.password)

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def get(self, path: str) -> dict:
        resp = self.session.get(self._url(path), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, payload: dict) -> dict:
        if self.read_only:
            raise PermissionError("READ-ONLY mode enforced by MCP")
        resp = self.session.post(self._url(path), json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

