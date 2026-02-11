# XCO MCP Server (ExtremeCloud Orchestrator MCP Gateway)

A lightweight **FastAPI** server that exposes a **read-only, tool-based API** for **ExtremeCloud Orchestrator (XCO)**.
It provides:

- A **machine-readable tool registry** (`/tools`) and a single **invoke** endpoint (`/invoke`)
- **Tier-1 tools**: thin wrappers around individual XCO REST endpoints
- **Tier-2 tools**: read-only composites that orchestrate multiple Tier-1 calls and return a higher-level answer
- Built-in **safety/policy hooks**, **structured logging**, and **Prometheus metrics** for production-style operations

> This repo currently ships a **SAFE_READ-only** tool catalog (**250 tools**: tier1=213, tier2=37, generated on 2026-02-11).  
> The runtime also contains scaffolding for future higher-level automation (planner/workflow + mutation ledger),
> but **Tier-3/Tier-4 toolpacks are not included** in this repo.

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
- [Documentation & Discovery](#documentation--discovery)
- [Adding new tools](#adding-new-tools)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)

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
Not shipped as tools in this repo today.  
However, the runtime includes **scaffolding** for future automation (workflow/planner modules and mutation ledger/registry),
so the project can grow into higher tiers if/when you add mutation tools and policy rules.

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
git clone <your_repo_url>
cd xco-mcp-server

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

# SAFETY: enforce read-only at MCP layer (recommended)
XCO_READ_ONLY=1

# Networking
XCO_TIMEOUT_SECONDS=20
```

### Environment variable reference

- `XCO_HOST` (**required**) — XCO IP/DNS (used to build `https://<host>:443/...`)
- `XCO_USERNAME` / `XCO_PASSWORD` (**required**) — credentials used to obtain a bearer token
- `XCO_VERIFY_TLS` (default: `false`) — set `true` if you want certificate verification
- `XCO_TIMEOUT_SECONDS` (default: `20`) — HTTP request timeout
- `XCO_READ_ONLY` (recommended: `1`) — **guardrail flag**; this repo ships only `SAFE_READ` tools by default


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

- This repo currently ships only `SAFE_READ` tools. If you introduce write tools:
  - tighten policy checks (`mcp_runtime/policy.py`)
  - use the mutation registry/ledger for rollbacks/auditing
  - consider running behind a reverse proxy and restricting access by network/IP
