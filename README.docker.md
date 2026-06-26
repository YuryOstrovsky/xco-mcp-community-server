# XCO MCP Community Server (Docker)

A lightweight, **read-only** MCP (Model Context Protocol) server that exposes
ExtremeCloud Orchestrator (XCO) and RESTCONF tooling as a structured API.
AI agents, scripts, and dashboards can invoke 250+ network tools through a
single `POST /invoke` endpoint.

---

## Quick Start

```bash
docker run -d --name xco-mcp \
  -p 8000:8000 \
  -e XCO_HOST=<xco-ip-or-hostname> \
  -e XCO_USERNAME=<username> \
  -e XCO_PASSWORD=<password> \
  xco-mcp-community-server
```

Verify it is running:

```bash
curl http://localhost:8000/health
```

---

## Environment Variables

### Required (XCO)

| Variable | Description |
|---|---|
| `XCO_HOST` | IP or hostname of the XCO instance |
| `XCO_USERNAME` | XCO login username |
| `XCO_PASSWORD` | XCO login password |

### Optional (XCO)

| Variable | Default | Description |
|---|---|---|
| `XCO_VERIFY_TLS` | `false` | Verify TLS certificate of XCO |
| `XCO_READ_ONLY` | `1` | Enforce read-only mode (recommended) |
| `XCO_TIMEOUT_SECONDS` | `20` | HTTP timeout for XCO API calls |

### Optional (RESTCONF / SLX switches)

| Variable | Default | Description |
|---|---|---|
| `RESTCONF_USERNAME` | `admin` | RESTCONF credentials for SLX switches |
| `RESTCONF_PASSWORD` | `password` | RESTCONF password |
| `RESTCONF_VERIFY_TLS` | `false` | Verify TLS on switch connections |

> You can also mount a `.env` file instead:
> `docker run ... -v /path/to/.env:/app/.env xco-mcp-community-server`

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/invoke` | Invoke a tool by name with inputs |
| `GET` | `/tools` | List all available tools |
| `GET` | `/health` | Health check |
| `GET` | `/ready` | Readiness probe |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/docs/tools` | Tool catalog (Markdown) |
| `GET` | `/docs/tools/html` | Tool catalog (HTML) |
| `GET` | `/swagger` | Swagger UI |
| `GET` | `/redoc` | ReDoc UI |

---

## Invoking a Tool

```bash
curl -sS -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "fabric_get_fabric_overview",
    "inputs": {}
  }' | jq
```

Response:

```json
{
  "session_id": "...",
  "result": {
    "tool": "fabric_get_fabric_overview",
    "status": 200,
    "payload": { ... }
  }
}
```

See `/docs/examples.md` inside the container or the [examples documentation](docs/examples.md)
for more invocation samples covering Fabric, Inventory, Tenant, Monitoring,
System, and RESTCONF tools.

---

## Tool Tiers

| Tier | Count | Description |
|---|---|---|
| **Tier-1** | 213 | Primitive read-only XCO endpoint wrappers |
| **Tier-2** | 38+ | Composite tools that combine multiple Tier-1 calls |

Categories: auth, fabric, faultmanager, hyperv, inventory, licensing, monitor,
notification, rbac, snmp, system, tenant, vcenter, restconf.

Browse the full catalog:

```bash
curl -sS http://localhost:8000/tools | jq '.[].name'
```

---

## Docker Compose Example

A ready-to-use [`docker-compose.yml`](docker-compose.yml) ships in the repo —
just `docker compose up -d`. The inline example below is the equivalent config:

```yaml
services:
  xco-mcp:
    image: xco-mcp-community:1.0.0
    container_name: xco-mcp
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      XCO_HOST: "10.13.85.20"
      XCO_USERNAME: "ubuntu"
      XCO_PASSWORD: "ubuntu"
      XCO_VERIFY_TLS: "false"
      XCO_READ_ONLY: "1"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

---

## Included Documentation

The container ships with documentation inside `/app/docs/`:

| File | Description |
|---|---|
| `docs/TOOL_CATALOG.md` | Full catalog of all 250+ tools with inputs and descriptions |
| `docs/examples.md` | Curl-based usage examples for every tool category |

Access the catalog through the API:

```bash
# Markdown
curl http://localhost:8000/docs/tools

# Rendered HTML
curl http://localhost:8000/docs/tools/html
```

---

## Security Notes

- The server enforces `XCO_READ_ONLY=1` by default -- no configuration-changing
  endpoints are exposed.
- All shipped Tier-2 tools are composite **read-only** operations.
- Inputs are validated before execution.
- Rate limiting is applied per source IP (60 requests/minute default).
- TLS verification is disabled by default for lab environments; enable
  `XCO_VERIFY_TLS=true` in production if certificates are properly configured.

---

## Building the Image

From the repository root:

```bash
docker build -t xco-mcp-community-server .
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `401 Unauthorized` from tools | Verify `XCO_USERNAME` / `XCO_PASSWORD` and that the user has API access |
| Connection refused | Confirm `XCO_HOST` is reachable from the container network |
| Health check failing | Check logs: `docker logs xco-mcp` |
| RESTCONF tools return errors | Ensure `RESTCONF_USERNAME` / `RESTCONF_PASSWORD` are set and the switch is reachable |
| Slow responses | Increase `XCO_TIMEOUT_SECONDS` if XCO is under load |
