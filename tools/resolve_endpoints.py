import json
from pathlib import Path

BASE_DIR = Path("generated")
SERVICES_FILE = BASE_DIR / "services.json"
ENDPOINTS_FILE = BASE_DIR / "endpoints.json"
OUTPUT_FILE = BASE_DIR / "resolved_endpoints.json"


def classify_risk(method: str) -> str:
    if method.upper() == "GET":
        return "SAFE_READ"
    return "MUTATION"


def main():
    with open(SERVICES_FILE) as f:
        services = json.load(f)

    with open(ENDPOINTS_FILE) as f:
        endpoints = json.load(f)

    resolved = []

    for ep in endpoints:
        service_key = ep["service"]
        if service_key not in services:
            # Skip endpoints with unknown service (should not happen)
            continue

        svc = services[service_key]

        base_path = svc["base_path"].rstrip("/")
        ep_path = ep["path"]
        if not ep_path.startswith("/"):
            ep_path = "/" + ep_path

        full_path = f"{base_path}{ep_path}"

        method = ep["method"].upper()
        risk = classify_risk(method)

        resolved.append({
            "id": f"{service_key}.{method}.{ep_path.strip('/').replace('/', '_')}",
            "service": service_key,
            "method": method,
            "host": "{XCO_HOST}",
            "port": svc["port"],
            "url": full_path,
            "auth": ep.get("auth", "none"),
            "risk": risk,
            "operationId": ep.get("operationId"),
            "summary": ep.get("summary"),
            "description": ep.get("description"),
            "params": ep.get("params", {}),
        })

    with open(OUTPUT_FILE, "w") as f:
        json.dump(resolved, f, indent=2)

    print(f"Resolved {len(resolved)} endpoints")
    print(f"Output written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

