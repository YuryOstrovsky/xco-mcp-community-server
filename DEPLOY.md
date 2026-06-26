# XCO MCP Server (Community) — Deployment Guide

A **read-only** Model Context Protocol server for ExtremeCloud Orchestrator
(XCO) and SLX RESTCONF. This guide covers production-style deployment via Docker
(recommended) and from source.

- Two front doors, same registry: REST `POST /invoke` and the MCP JSON-RPC
  transport at `POST /mcp` (for MCP Inspector / Claude Desktop / any MCP client).
- All tools are `SAFE_READ`; the server makes no config changes.

## Prerequisites

- Docker 20.10+ (or Python 3.10/3.11 for the from-source path) on an **x86-64**
  host.
- Network reachability from the host to your **XCO controller** and, for the
  `restconf_*` tools, to the **SLX switches**.
- XCO API credentials and (for RESTCONF tools) per-switch RESTCONF credentials.

## Quick start (Docker)

### 1. Load the image

```bash
docker load -i xco-mcp-community-1.0.0.tar.gz
docker images xco-mcp-community
```

(Or build it yourself: `docker build -t xco-mcp-community:1.0.0 .`)

### 2. Create the environment file

The image contains **no credentials** — supply them at runtime. Pick a working
directory on the **host** (e.g. `~/xco-mcp/`) and create a `.env` file **there**.
The `.env` is read by the Docker CLI on the host at launch time (via
`--env-file .env`, or Compose's `env_file:`) and injected as environment
variables into the container — it is **not** copied into the image and does
**not** go in any path inside the container.

> The path passed to `--env-file` / `env_file:` is resolved **relative to the
> directory you run `docker run` / `docker compose` from**. Run the commands in
> steps 3–4 from that same directory (where your `.env` lives). With Compose,
> keep `.env` next to `docker-compose.yml`.

If you cloned the repo, copy the template: `cp .env.example .env`. If you only
have the image tarball (no repo), just create `.env` with these keys:

```bash
# XCO controller (required)
XCO_HOST=10.0.0.10
XCO_USERNAME=changeme
XCO_PASSWORD=changeme
XCO_VERIFY_TLS=false
XCO_READ_ONLY=1
XCO_TIMEOUT_SECONDS=20

# Per-switch SLX RESTCONF credentials (required for restconf_* tools)
RESTCONF_USERNAME=admin
RESTCONF_PASSWORD=changeme
RESTCONF_VERIFY_TLS=false

# Optional
# MCP_TRANSPORT_ENABLED=true   # mount /mcp (default on)
# MCP_RATE_LIMIT_RPM=60        # per-IP request limit
# CORS_ORIGINS=                # comma-separated allowed origins (empty = none)
```

> ⚠️ Keep `XCO_READ_ONLY=1`. Never commit a real `.env`. Use the exact key names
> above (`XCO_PASSWORD` / `RESTCONF_PASSWORD`, not `*_PASS`).

### 3. Run

```bash
docker run -d --name xco-mcp --restart unless-stopped \
  --env-file .env -p 8000:8000 \
  xco-mcp-community:1.0.0
```

Or with Docker Compose:

```yaml
# docker-compose.yml
services:
  xco-mcp:
    image: xco-mcp-community:1.0.0
    env_file: .env
    ports: ["8000:8000"]
    restart: unless-stopped
```

```bash
docker compose up -d
```

### 4. Verify

```bash
curl localhost:8000/health      # {"status":"ok",...}
curl localhost:8000/ready       # {"status":"ready","checks":{...,"xco":true}}
curl -sI localhost:8000/tools | grep -i x-catalog-version
curl -s -X POST localhost:8000/invoke -H 'Content-Type: application/json' \
  -d '{"tool":"fabric_get_fabric_names","inputs":{}}'
```

`/ready` returning `"xco":true` confirms the container can reach XCO with the
supplied credentials.

## From source (no Docker)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then edit
.venv/bin/python api/run.py      # serves on :8000
```

## MCP JSON-RPC transport (`/mcp`)

Standard MCP clients connect to `http://<host>:8000/mcp` (Streamable HTTP,
JSON-RPC 2.0: `initialize` → `tools/list` → `tools/call`) — no shim required,
running alongside `POST /invoke`. The `initialize` handshake advertises a
`catalog_version` capability matching the `X-Catalog-Version` header on
`GET /tools`, so a client can skip re-discovery when the tool surface is
unchanged. Disable with `MCP_TRANSPORT_ENABLED=false`.

## Reverse proxy & TLS

The server speaks plain HTTP and performs **no authentication** (community
edition). Do **not** expose it directly to untrusted networks. Terminate TLS and
add access control with a reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name xco-mcp.example.com;
    ssl_certificate     /etc/ssl/certs/xco-mcp.crt;
    ssl_certificate_key /etc/ssl/private/xco-mcp.key;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Restrict access to a trusted management network and/or add auth at the proxy.

## Monitoring & health

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness (always 200 when the process is up). |
| `GET /ready` | Readiness — includes an XCO connectivity check. |
| `GET /metrics` | Prometheus metrics. |

Useful metrics: `mcp_invoke_total`, `mcp_invoke_failure_total`,
`mcp_invoke_latency_seconds`, `mcp_invoke_status_total`,
`mcp_rate_limit_hits_total`. The image ships a Docker `HEALTHCHECK` hitting
`/health`.

## Rate limiting

A per-IP sliding-window limiter is on by default (`MCP_RATE_LIMIT_RPM`, default
60). Over the limit returns HTTP **429** with a `Retry-After` header and a JSON
`{detail, error_id}` body. Raise it for bulk/automation clients or place the
limit at your proxy.

## Logs

```bash
docker logs -f xco-mcp          # container logs (stdout)
docker logs --tail 200 xco-mcp
```

Credentials are redacted from logs. SAFE_READ policy decisions log at DEBUG to
keep `/invoke` hot-path volume down.

## Upgrade

```bash
docker load -i xco-mcp-community-<new>.tar.gz
docker rm -f xco-mcp
docker run -d --name xco-mcp --restart unless-stopped \
  --env-file .env -p 8000:8000 xco-mcp-community:<new>
```

There is no persistent state to migrate — the catalog ships in the image and all
config is environment-driven.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `/ready` shows `"xco":false` | Wrong `XCO_HOST`/credentials, or no network route to XCO. |
| Error shows a host like `10.9.140.10%20%20` / `Failed to resolve …%20` | Trailing whitespace in a `.env` value (`%20` = a space). Docker `--env-file` keeps it. Run `sed -i 's/[[:space:]]*$//' .env` and recreate the container. |
| `401` from tools | Check `XCO_USERNAME` / `XCO_PASSWORD` and that the user has API access. |
| `restconf_*` tools error | Verify `RESTCONF_USERNAME` / `RESTCONF_PASSWORD` and switch reachability. |
| `429 Too Many Requests` | Rate limit hit — raise `MCP_RATE_LIMIT_RPM` or back off (`Retry-After`). |
| Container won't start | `docker logs xco-mcp`; confirm the host is x86-64 and `.env` is valid. |

See also: [README.md](README.md), [README.docker.md](README.docker.md), and the
in-repo User Guide / Operator Notes.
