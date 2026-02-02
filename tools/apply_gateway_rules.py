#!/usr/bin/env python3

import json
from pathlib import Path

ENDPOINTS_IN = Path("generated/resolved_endpoints.json")
CAPS_IN = Path("generated/mcp_capabilities.json")
RULES_IN = Path("generated/gateway_rules.json")

OUT = Path("generated/final_endpoints.json")


def main():
    endpoints = json.loads(ENDPOINTS_IN.read_text())
    caps = {c["id"]: c for c in json.loads(CAPS_IN.read_text())}
    rules = json.loads(RULES_IN.read_text())

    final = []

    gateway_services = set(rules.get("gateway_services", []))
    direct_services = rules.get("direct_services", {})
    disabled_services = set(rules.get("disabled_services", []))

    scheme = rules.get("scheme", "https")
    host = rules.get("host", "{XCO_HOST}")

    for ep in endpoints:
        service = ep["service"]

        if service in disabled_services:
            continue

        if service in gateway_services:
            external_url = f"{scheme}://{host}{ep['url']}"

        elif service in direct_services:
            port = direct_services[service]["port"]
            external_url = f"{scheme}://{host}:{port}{ep['url']}"

        else:
            # Unknown service → skip for now
            continue

        cap = caps.get(ep["id"])
        if not cap:
            continue

        final.append({
            "id": ep["id"],
            "service": service,
            "method": ep["method"],
            "external_url": external_url,
            "auth": ep["auth"],
            "risk": cap["risk"],
            "policy": {
                "allowed_in_auto_mode": cap["allowed_in_auto_mode"],
                "requires_confirmation": cap["requires_confirmation"]
            },
            "summary": ep.get("summary")
        })

    OUT.write_text(json.dumps(final, indent=2))
    print(f"Wrote {len(final)} endpoints to {OUT}")


if __name__ == "__main__":
    main()

