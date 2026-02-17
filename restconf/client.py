from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests


class RestconfError(Exception):
    """Raised for RESTCONF connectivity / protocol / parsing failures."""
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
    s = str(v).strip()
    return s if s else default


def _as_opt(v: Optional[str], default: Optional[str]) -> Optional[str]:
    """Return v if it is a non-empty string; otherwise default."""
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


@dataclass
class RestconfClient:
    """Tiny RESTCONF client for SLX RESTCONF endpoint (direct to switch, basic auth)."""

    switch_ip: str
    username: str
    password: str
    verify_tls: bool = True
    timeout_seconds: int = 20

    def __post_init__(self) -> None:
        if not self.switch_ip:
            raise RestconfError("Missing switch_ip")
        if not self.username or not self.password:
            raise RestconfError("Missing RESTCONF credentials (username/password).")

        self.base_url = f"https://{self.switch_ip}/restconf"

        # Some SLX resources (config datastore) live under /rest (not /restconf).
        self.rest_base_url = f"https://{self.switch_ip}/rest"

        self.session = requests.Session()
        self.session.auth = (self.username, self.password)
        self.session.verify = self.verify_tls

    # ---------------------------
    # Internal request helpers
    # ---------------------------

    def _headers(self, *, accept_json: bool = True, content_xml: bool = False) -> Dict[str, str]:
        h: Dict[str, str] = {}
        h["Accept"] = "application/yang-data+json" if accept_json else "application/yang-data+xml"
        h["Content-Type"] = "application/yang-data+xml" if content_xml else "application/yang-data+json"
        return h

    def _get_json(self, path: str) -> Dict[str, Any]:
        url = self.base_url + path
        r = self.session.get(url, headers=self._headers(accept_json=True), timeout=self.timeout_seconds)
        if r.status_code >= 400:
            raise RestconfError(f"RESTCONF GET {path} failed: {r.status_code} {r.text[:300]}")
        try:
            return r.json()
        except Exception as e:
            snippet = (r.text or "")[:300]
            ct = r.headers.get("Content-Type", "")
            raise RestconfError(
                f"RESTCONF GET returned non-JSON response (status={r.status_code}, content-type={ct}, snippet={snippet!r})"
            ) from e

    def _get_text(self, path: str, *, accept: str) -> Tuple[int, Dict[str, str], str]:
        """GET and return (status_code, headers, text) without JSON parsing."""
        url = self.base_url + path
        r = self.session.get(url, headers={"Accept": accept}, timeout=self.timeout_seconds)
        return r.status_code, dict(r.headers), r.text

    def _rest_get_text(self, path: str, *, accept: str) -> Tuple[int, Dict[str, str], str]:
        """GET using the legacy /rest API (not /restconf). Returns (status, headers, text)."""
        url = self.rest_base_url + path
        r = self.session.get(
            url,
            headers={"Accept": accept},
            timeout=self.timeout_seconds,
        )
        return r.status_code, dict(r.headers), r.text

    def _post_rpc(self, rpc: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /restconf/operations/<rpc> with JSON (yang-data+json)."""
        url = f"{self.base_url}/operations/{rpc}"
        body = payload if payload is not None else {}
        r = self.session.post(
            url,
            headers=self._headers(accept_json=True, content_xml=False),
            json=body,
            timeout=self.timeout_seconds,
        )
        if r.status_code >= 400:
            raise RestconfError(f"RESTCONF RPC {rpc} failed: {r.status_code} {r.text[:300]}")
        try:
            return r.json()
        except Exception as e:
            raise RestconfError("RESTCONF RPC returned non-JSON response") from e

    def _post_xml(self, path: str, xml_body: str) -> Dict[str, Any]:
        """POST /restconf/<path> with an XML RPC body (yang-data+xml)."""
        url = self.base_url + path
        r = self.session.post(
            url,
            headers=self._headers(accept_json=True, content_xml=True),
            data=xml_body,
            timeout=self.timeout_seconds,
        )
        if r.status_code >= 400:
            raise RestconfError(f"RESTCONF POST {path} failed: {r.status_code} {r.text[:300]}")
        try:
            return r.json()
        except Exception as e:
            raise RestconfError("RESTCONF POST returned non-JSON response") from e

    # ---------------------------
    # Public RESTCONF calls
    # ---------------------------

    def list_operations(self) -> Dict[str, Any]:
        """GET /restconf/operations"""
        return self._get_json("/operations")

    # ---- RPC wrappers (XML bodies) ----

    def show_firmware_version(self) -> Dict[str, Any]:
        """RPC: show-firmware-version"""
        body = "<show-firmware-version></show-firmware-version>"
        return self._post_xml("/operations/show-firmware-version", body)

    def get_interface_detail(self, interface_name: Optional[str]) -> Dict[str, Any]:
        """RPC: get-interface-detail"""
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

    def get_lldp_neighbor_detail(self) -> Dict[str, Any]:
        """RPC: brocade-lldp-ext:get-lldp-neighbor-detail"""
        body = "<get-lldp-neighbor-detail></get-lldp-neighbor-detail>"
        return self._post_xml("/operations/brocade-lldp-ext:get-lldp-neighbor-detail", body)

    def get_media_detail(self, interface_name: Optional[str] = None) -> Dict[str, Any]:
        """RPC: brocade-interface-ext:get-media-detail"""
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
        """RPC: brocade-arp:get-arp"""
        body = "<get-arp></get-arp>"
        return self._post_xml("/operations/brocade-arp:get-arp", body)

    def get_clock(self) -> Dict[str, Any]:
        """RPC: brocade-clock:show-clock"""
        return self._post_xml("/operations/brocade-clock:show-clock", "<show-clock/>")

    def get_vlan_brief(self) -> Dict[str, Any]:
        """RPC: brocade-interface-ext:get-vlan-brief"""
        xml = '<get-vlan-brief xmlns="urn:brocade.com:mgmt:brocade-interface-ext"></get-vlan-brief>'
        return self._post_xml("/operations/brocade-interface-ext:get-vlan-brief", xml)

    # ---- Data tree wrappers ----

    def get_vrf_tree(self) -> Dict[str, Any]:
        """GET /restconf/data/brocade-vrf:vrf (JSON)."""
        return self._get_json("/data/brocade-vrf:vrf")

    def get_vrf_tree_xml(self) -> Tuple[int, Dict[str, str], str]:
        """GET /restconf/data/brocade-vrf:vrf (XML) without parsing."""
        return self._get_text("/data/brocade-vrf:vrf", accept="application/yang-data+xml")

    def get_interface_tree_xml(self, *, depth: str = "unbounded") -> Tuple[int, Dict[str, str], str]:
        """GET /restconf/data/brocade-interface:interface (XML). Use depth=unbounded to fetch all children."""
        qs = f"?depth={depth}" if depth else ""
        return self._get_text(f"/data/brocade-interface:interface{qs}", accept="application/yang-data+xml")

    def get_interface_tree_json(self, *, depth: str = "unbounded") -> Dict[str, Any]:
        """GET /restconf/data/brocade-interface:interface (JSON). NOTE: some SLX builds return non-strict JSON."""
        qs = f"?depth={depth}" if depth else ""
        return self._get_json(f"/data/brocade-interface:interface{qs}")




    def get_running_config_xml(self, *, config_path: str = "") -> Tuple[int, Dict[str, str], str]:
        """GET /rest/config/running (XML). Optional config_path appends to the URL."""
        config_path = (config_path or "").strip()
        if config_path.startswith("/"):
            config_path = config_path[1:]
        path = "/config/running" + (f"/{config_path}" if config_path else "")
        return self._rest_get_text(path, accept="application/vnd.configuration.resource+xml")



# ---------------------------
# SLX /rest config datastore helpers
# ---------------------------

def make_client(
    switch_ip: str,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
    verify_tls: Optional[bool] = None,
    timeout_seconds: Optional[int] = None,
) -> RestconfClient:
    """Factory applying env defaults unless overridden by inputs."""
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
    c = make_client(ip)
    print(json.dumps(c.list_operations(), indent=2))
