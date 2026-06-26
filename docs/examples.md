# XCO MCP Server – Usage Examples

This file contains real invocation examples for the XCO MCP Server.

All tools are invoked via:

POST http://<your_mcp_IP_addr>:8000/invoke

---

## Running with Docker

```bash
docker run -d --name xco-mcp \
  -p 8000:8000 \
  -e XCO_HOST=<xco-ip-or-hostname> \
  -e XCO_USERNAME=<username> \
  -e XCO_PASSWORD=<password> \
  xco-mcp-community:1.0.0
```

Or with a `.env` file:

```bash
docker run -d --name xco-mcp \
  -p 8000:8000 \
  -v /path/to/.env:/app/.env \
  xco-mcp-community:1.0.0
```

Verify the server is up:

```bash
curl http://localhost:8000/health
```

When running in Docker, replace `<your_mcp_IP_addr>` with `localhost`
(or the Docker host IP) in all examples below.

---

## 0️⃣ Base Variables (Optional Helper)

```bash
export MCP="http://<your_mcp_IP_addr>:8000/invoke"
```

---

# 🧩 Discovery Tools (paired-ID lookups)

SAFE_READ tools that return IDs in clean snake_case, so you can feed them
straight into ID-required tools without hard-coding a value from a cached
sample.

## fabric_get_fabric_names

```bash
curl -sS -X POST "$MCP" -H "Content-Type: application/json" \
  -d '{"tool":"fabric_get_fabric_names","inputs":{}}' \
| jq '.result.payload | {fabric_names, fabrics, count}'
# → fabric_names:[...], fabrics:[{fabric_name, fabric_id, fabric_type}], count
```

## inventory_list_device_ids

```bash
curl -sS -X POST "$MCP" -H "Content-Type: application/json" \
  -d '{"tool":"inventory_list_device_ids","inputs":{}}' \
| jq '.result.payload | {device_ids, count}'
# → device_ids:[...], devices:[{device_id, ip, hostname}], count
```

## tenant_list_ids

```bash
curl -sS -X POST "$MCP" -H "Content-Type: application/json" \
  -d '{"tool":"tenant_list_ids","inputs":{}}' \
| jq '.result.payload | {tenant_ids, tenants, count}'
# → tenant_ids:[...], tenants:[{tenant_id, tenant_name}], count
```

---

# 🧩 Fabric Tools

---

## 1️⃣ fabric_get_fabric_overview

Use-case:
> "Show me all fabrics with status, type, stage and health summary."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{"tool":"fabric_get_fabric_overview","inputs":{}}' \
| jq
```

---

## 2️⃣ fabric_get_fabric_health_summary

Use-case:
> "Why is Fabric DC red?"

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{
        "tool":"fabric_get_fabric_health_summary",
        "inputs":{"fabric_name":"DC"}
      }' \
| jq
```

---

## 3️⃣ fabric_get_fabric_validation_report

Use-case:
> "Show validation issues for Fabric DC."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{
        "tool":"fabric_get_fabric_validation_report",
        "inputs":{"fabric_name":"DC"}
      }' \
| jq
```

---

# 🧩 Inventory Tools

---

## 4️⃣ inventory_get_unreachable_devices

Use-case:
> "Show unreachable devices across fabrics."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{"tool":"inventory_get_unreachable_devices","inputs":{}}' \
| jq '.result.payload.payload'
```

---

## 5️⃣ inventory_switch_inventory_info

Use-case:
> "Show hardware inventory for a specific switch."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{
        "tool":"inventory_switch_inventory_info",
        "inputs":{"device_id":15}
      }' \
| jq '.result.payload'
```

---

# 🧩 Tenant Tools

---

## 6️⃣ tenant_get_service_epg_event_logs

Use-case:
> "Show EPG event logs for tenant DC."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{
        "tool":"tenant_get_service_epg_event_logs",
        "inputs":{"tenant_name":"DC"}
      }' \
| jq '.result.payload'
```

---

## 7️⃣ tenant_get_service_epg_alarm_summary

Use-case:
> "Show Service/EPG alarms filtered by severity."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{
        "tool":"tenant_get_service_epg_alarm_summary",
        "inputs":{
          "tenant_name":"DC",
          "severity":"CRITICAL"
        }
      }' \
| jq
```

---

# 🧩 Monitoring Tools

---

## 8️⃣ monitor_get_platform_quick_status

Use-case:
> "Single view: EFA status + services + health endpoints."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{"tool":"monitor_get_platform_quick_status","inputs":{}}' \
| jq
```

---

# 🧩 System Tools

---

## 9️⃣ system_get_certificates_expiring_soon

Use-case:
> "Show certificates expiring in next 90 days."

```bash
curl -sS -X POST "$MCP" \
  -H "Content-Type: application/json" \
  -d '{
        "tool":"system_get_certificates_expiring_soon",
        "inputs":{
          "window_days":90
        }
      }' \
| jq
```

---

# 🛡 Safety Notes

- Server enforces `XCO_READ_ONLY=1`
- All Tier-2 tools are composite read-only
- No configuration-changing endpoints are exposed
- Inputs are validated before execution

---

# 🔌 MCP JSON-RPC Transport (`/mcp`)

Standard MCP clients (MCP Inspector, Claude Desktop, any JSON-RPC 2.0 MCP
client) connect directly to `POST /mcp` — `initialize` → `tools/list` →
`tools/call` — alongside the REST `/invoke` front door. Both route through the
same tool registry. Disable with `MCP_TRANSPORT_ENABLED=false`.

The `GET /tools` response carries an `X-Catalog-Version` header (the same value
is advertised in the MCP `initialize` handshake); cache it and skip
re-discovery while it is unchanged:

```bash
curl -sI http://<your_mcp_IP_addr>:8000/tools | grep -i x-catalog-version
# x-catalog-version: 53ca2727b2113ded
```

Point an MCP client (e.g. MCP Inspector) at `http://<your_mcp_IP_addr>:8000/mcp`.

---

# 🧠 AI Client Example

An AI MCP client should construct requests in this format:

```json
{
  "tool": "fabric_get_fabric_health_summary",
  "inputs": {
    "fabric_name": "DC"
  }
}
```

The AI should:
1. Determine correct tool
2. Extract required inputs
3. Send structured invoke request
4. Interpret structured JSON response

---

# 📌 Health Check (Optional)

If health endpoint exists:

```bash
curl http://<your_mcp_IP_addr>:8000/health
```

---

# 🎯 Response Structure

Typical response format:

```json
{
  "session_id": "...",
  "result": {
    "tool": "tool_name",
    "status": 200,
    "payload": {
      ...
    }
  }
}
```

---

# 🚀 Ready for Integration

These examples can be used for:

- Manual testing
- Postman collection import
- AI tool-calling agents
- UI integration validation
- CI/CD health checks


---
## RESTCONF examples (SLX / on-prem switch)

These examples use the **RESTCONF** toolpack against an SLX switch (tested with `10.13.9.66`).

### Prerequisites

1) Ensure your `.env` includes RESTCONF credentials:

```bash
RESTCONF_USERNAME=admin
RESTCONF_PASSWORD=password
RESTCONF_VERIFY_TLS=false
```

2) Restart the server if you changed `.env`:

```bash
# Docker
docker restart xco-mcp

# Or if running natively
sudo systemctl restart xco-mcp
```

3) Set shell variables used in the commands:

```bash
export MCP="http://127.0.0.1:8000"
export SW="10.13.9.66"
export U="${RESTCONF_USERNAME:-admin}"
export P="${RESTCONF_PASSWORD:-password}"
```

### Confirm tools are present

```bash
curl -sS "$MCP/tools" | jq '.[] | select(.category=="restconf") | .name'
```

### 1) System maintenance mode status

```bash
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_system_maintenance_status","inputs":{"switch_ip":"'$SW'"}}' \
| jq '.result.status, .result.payload.summary, .result.payload.items[0], .result.payload.warnings'
```

### 2) System maintenance rate monitoring (may return 204 / no content)

```bash
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_system_maintenance_rate_monitoring","inputs":{"switch_ip":"'$SW'","include_raw":true}}' \
| jq '.result.status, .result.payload.summary, .result.payload.items, .result.payload.raw_json, .result.payload.warnings'
```

### 3) List RESTCONF RPC operations supported by the switch

```bash
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_list_operations","inputs":{"switch_ip":"'$SW'"}}' \
| jq '.result.status, (.result.payload.items|length), .result.payload.items[0]'
```

### 4) VRF summary and IP interfaces

```bash
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_vrf_summary","inputs":{"switch_ip":"'$SW'"}}' \
| jq '.result.status, .result.payload.summary, (.result.payload.items|length), .result.payload.warnings'

curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_ip_interface","inputs":{"switch_ip":"'$SW'"}}' \
| jq '.result.status, (.result.payload.items|length), .result.payload.warnings'
```

### 5) Running config snapshot (vendor REST endpoint on SLX)

```bash
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_running_config","inputs":{"switch_ip":"'$SW'"}}' \
| jq '.result.status, .result.payload.summary, (.result.payload.items|length), .result.payload.warnings'
```

### 6) ARP table — single switch or multi-switch fan-out

`switch_ip` accepts a single string (original response shape) or a list of
strings (parallel fan-out: `meta.multi_switch=true`, `switch_level_data_by_ip`,
`errors_by_ip`; a per-switch failure is non-fatal).

```bash
# Single switch
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_arp_table","inputs":{"switch_ip":"'$SW'"}}' \
| jq '.result.payload.meta, (.result.payload.items|length)'

# Multiple switches in parallel
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_arp_table","inputs":{"switch_ip":["10.13.9.62","10.13.9.63"]}}' \
| jq '.result.payload.meta.multi_switch, .result.payload.switch_level_data_by_ip, .result.payload.errors_by_ip'
```


### 7) BGP summary — per switch or whole fabric

Reads **configured** BGP from the running-config (local AS, neighbors, peer
groups). `switch_ips` accepts a string or list; or pass `fabric_name` to
auto-discover member switches. (Operational session state isn't exposed via
RESTCONF on these SLX builds — this is the configured view.)

```bash
# One switch
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_bgp_summary","inputs":{"switch_ips":"'$SW'"}}' \
| jq '.result.payload.switches[0] | {local_as, neighbor_count, neighbors}'

# A whole fabric (auto-discovers member switches)
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_bgp_summary","inputs":{"fabric_name":"DC"}}' \
| jq '.result.payload.summary'
```
