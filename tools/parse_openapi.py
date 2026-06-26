import json
import re
from pathlib import Path
from urllib.parse import urlparse

OPENAPI_DIR = Path("openapi/openapi-specs")
OUTPUT_DIR = Path("generated")

OUTPUT_DIR.mkdir(exist_ok=True)

services = {}
endpoints = []


def parse_server_url(url: str):
    """
    Example: http://monitor-service:8078/v1
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 80
    base_path = parsed.path.rstrip("/")
    return host, port, base_path


for file in OPENAPI_DIR.glob("*.json"):
    with open(file, "r") as f:
        spec = json.load(f)

    # ---- Service name inference ----
    title = spec.get("info", {}).get("title", file.stem)
    service_key = re.sub(r"\s+Service$", "", title).lower().replace(" ", "_")

    servers = spec.get("servers", [])
    if not servers:
        print(f"[WARN] No servers defined in {file.name}")
        continue

    server_url = servers[0]["url"]
    service_host, service_port, base_path = parse_server_url(server_url)

    services[service_key] = {
        "service": service_host,
        "port": service_port,
        "base_path": base_path,
        "openapi_file": file.name,
        "title": title,
    }

    # ---- Paths ----
    for path, methods in spec.get("paths", {}).items():
        for method, meta in methods.items():
            method_upper = method.upper()

            params = {
                "path": [],
                "query": [],
                "body": None,
            }

            for p in meta.get("parameters", []):
                location = p.get("in")
                if location in params:
                    params[location].append({
                        "name": p.get("name"),
                        "required": p.get("required", False),
                        "schema": p.get("schema", {}),
                    })

            if "requestBody" in meta:
                params["body"] = meta["requestBody"]

            endpoints.append({
                "service": service_key,
                "method": method_upper,
                "path": path,
                "operationId": meta.get("operationId"),
                "summary": meta.get("summary"),
                "description": meta.get("description"),
                "auth": "bearer" if meta.get("security") else "none",
                "params": params,
            })


# ---- Write outputs ----
with open(OUTPUT_DIR / "services.json", "w") as f:
    json.dump(services, f, indent=2)

with open(OUTPUT_DIR / "endpoints.json", "w") as f:
    json.dump(endpoints, f, indent=2)

print(f"Parsed {len(services)} services")
print(f"Parsed {len(endpoints)} endpoints")
print("Output written to ./generated/")

