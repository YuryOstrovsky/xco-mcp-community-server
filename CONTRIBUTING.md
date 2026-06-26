# Contributing

Thanks for your interest in the XCO MCP Server (community edition)! This is a
**read-only** MCP server for ExtremeCloud Orchestrator (XCO) and SLX RESTCONF.
This guide covers how to set up, run, test, and add a tool.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating you agree to uphold it.

## Setup

```bash
git clone https://github.com/YuryOstrovsky/xco-mcp-community-server.git
cd xco-mcp-community-server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# dev tooling (tests + lint):
.venv/bin/pip install -e ".[dev]"   # or: pip install pytest flake8
```

Configuration is via environment variables loaded from `.env` (which is **not**
committed — see `.env` keys below):

| Variable | Purpose |
|---|---|
| `XCO_HOST` / `XCO_USERNAME` / `XCO_PASS` | XCO controller endpoint + credentials |
| `XCO_VERIFY_TLS` | Verify the XCO TLS cert (default off for lab) |
| `XCO_READ_ONLY` | Enforce read-only at the MCP layer (keep `1`) |
| `RESTCONF_USERNAME` / `RESTCONF_PASS` | Per-switch SLX RESTCONF credentials |
| `MCP_TRANSPORT_ENABLED` | Mount the `/mcp` JSON-RPC transport (default on) |
| `MCP_RATE_LIMIT_RPM` | Per-IP rate limit (default 60) |

## Run

```bash
.venv/bin/python api/run.py        # serves on :8000
curl http://localhost:8000/health  # liveness
curl http://localhost:8000/tools   # served catalog (+ X-Catalog-Version header)
```

Standard MCP clients (MCP Inspector, Claude Desktop) connect to the JSON-RPC
transport at `POST /mcp` — alongside the REST `POST /invoke` front door.

## Test

Two layers:

- **Unit tests (offline, no XCO):** `pytest` — validate the catalog, registry,
  catalog-version hash, payload normalizer, and HTTP surface. These run in CI.
  ```bash
  .venv/bin/pytest -q
  ```
- **Smoke tests (live, require a running server + reachable XCO):** the
  `smoke-test/smoke_tier2_{a..e}.py` batches exercise real tools end-to-end.
  They are the **release gate** and are not run in CI (they need a live backend).
  ```bash
  .venv/bin/python smoke-test/smoke_tier2_a.py --url http://localhost:8000
  ```

## Adding a tool

The registry (`mcp_runtime/registry.py`) is the single source of truth. To add a
**Tier-2 composite**:

1. Write the handler in `tools/<area>/<name>.py` with the signature
   `def my_tool(*, inputs, registry, transport, context, **kwargs) -> dict`,
   returning `{"status": <int>, "payload": <data>}`.
2. Add a catalog entry to `generated/mcp_tools.json` (`name`, `description`,
   `category`, `method: "COMPOSITE"`, `auth`, `input_schema`, `policy`, `tags`,
   `capabilities`). Keep the file **2-space indent, `ensure_ascii=True`,
   trailing newline**.
3. Register it in `registry.py` (import + `self.handlers["my_tool"] = my_tool`).
4. Run `pytest` (catalog/registry validation) and add or extend a smoke case.

## Safety model

This edition is **read-only**: every tool is `SAFE_READ`. Do **not** add
mutating tools, auth/scope enforcement, or destructive RESTCONF/SLX operations —
those live in the enterprise edition and are intentionally out of scope here.

## Pull requests

- Keep changes focused; match the surrounding code style.
- `pytest` and `flake8` must pass (CI enforces both).
- Update the catalog and docs when you add or change a tool.
- Describe what you changed and how you verified it (smoke output helps).
