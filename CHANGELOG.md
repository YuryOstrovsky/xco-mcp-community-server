# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **MCP JSON-RPC transport** at `POST /mcp` (Streamable HTTP) — `initialize` /
  `tools/list` / `tools/call` — so standard MCP clients (MCP Inspector, Claude
  Desktop) connect with no shim, alongside the REST `POST /invoke` front door.
  Env-gated via `MCP_TRANSPORT_ENABLED` (default on).
- **`X-Catalog-Version`** header on `GET /tools` and an advertised
  `catalog_version` in the MCP `initialize` capabilities, so clients can
  short-circuit re-discovery when the catalog is unchanged.
- **Discovery tools** (`SAFE_READ`): `inventory_list_device_ids`,
  `tenant_list_ids`, `fabric_get_fabric_names` — paired ID listings in clean
  snake_case for the ID-required inventory/tenant/fabric tools.
- **ARP multi-switch fan-out** — `restconf_get_arp_table` accepts `switch_ip` as
  a string (single switch) or a list (parallel multi-switch fan-out).
- Community packaging & process: `LICENSE` (Apache 2.0), `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `pyproject.toml`, an offline `pytest`
  suite, and a GitHub Actions CI workflow (flake8 + pytest + Docker build).

### Changed
- **RESTCONF client now sends JSON RPC bodies** instead of XML for arp, clock,
  vlan-brief, lldp, media, firmware-version, and interface-detail — the target
  SLX firmware rejects XML bodies (`400 "Bad JSON character: <"`). This restores
  end-to-end function for that whole tool class.
- **LLDP** (`restconf_get_lldp_neighbor_detail`) now populates
  `remote_management` and `remote_capabilities` (previously hardcoded empty).
- Dependency security bumps: `starlette 1.3.1`, `fastapi 0.137.1`,
  `cryptography 46.0.7`, `urllib3 2.7.0`, `requests 2.34.2`, `idna 3.15`,
  `python-multipart 0.0.28`, `python-dotenv 1.2.2`.
- Rate limiter: stale-key garbage collection + `429` responses now carry
  `Retry-After` and a JSON body; added a `mcp_rate_limit_hits_total` metric.
- Catalog input-schema corrections (fabric topology `fabric_name`+`site`;
  `device_ips`/`host_ips`/`device_id` required where XCO requires them);
  normalized to `ensure_ascii=True`; de-duplicated `inventory_switch_inventory_info`.
- Dockerfile runs as a non-root user.

### Fixed
- `restconf/tools.py`: defined `_deep_find_any` (used in the clock-parser
  fallback but previously undefined — a latent `NameError`), caught by the new
  flake8 CI gate.
- `.gitignore`: removed a bare `test*` rule that silently ignored `tests/` and
  `test_*.py`, hiding any unit-test suite from the repo.

## [1.0.0]
- Initial community edition: read-only MCP server for XCO + SLX RESTCONF, Tier-1
  and Tier-2 tools, Prometheus metrics, health/ready endpoints, Docker support,
  and the `smoke-test/` integration suite.
