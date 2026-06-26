# XCO MCP Server (ExtremeCloud Orchestrator MCP Gateway)

> **Community-ready beta read-only MCP server for Extreme XCO/IP Fabric visibility.**

A lightweight **FastAPI** server that exposes a **read-only, tool-based API** for **ExtremeCloud Orchestrator (XCO)**.
It provides:

- A **machine-readable tool registry** (`/tools`) and a single **invoke** endpoint (`/invoke`)
- **Tier-1 tools**: thin wrappers around individual XCO REST endpoints
- **Tier-2 tools**: read-only composites that orchestrate multiple Tier-1 calls and return a higher-level answer
- Built-in **safety/policy hooks**, **structured logging**, and **Prometheus metrics** for operational visibility

> This repo ships a **SAFE_READ-only** tool catalog — see
> [`docs/TOOL_CATALOG.md`](docs/TOOL_CATALOG.md) or `GET /tools` for the current set.
> **Tier-3/Tier-4 (mutating) toolpacks are not included** in this read-only community edition.

> ### ⚠️ WARNING: Network exposure
>
> This community edition exposes `/invoke` and `/mcp` **without built-in caller
> authentication or per-user authorization**.
>
> Run it only on **localhost or a trusted management network**. If exposing it
> beyond localhost, place it behind an authenticated reverse proxy, VPN, or other
> access-control layer.
>
> The server uses the XCO and/or RESTCONF credentials provided through environment
> variables, so **anyone who can reach the MCP server can invoke the exposed
> read-only tools** (including `restconf_get_running_config` — see the warning in
> the [RESTCONF toolpack](#restconf-toolpack-slx-switches) section).

---

## Table of Contents
- [What this is](#what-this-is)
- [Tier model](#tier-model)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Run the server](#run-the-server)
- [Use the server](#use-the-server)
- [Reference client (demo)](#reference-client-demo)
- [Documentation & Discovery](#documentation--discovery)
- [Adding new tools](#adding-new-tools)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)
- [Support](#support)

---

## What this is

This project turns XCO REST APIs into a **tool catalog** that can be discovered and invoked consistently:

- Clients fetch the catalog from `GET /tools`
- Clients invoke a tool via `POST /invoke` with `{"tool": "...", "inputs": {...}}`
- The server handles:
  - authentication/token refresh
  - context-safe param injection (IDs only)
  - consistent response envelopes (status/payload/meta)
  - safety/policy checks
  - observability (metrics + logs)

---

## Tier model

### Tier-1 (primitive)
**One tool ↔ one XCO endpoint.**

- Defined in `generated/mcp_tools.json`
- Executed directly via the transport layer
- Typical use: “GET switches”, “GET fabric topology”, “GET alarms”, etc.

### Tier-2 (composite, read-only)
**One tool ↔ multiple Tier-1 calls + post-processing.**

- Implemented as Python handlers in `tools/<category>/...`
- Registered in `mcp_runtime/registry.py`
- Receives:
  - `inputs` (user parameters)
  - `registry` (to look up Tier-1 specs)
  - `transport` (to call Tier-1 endpoints)
  - `context` (resolved context, if available)

### Tier-3 / Tier-4 (automation)
**Not included in this community edition.** This repository ships read-only
(`SAFE_READ`) tools only — there are no mutation/configuration tools. This
repository does not include tools intended to change device, switch, or fabric
state.

---

## Repository layout

High-level layout (may evolve):

- `api/` — FastAPI app + routes (`/invoke`, `/tools`, docs endpoints)
- `mcp_runtime/` — core runtime (registry, policy, transport, auth, sessions, metrics)
- `tools/` — tool implementations
  - `tools/<category>/...` — Tier-2 composite handlers (Tier-1 tools are described in JSON)
- `generated/` — generated artifacts
  - `generated/mcp_tools.json` — canonical tool catalog consumed by the server
- `docs/`
  - `docs/TOOL_CATALOG.md` — human-friendly catalog generated from `mcp_tools.json`
- `openapi/` — portable OpenAPI spec for `/invoke` (optional)
- `logs/` — local logs (if enabled / used by your deployment)

---

## Requirements

- **OS**: Linux/macOS (tested commonly on Ubuntu 22.04)
- **Python**: **3.10+**
- Network access from this server to your XCO instance (HTTPS/443 by default)

Python libraries (minimum):
- `fastapi`
- `uvicorn`
- `requests`
- `python-dotenv`
- `prometheus-client`
- `markdown` (optional; enables rendered HTML tool catalog)


---

## Installation

```bash
# 1) Clone
git clone https://github.com/YuryOstrovsky/xco-mcp-community-server.git
cd xco-mcp-community-server

# 2) Create venv
python3 -m venv .venv
source .venv/bin/activate

# 3) Install deps
pip install --upgrade pip
pip install -r requirements.txt
```



---

## Configuration

Create a `.env` file in the repo root (same level as `api/`, `mcp_runtime/`, etc).

Example :

```
XCO_HOST=<IP_ADDR/FQDN>
XCO_USERNAME=<your_XCO_username>
XCO_PASSWORD=<your_XCO_password>
XCO_VERIFY_TLS=false

# SAFETY: explicit read-only safety marker (this edition ships no mutation tools)
XCO_READ_ONLY=1

# Networking
XCO_TIMEOUT_SECONDS=20
```

### Environment variable reference

- `XCO_HOST` (**required**) — XCO IP/DNS (used to build `https://<host>:443/...`)
- `XCO_USERNAME` / `XCO_PASSWORD` (**required**) — credentials used to obtain a bearer token
- `XCO_VERIFY_TLS` (default: `false`) — set `true` if you want certificate verification
- `XCO_TIMEOUT_SECONDS` (default: `20`) — HTTP request timeout
- `XCO_READ_ONLY` (recommended: `1`) — explicit **read-only safety marker**. The real protection is that this edition ships **no mutation tools**; do not treat this flag (or the server) as an authentication/authorization boundary.


---

## Run the server

From the repo root:

```bash
source .venv/bin/activate
python api/run.py
```

The server listens on:

- `http://0.0.0.0:8000` (default)

---

## Use the server

### List tools

```bash
curl -sS http://127.0.0.1:8000/tools | jq
```

### Invoke a tool

```bash
curl -sS -X POST http://127.0.0.1:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool":"fabric_get_fabrics","inputs":{}}' | jq
```

> Tip: set a shell variable:
>
> ```bash
> export MCP="http://127.0.0.1:8000/invoke"
> curl -sS -X POST "$MCP" -H "Content-Type: application/json" -d '{"tool":"inventory_getswitches","inputs":{}}' | jq
> ```

---

## Reference client (demo)

A separate **demo client** — a natural-language web console + AI agent driven by
this server's tools — lives in a sibling repo:

**[xco-mcp-community-client-demo](https://github.com/YuryOstrovsky/xco-mcp-community-client-demo)**

It exists **only as a reference / example** for people who want to see the
server driven end-to-end without building their own UI or AI agent. **You do not
need it to use this server** — any standard MCP client (MCP Inspector, Claude
Desktop, or your own agent) works against `POST /invoke` or the `/mcp` transport.
Treat the demo as illustrative, not a product, and not a required component.

## Documentation & Discovery

### Human-friendly tool catalog
- **Rendered HTML:** `http://<your_mcp_IP_addr>:8000/docs/tools/html`
- **Raw Markdown:** `http://<your_mcp_IP_addr>:8000/docs/tools`
- **Repo file:** `docs/TOOL_CATALOG.md`

### API / Swagger-style docs
- **FastAPI Swagger UI (canonical):** `http://<your_mcp_IP_addr>:8000/docs`
- **FastAPI OpenAPI JSON:** `http://<your_mcp_IP_addr>:8000/openapi.json`

### Tool discovery (machine-readable)
- **Tools list (JSON):** `http://<your_mcp_IP_addr>:8000/tools`

### Health & readiness
- **Health:** `http://<your_mcp_IP_addr>:8000/health`
- **Readiness:** `http://<your_mcp_IP_addr>:8000/ready`
- **Metrics (Prometheus):** `http://<your_mcp_IP_addr>:8000/metrics`

### Optional standalone OpenAPI for /invoke (portable spec)
- **YAML (served):** `http://<your_mcp_IP_addr>:8000/openapi/mcp-invoke.yaml`
- **Repo file:** `openapi/mcp-server/openapi_mcp_invoke.yaml`

### Optional extra UIs
- **Custom Swagger UI (loads the YAML above):** `http://<your_mcp_IP_addr>:8000/swagger`
- **ReDoc:** `http://<your_mcp_IP_addr>:8000/redoc`

---

## Adding new tools

### Add a Tier-1 tool (primitive)
Tier-1 tools are described in JSON (not Python handlers):

1. Add/modify the tool entry in `generated/mcp_tools.json`
2. Allow tool in `tier1_tools.py` catalog
3. Regenerate the human catalog (optional): `docs/TOOL_CATALOG.md`
4. Restart the server

> If you’re using the generator pipeline (`tools/parse_openapi.py`, `tools/resolve_endpoints.py`, etc.),
> keep those outputs under `generated/` and commit the final `generated/mcp_tools.json`.

### Add a Tier-2 tool (composite)
1. Create the handler file under `tools/<category>/<tool_name>.py`
2. Import and register it in `mcp_runtime/registry.py` and add handler
3. Add a matching tool spec entry in `generated/mcp_tools.json`
   - Tag it as Tier-2 (e.g., include `tier2` in `tags`)
   - Keep policy as `SAFE_READ` unless you are intentionally adding mutations
4. Restart the server and test via `POST /invoke`

Tier-2 handlers are invoked with:
- `inputs` — validated user inputs
- `registry` — access to tool definitions
- `transport` — to call Tier-1 endpoints
- `context` — resolved context (if available)

---

## Troubleshooting

- **401 / auth issues**: verify `XCO_USERNAME`, `XCO_PASSWORD`, and that XCO is reachable from this host.
- **TLS problems**: if you use internal/self-signed certs, keep `XCO_VERIFY_TLS=false`.
- **Timeouts**: increase `XCO_TIMEOUT_SECONDS` for large inventories.
- **Missing rendered HTML for tool catalog**: install `markdown`:
  ```bash
  pip install markdown
  ```

---

## Security notes

- **No caller authentication.** `/invoke` and `/mcp` have no built-in
  authentication or per-user authorization (see the network-exposure warning near
  the top). Run on localhost or a trusted network, or front it with an
  authenticated reverse proxy/VPN.
- **Read-only by construction.** This edition ships only `SAFE_READ` tools; there
  are no mutation/configuration tools. `XCO_READ_ONLY=1` is an explicit safety
  marker, **not** an authorization boundary.
- **Sensitive output.** `restconf_get_running_config` returns real switch
  configuration that may contain secrets (usernames, SNMP communities, AAA keys,
  certificates) — see its warning in the [RESTCONF toolpack](#restconf-toolpack-slx-switches)
  section. Output handling is the operator's responsibility.
- The server uses the XCO/RESTCONF credentials from your environment, so anyone
  who can reach it can invoke every exposed read-only tool.

---
## RESTCONF toolpack (SLX switches)

The server includes a set of **Tier-2 RESTCONF** tools for interrogating SLX switches (tested with SLX9150).

### RESTCONF configuration (.env)

Add the following to your `.env` (use your own switch credentials):

```bash
RESTCONF_USERNAME=<restconf-username>
RESTCONF_PASSWORD=<restconf-password>
RESTCONF_VERIFY_TLS=false
```

Restart the service after changing `.env`:

```bash
sudo systemctl restart xco-mcp
```

### RESTCONF Tier-2 tools available

| Tool | What it does |
|---|---|
| `restconf_show_firmware_version` | Query SLX switch via RESTCONF to retrieve OS version, firmware build, uptime, CPU and memory info. |
| `restconf_get_interface_detail` | Retrieve detailed interface information including status and counters from the switch. |
| `restconf_list_operations` | List all RESTCONF RPC operations supported by the switch. |
| `restconf_get_lldp_neighbor_detail` | Retrieve LLDP neighbor details to understand connected devices. |
| `restconf_get_port_statistics_summary` | Summarize port traffic statistics and errors across interfaces. |
| `restconf_get_media_detail` | Retrieve physical media/transceiver details for switch ports. |
| `restconf_get_arp_table` | Retrieve the ARP table entries from the switch. |
| `restconf_get_clock` | Retrieve system clock/time information from the switch. |
| `restconf_get_vlan_brief` | Retrieve VLAN summary information configured on the switch. |
| `restconf_get_vrf_summary` | Retrieve VRF configuration and summary information. |
| `restconf_get_ip_interface` | Retrieve IP interface configuration and status details. |
| `restconf_get_running_config` | Retrieve running configuration directly from the switch via RESTCONF. |
| `restconf_get_system_maintenance_status` | Retrieve system maintenance mode status and stage information. |
| `restconf_get_system_maintenance_rate_monitoring` | Retrieve maintenance rate monitoring configuration/status (may return 204 if disabled). |

> ### ⚠️ WARNING: `restconf_get_running_config`
>
> `restconf_get_running_config` returns the switch **running configuration as
> reported by the device** — the real output, unredacted.
>
> Although this is a read-only operation, running configuration may contain
> **sensitive information** such as usernames, SNMP communities,
> AAA/TACACS/RADIUS settings, keys, certificates, pre-shared secrets, or other
> operational details.
>
> Use this tool only when you are **authorized to view the full switch
> configuration**. Output handling, storage, sharing, and redaction are the
> responsibility of the operator/community user.

### Example invoke

```bash
export MCP="http://127.0.0.1:8000"
curl -sS -X POST "$MCP/invoke" -H "Content-Type: application/json" \
  -d '{"tool":"restconf_get_system_maintenance_status","inputs":{"switch_ip":"10.13.9.66"}}' \
| jq '.result.status, .result.payload.summary'
```

## Testing

Two layers (see [CONTRIBUTING.md](CONTRIBUTING.md)):

- **Unit tests (offline, run in CI):** validate the catalog, registry,
  catalog-version hash, payload normalizer, and HTTP surface — no XCO needed.
  ```bash
  pip install pytest
  pytest -q
  ```
- **Smoke tests (live release gate):** `smoke-test/smoke_tier2_{a..e}.py` exercise
  real tools against a running server + reachable XCO. Not run in CI.

GitHub Actions ([.github/workflows/lint-test.yml](.github/workflows/lint-test.yml))
runs flake8 + pytest + a Docker build on every push and PR.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). This edition is **read-only**; please keep
new tools `SAFE_READ`.

## Support

This is a **community** project, provided **as-is, with no warranty and no
official support**. It is **not** supported by **Extreme Networks GTAC**,
Extreme professional services, or any Extreme support channel — please do **not**
open GTAC cases or expect vendor assistance for it. The same applies to the
[reference client demo](#reference-client-demo).

Help is **best-effort and community-driven**: use the repo's
[GitHub Issues](https://github.com/YuryOstrovsky/xco-mcp-community-server/issues)
and [Discussions](https://github.com/YuryOstrovsky/xco-mcp-community-server/discussions).
For vulnerabilities, see [SECURITY.md](SECURITY.md).

## Versioning & compatibility

- **API version** — every HTTP response carries an `X-API-Version` header (`v1`).
- **Catalog version** — `GET /tools` returns an `X-Catalog-Version` header and
  the MCP `initialize` handshake advertises the same `catalog_version`. It is a
  stable hash of tool names + input schemas + risk, so a client can detect when
  the tool surface changed and skip re-discovery when it hasn't.
- **Releases** follow [Semantic Versioning](https://semver.org); changes are
  tracked in [CHANGELOG.md](CHANGELOG.md). Tools are **additive** — existing tool
  names and input fields are not removed or repurposed within a major version;
  new optional fields and tools may be added.

## License

Licensed under the [Apache License 2.0](LICENSE).
