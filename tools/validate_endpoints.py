#!/usr/bin/env python3

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
GENERATED = BASE / "generated"

# INPUTS
ENDPOINTS_FILE = GENERATED / "mcp_tools.json"
PROBES_FILE = GENERATED / "read_probe_results.json"

# OUTPUT
OUTPUT_FILE = GENERATED / "validated_endpoints.json"


def main():
    if not ENDPOINTS_FILE.exists():
        raise SystemExit(f"Missing {ENDPOINTS_FILE}")

    if not PROBES_FILE.exists():
        raise SystemExit(f"Missing {PROBES_FILE}")

    endpoints = json.loads(ENDPOINTS_FILE.read_text())
    probes = json.loads(PROBES_FILE.read_text())

    # Build probe lookup by MCP tool name
    probe_by_name = {}
    for p in probes:
        name = p.get("name")
        if name:
            probe_by_name[name] = p

    validated = []

    for ep in endpoints:
        name = ep.get("name")
        if not name:
            continue

        probe = probe_by_name.get(name)

        record = {
            "name": name,
            "method": ep.get("method"),
            "endpoint": ep.get("endpoint"),
            "policy": ep.get("policy"),
            "validated": False,
            "status": None,
            "latency_ms": None,
            "error": None,
            "classification": None,
        }

        if probe:
            record["validated"] = probe.get("ok", False)
            record["status"] = probe.get("status")
            record["latency_ms"] = probe.get("latency_ms")
            record["error"] = probe.get("error")

            if probe.get("ok"):
                record["classification"] = "VALID"
            elif probe.get("status") in (401, 403):
                record["classification"] = "AUTH_REQUIRED"
            elif probe.get("status") == 404:
                record["classification"] = "NOT_EXPOSED_OR_CONTEXTUAL"
            else:
                record["classification"] = "ERROR"
        else:
            record["classification"] = "NOT_PROBED"

        validated.append(record)

    OUTPUT_FILE.write_text(json.dumps(validated, indent=2))
    print(f"Wrote {len(validated)} validated endpoints to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

