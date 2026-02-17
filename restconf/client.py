from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class RestconfError(Exception):
    pass


def _env_bool(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None:
        return default
    v = str(v).strip()
    return v if v else default


def _as_opt(v: Optional[str], default: Optional[str]) -> Optional[str]:
    """Return `v` if it is a non-empty string, otherwise `default`."""
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


@dataclass
class RestconfClient:
    """Small RESTCONF client for SLX RESTCONF endpoint (HTTP Basic auth)."""

    switch_ip: str
    username: str
    password: str
    verify_tls: bool = True
    timeout_seconds: int = 20

    def __post_init__(self):
        if not self.switch_ip:
            raise RestconfError("Missing switch_ip")
        if not self.username or not self.password:
            raise RestconfError("Missing RESTCONF credentials (username/password).")

        self.base_url = f"https://{self.switch_ip}/restconf"

        self.session = requests.Session()
        self.session.auth = (self.username, self.password)
        self.session.verify = self.verify_tls

    # ---------------------------
    # Internal request helpers
    # ---------------------------

    def _headers(self, accept_json: bool = True, content_xml: bool = False) -> Dict[str, str]:
        h: Dict[str, str] = {}
        h["Accept"] = "application/yang-data+json" if accept_json else "application/yang-data+xml"
        if content_xml:
            h["Content-Type"] = "application/yang-data+xml"
        return h

    def _get_json(self, path: str) -> Dict[str, Any]:
        url = self.base_url + path
        r = self.session.get(url, headers=self._headers(accept_json=True), timeout=self.timeout_seconds)
        if r.status_code >= 400:
            raise RestconfError(f"RESTCONF GET {path} failed: {r.status_code} {r.text[:200]}")
        try:
            return r.json()
        except Exception as e:
            raise RestconfError("RESTCONF GET returned non-JSON response") from e

    def _post_xml(self, path: str, xml_body: str) -> Dict[str, Any]:
        url = self.base_url + path
        r = self.session.post(
            url,
            headers=self._headers(accept_json=True, content_xml=True),
            data=xml_body,
            timeout=self.timeout_seconds,
        )
        if r.status_code >= 400:
            raise RestconfError(f"RESTCONF POST {path} failed: {r.status_code} {r.text[:200]}")
        try:
            return r.json()
        except Exception as e:
            raise RestconfError("RESTCONF POST returned non-JSON response") from e

    # ---------------------------
    # Public API calls
    # ---------------------------

    def list_operations(self) -> Dict[str, Any]:
        # GET /restconf/operations
        return self._get_json("/operations")

    def show_firmware_version(self) -> Dict[str, Any]:
        # POST /restconf/operations/show-firmware-version
        body = "<show-firmware-version></show-firmware-version>"
        return self._post_xml("/operations/show-firmware-version", body)

    def get_interface_detail(self, interface_name: Optional[str]) -> Dict[str, Any]:
        # POST /restconf/operations/get-interface-detail
        # Some builds accept <interface-name>, some accept <name>. We'll send both.
        if interface_name:
            body = (
                "<get-interface-detail>"
                f"<interface-name>{interface_name}</interface-name>"
                f"<name>{interface_name}</name>"
                "</get-interface-detail>"
            )
        else:
            body = "<get-interface-detail></get-interface-detail>"
        return self._post_xml("/operations/get-interface-detail", body)

    def get_media_detail(self, interface_name: Optional[str] = None) -> Dict[str, Any]:
        # brocade-interface-ext:get-media-detail
        # Platforms vary on parameter tags. We'll send a few common ones.
        if interface_name:
            raw = str(interface_name).strip()
            short = raw
            for prefix in ("Ethernet", "Eth", "eth", "ethernet"):
                short = short.replace(prefix, "")
            short = short.strip()

            body = (
                "<get-media-detail>"
                f"<if-name>{raw}</if-name>"
                f"<interface-name>{short}</interface-name>"
                f"<name>{raw}</name>"
                "</get-media-detail>"
            )
        else:
            body = "<get-media-detail></get-media-detail>"

        return self._post_xml("/operations/brocade-interface-ext:get-media-detail", body)


    def get_arp_table(self) -> Dict[str, Any]:
        # brocade-arp:get-arp
        # Most SLX builds accept the empty RPC body.
        body = "<get-arp></get-arp>"
        return self._post_xml("/operations/brocade-arp:get-arp", body)

    def get_lldp_neighbor_detail(self) -> Dict[str, Any]:
        # brocade-lldp-ext:get-lldp-neighbor-detail
        body = "<get-lldp-neighbor-detail></get-lldp-neighbor-detail>"
        return self._post_xml("/operations/brocade-lldp-ext:get-lldp-neighbor-detail", body)


def make_client(
    switch_ip: str,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
    verify_tls: Optional[bool] = None,
    timeout_seconds: Optional[int] = None,
) -> RestconfClient:
    """Factory that applies env defaults unless overridden by inputs."""
    u = _as_opt(username, _env_str("RESTCONF_USERNAME"))
    p = _as_opt(password, _env_str("RESTCONF_PASSWORD"))

    if verify_tls is None:
        verify_tls = _env_bool("RESTCONF_VERIFY_TLS", default=True)
    if timeout_seconds is None:
        timeout_seconds = int(_env_str("RESTCONF_TIMEOUT_SECONDS", "20") or "20")

    return RestconfClient(
        switch_ip=switch_ip,
        username=u or "",
        password=p or "",
        verify_tls=bool(verify_tls),
        timeout_seconds=int(timeout_seconds),
    )


# ---------------------------
# Local CLI test harness
# ---------------------------
if __name__ == "__main__":
    import sys

    ip = sys.argv[1] if len(sys.argv) > 1 else ""
    client = make_client(ip)
    out = client.show_firmware_version()
    print(json.dumps(out, indent=2))

    def get_clock(self):
        """Call brocade-clock:show-clock RPC (best-effort)."""
        # Many SLX builds accept empty body for show-clock.
        # Keep this tolerant: no required inputs.
        return self._post_xml("/operations/brocade-clock:show-clock", "<show-clock/>")
