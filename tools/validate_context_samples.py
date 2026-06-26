#!/usr/bin/env python3
import json
import os
import time
import requests
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "generated/context_validation_report.json"

XCO_HOST = os.environ.get("XCO_HOST", "")
TOKEN = os.environ.get("TOKEN")

if not TOKEN:
    raise SystemExit("ERROR: TOKEN env var not set")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def get(url):
    t0 = time.time()
    r = requests.get(url, headers=HEADERS, verify=False, timeout=10)
    return r, int((time.time() - t0) * 1000)

print("▶ Phase 1.6-lite — context-aware validation")

# -------------------------------------------------
# 1. DISCOVER CONTEXT
# -------------------------------------------------
ctx = {}

print("  Discovering fabrics...")
r, _ = get(f"https://{XCO_HOST}/v1/fabric/fabrics")
r.raise_for_status()

fabrics = r.json().get("items", [])
if not fabrics:
    raise SystemExit("ERROR: No fabrics returned by XCO")

selected_fabric = None
selected_device = None

for fab in fabrics:
    devices = fab.get("fabric-devices", {}).get("items", [])
    if devices:
        selected_fabric = fab
        selected_device = devices[0]
        break

if not selected_fabric:
    raise SystemExit("ERROR: No fabric with devices found")

ctx["fabric-name"] = selected_fabric["fabric-name"]
ctx["fabric-id"] = selected_fabric["fabric-id"]
ctx["device-id"] = selected_device["device-id"]
ctx["device-ip"] = selected_device["ip-address"]
ctx["hostname"] = selected_device.get("host-name")



# -------------------------------------------------
# 2. REPRESENTATIVE ENDPOINTS
# -------------------------------------------------
tests = [
    ("GET", f"/v1/fabric/fabrics"),
    ("GET", f"/v1/fabric?name={ctx['fabric-name']}"),
    ("GET", f"/v1/fabric/{ctx['fabric-id']}"),
    ("GET", f"/v1/inventory/switches"),
    ("GET", f"/v1/inventory/switch/{ctx['device-id']}"),
    ("GET", f"/v1/inventory/switch?ip={ctx['device-ip']}"),
    ("GET", f"/v1/system/feature"),
]

results = []

print("  Validating endpoints...")
for method, path in tests:
    url = f"https://{XCO_HOST}{path}"
    try:
        r, latency = get(url)
        content_type = r.headers.get("content-type", "")
        results.append({
            "method": method,
            "path": path,
            "url": url,
            "status": r.status_code,
            "latency_ms": latency,
            "content_type": content_type,
            "classification": (
                "VALID"
                if r.status_code in (200, 400, 403)
                and "text/html" not in content_type
                else "BROKEN_OR_UI"
            )
        })
        print(f"    {path} → {r.status_code}")
    except Exception as e:
        results.append({
            "method": method,
            "path": path,
            "url": url,
            "error": str(e),
            "classification": "ERROR"
        })

OUT.write_text(json.dumps(results, indent=2))
print(f"\n✔ Wrote report → {OUT}")

