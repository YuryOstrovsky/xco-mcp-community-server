#!/usr/bin/env python3
import json
import time
import requests
import os

INPUT = "generated/mcp_tools.json"
OUTPUT = "generated/read_probe_results.json"

XCO_HOST = os.environ.get("XCO_HOST")
TOKEN = os.environ.get("TOKEN")

if not XCO_HOST or not TOKEN:
    raise SystemExit("ERROR: XCO_HOST or TOKEN env var not set")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

def is_safe_to_probe(tool):
    if tool["method"] != "GET":
        return False

    policy = tool.get("policy", {})
    if policy.get("risk") != "SAFE_READ":
        return False

    schema = tool.get("input_schema", {})
    required = schema.get("required", [])
    if required:
        return False

    return True

def main():
    tools = json.load(open(INPUT))
    results = []

    session = requests.Session()
    session.verify = False
    session.headers.update(HEADERS)

    safe_tools = [t for t in tools if is_safe_to_probe(t)]

    print(f"Probing {len(safe_tools)} SAFE_READ GET endpoints")

    for tool in safe_tools:
        ep = tool["endpoint"]
        url = f"https://{XCO_HOST}:{ep['port']}{ep['path']}"

        start = time.time()
        try:
            r = session.get(url, timeout=10)
            latency = int((time.time() - start) * 1000)

            ok = r.status_code < 400

            results.append({
                "name": tool["name"],
                "method": "GET",
                "url": url,
                "status": r.status_code,
                "ok": ok,
                "latency_ms": latency,
                "error": None if ok else r.text[:200]
            })

        except Exception as e:
            results.append({
                "name": tool["name"],
                "method": "GET",
                "url": url,
                "status": None,
                "ok": False,
                "latency_ms": None,
                "error": str(e)
            })

    json.dump(results, open(OUTPUT, "w"), indent=2)
    print(f"Wrote {len(results)} results to {OUTPUT}")

if __name__ == "__main__":
    main()

