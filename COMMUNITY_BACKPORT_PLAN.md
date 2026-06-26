# Community-Grade MCP Server — Back-port Plan (enterprise → community)

**Goal:** bring the Tier-1/2 fixes + Brendan "base" design from the enterprise repo
into this community edition, **without** any enterprise feature.
**Source:** `/home/user01/xco-mcp-enterprise-server` (evolving). **Target:** this repo
(`~/xco-mcp-community-server`, frozen `7b485fd` 2026-04-09, 267 tools, smoke-test based).

## ✅ PROGRESS (2026-06-26) — START THE NEXT SESSION HERE
**DONE + verified (compile + import + functional; NOT live-smoke-tested):**
- **P1 spine:** ✅ 1.1 normalizer · ✅ 1.2 human_hint · ✅ 1.3 inner-status unwrap · ✅ 1.4 fabric-alias · ✅ 1.6 SecurityHeaders · ✅ 1.7 exception-handlers+error_id · ✅ 1.8 `_safe_log`. (⬜ only 1.5 SAFE_READ log-demotion left — lowest value.)
- **P2 tool-code:** ✅ device_health_rollup (+ unreachable_devices + software_version_mismatch) · ✅ active_alarms_top · ✅ recent_events_filtered.
- **P2 catalog:** ✅ 3 policy fixes (firmware_download_* `requires_confirmation` true→false).
- New files: `mcp_runtime/payload_normalize.py`, `mcp_runtime/error_classify.py`, this plan.

**NEXT (needs the community server RUNNING vs XCO + the smoke harness):**
1. **LLDP fix** — surgical edit in `restconf/tools.py` (`restconf_get_lldp_neighbor_detail`: `remote_management`/`remote_capabilities` hardcoded `None`/`[]`). The one P2 tool fix not yet done (it's inside the big multi-tool file).
2. **The 9 input_schema catalog fixes** — esp. the ones making `device_ips`/`host_ips`/`device_id` **required** + arp `switch_ip` `oneOf` → **update `smoke-test/smoke_tier2_b.py`+`_e.py` call sites in the SAME change** + dedupe `inventory_switch_inventory_info` (appears twice).
3. **P3** catalog_version → **P4** `/mcp` transport (auth-stripped) → **P5** deps.
> After each phase: `python3 smoke-test/smoke_tier2_{a..e}.py --url <community-server>` and re-baseline `results_*.json`.

## Ground rules (scope)
- **STRICTLY EXCLUDE — never port:** OAuth2 / auth middleware / API-keys / JWT / scope
  enforcement / `required_scope`; the plan pipeline (`/plans`, workflow, undo, mutation
  registry, job store, ledger/webhooks); RoCE / nuclear_clean / factory_default / TPVM
  / QoS / hardware-profile; multi-site (`site_registry`); response cache; Vault.
- **The two repos share NO git history** → every change is a **manual file-level port**,
  not a cherry-pick. Verify each against the community file before editing.
- **Gate of record:** community's `smoke-test/smoke_tier2_{a..e}.py` must stay green.
  No pytest suite here — smoke-test is the release gate.
- **Catalog format:** 2-space indent, trailing newline. ⚠ community currently uses
  `ensure_ascii=False` (2 `→` chars in the arp description); enterprise uses
  `ensure_ascii=True`. Pick `ensure_ascii=True` going forward for clean diffs.
- **Already in community (do NOT re-port):** CORS, request-logging + body-size
  middleware, single IP-keyed rate limiter, `/metrics` `/health` `/ready`, the
  exception→HTTP mapping, `mcp==1.26.0` + `anyio==4.12.1` (so the MCP transport needs
  **zero new deps**).

---

## PHASE 1 — Self-contained, auth-free, lowest risk (DO FIRST)

| # | Item | Source | Action |
|---|---|---|---|
| 1.1 | **Payload normalizer** | `mcp_runtime/payload_normalize.py` (171 lines, imports only `os`/`re`) — community lacks it | **Copy verbatim.** Wire `normalize_result(result)` into the community `/invoke` return (community `api/app.py` sync return). Gate `MCP_NORMALIZE_PAYLOADS` (default on). |
| 1.2 | **Human-readable error hints** | `mcp_runtime/error_classify.py` (self-contained) + `server.py:625-632` | Copy `error_classify.py` verbatim; in community `server.py` HTTP-path result add `if not 2xx: result["human_hint"]=format_step_error(...)`. |
| 1.3 | **Inner-status unwrap for Tier-2 composites** | `server.py:508-512` | Community hardcodes `status:200` for all Tier-2 handlers; let a composite return its own `{status,payload}`. |
| 1.4 | **Fabric alias → canonical key** | `server.py:467-470` | Add the `fabric_name`/`fabric` → `fabric-name` alias loop (community has `fabric_param` in its catalog; fixes the 404 class). |
| 1.5 | **SAFE_READ log demotion** | `server.py:323-335` (policy half only) | `DEBUG if risk==SAFE_READ else INFO` — log-volume hygiene. Skip the *site* half. |
| 1.6 | **SecurityHeadersMiddleware + `X-API-Version`** | `app.py:226-239` | Copy verbatim (pure response headers). |
| 1.7 | **Global exception handlers + `error_id`** | `app.py:203-219` | Copy verbatim (`JSONResponse`, `uuid`). Preserves `detail`, adds `error_id`. |
| 1.8 | **`_safe_log` control-char sanitizer** | `app.py:30-35,275` | Copy `_safe_log`+regex, wrap `request.url.path` in community's request-log middleware. **Drop** the `client_id`/`oauth2_client_id` field. |

---

## PHASE 2 — Tier-1/2 tool correctness fixes (CATALOG + CODE) — highest user value

**Tool-code fixes** (port the function bodies; registrations are identical):

| Pri | Tool / file | Bug fixed |
|---|---|---|
| **P0** | `inventory_get_device_health_rollup` (+ `unreachable_devices.py`, `software_version_mismatch.py`) | **N_fabrics × N_switches double-count.** Fetch switches **once**, dedupe by id, resolve true fabric membership, add "unassigned" group. (~174-line diff in rollup; helpers already in-file.) |
| **P0** | `restconf_get_lldp_neighbor_detail` (`restconf/tools.py`) | `remote_management`/`remote_capabilities` were hardcoded `None`/`[]` → **silent LLDP TLV data loss.** Wire to `_pick(r,"remote-management-address")` + capability split. (~22 lines; `_pick` already present.) |
| **P1** | `faultmanager_get_active_alarms_top` | **alarms 8-vs-26** — `top[]` are groups; consumers read `len(top)` as count. Add `instance_count`, `total_alarm_instances`, `group_count`, `result_is_grouped`, `top_resources_objects`; default `sample_per_group` 3→25. **Additive only.** |
| **P1** | `notification_get_recent_events_filtered` | Always send `status` param (XCO 404s without it); treat 404 as **empty**, not "unsupported" (kills false warning). Defaults `last_n` 50→20, `limit_per_source` 10→5. |
| **P2** | `restconf_get_arp_table` (capability, not bug) | Multi-switch fan-out: `switch_ip` accepts string **or** list. Back-compat preserved; add `_arp_multi_switch_fanout` + `_ARP_MAX_PARALLEL=16`. |

**Catalog edits (`generated/mcp_tools.json`):**
- **`input_schema` corrections (9):** `fabric_get_{overlay,physical,underlay}_topology` (`fabric-name`→`fabric_name` + new `site`); `inventory_get_interfaces` (`device_ips` **required**); `inventory_get_firmware_hosts` (`host_ips` **required**); `inventory_switch_inventory_info` (add required `device_id`); `restconf_get_arp_table` (`switch_ip` oneOf string|array); `fault_get_active_alarms_top` (`sample_per_group` 3→25, range 0..200); `notification_get_recent_events_filtered` (default tune).
- **`policy` corrections (3):** `inventory_get_firmware_download_history_status`, `…_operation_history`, `…_status` — flip wrong `requires_confirmation:true` → `false` (they're SAFE_READ).
- **Cleanups:** **dedupe `inventory_switch_inventory_info`** (it appears twice); normalize to `ensure_ascii=True`.
- **DO NOT port:** the `required_scope` field (auth — differs on all 266 shared tools) or the "⚠ REQUIRES PLAN APPROVAL" description banners (enterprise-only).

> ⚠ **CROSS-DEPENDENCY (must do together):** the schema fixes make `device_ips`/`host_ips`/`device_id` **required** and widen `arp switch_ip`. **Audit `smoke-test/smoke_tier2_b.py` + `smoke_tier2_e.py` call sites** for these 4 tools and add the new required inputs *in the same change*, or smoke will FAIL 400/404. Re-baseline `smoke-test/results_*.json` afterward.

---

## PHASE 3 — `catalog_version` + `X-Catalog-Version`
- Lift `compute_catalog_version()` (sha256 over `name|input_schema|risk`, 16 hex) from
  enterprise `api/mcp_transport.py:190-201` into a **standalone** `mcp_runtime/catalog_version.py`
  (so `app.py` doesn't depend on the SDK transport just for a hash).
- Add a process-cached `_catalog_version()` and set `response.headers["X-Catalog-Version"]`
  on community's `GET /tools`. Purely additive header.

---

## PHASE 4 — MCP JSON-RPC transport `/mcp` (biggest; DO LAST)
Copy `api/mcp_transport.py`, **strip all auth**, add a lifespan to community `app.py`,
env-gate the mount (`MCP_TRANSPORT_ENABLED`, default on). SDK already pinned.

**Auth code to REMOVE (per enterprise line refs):**
- `_token_claims`/`_caller_id` contextvars (`:49-52`) — delete.
- `_dispatch_tool` scope block (`:284,287-311`) — remove `enforce_scope`, `get_tool_permission_store`, claims/caller reads; also drop the probe-dispatch block (`:291-301`, RoCE/xco_health excluded) → leave a plain `if name not in reg.tools: raise ToolNotFound`.
- `handle_asgi` auth threading (`:392-411`) → simplify to `await sessions.handle_request(...)` + the 503 guard.
- `_invoke_with_optional_progress` (`:356-357`) — drop `caller` param + `caller_id=` kwarg (community `invoke()` has no `caller_id`).
- Reword the `instructions` string (drop "plan approval"/"authorization").
- Keep `_tool_to_mcp`, `_estimated_seconds`, `_OUTPUT_ENVELOPE_SCHEMA`, the progress
  heartbeat (default off), and `_advertise_catalog_version`.
- **New app wiring:** community `FastAPI(...)` has no `lifespan=`; add one to run the
  `StreamableHTTPSessionManager`. Mount per enterprise `app.py:452-462` + `:173-175`.
- Depends on Phase 1.1 (`normalize_result`) being in first.

---

## PHASE 5 — deps / build / optional discovery tools / rate-limit polish
- **requirements.txt bumps (security):** `starlette 0.50.0→1.3.1` **and** `fastapi 0.128.2→0.137.1` (move together — test!); `idna 3.11→3.15`, `requests 2.32.5→2.34.2`, `urllib3 2.6.3→2.7.0`, `cryptography 46.0.4→46.0.7`, `python-multipart→0.0.28`, `python-dotenv→1.2.2`. **Do NOT** bump/add `PyJWT`, `hvac`, `paramiko`, `PyYAML`.
- **Dockerfile (optional):** adopt non-root `USER` + HEALTHCHECK; keep community's simple
  single-stage `python:3.11-slim` (don't import the enterprise multi-stage/Vault/DB env).
- **Optional new SAFE_READ discovery tools** (each needs its `tools/…` module ported +
  catalog entry; verify no enterprise import): `inventory_list_device_ids`, `tenant_list_ids`,
  `fabric_get_fabric_names`. (Pair the first two with the device-id-required inventory tools.)
- **Rate-limit polish (auth-free):** stale-key GC (`app.py:579-580,624-628`) to stop the
  `_rate_store` leak; JSON-429 + `Retry-After` (`:840-846`). If porting the
  `MCP_RATE_LIMIT_HITS` metric, **add that Counter to `mcp_runtime/metrics.py`** (community lacks it) or keep the `.inc()` in try/except. Keep community's **IP-only** rate-limit key — never re-introduce the oauth/api-key key derivation.

---

## Explicitly LEAVE BEHIND (auth / enterprise / plan / RoCE)
AuthMiddleware + OAuth routers + `/oauth/token`/`/authorize`/`/register`/`.well-known`;
`enforce_scope` / `caller_id` / `token_claims`; `method=="PLAN"` routing + plan/job/ledger/
webhook routes + stale-plan reaper; `site_registry` + `/sites`; response cache + `X-Cache`;
direct-probe `run_xco_probe` dispatch; all `restconf_slx_*`/`restconf_xco_*` RoCE/QoS/nuclear/
factory tools; the transport `body=`/`timeout=`/`has_body` GET-passthrough split (a
**prerequisite** the GET-passthrough improvement needs — note, don't port as part of core).

---

## Execution order & verification
1. **Phase 1** (self-contained copies) → `python -c "import api.app, mcp_runtime.server"` clean.
2. **Phase 2** (tool fixes + catalog + **smoke call-site updates together**) → run all 5 smoke files, re-baseline.
3. **Phase 3** (catalog_version) → `curl -sI /tools | grep X-Catalog-Version`.
4. **Phase 4** (transport) → MCP Inspector `initialize`→`tools/list`→`tools/call` on a SAFE_READ tool.
5. **Phase 5** (deps/build/optional) → re-run smoke after the starlette/fastapi bump.

**Run smoke-test:** `cd ~/xco-mcp-community-server && python3 smoke-test/smoke_tier2_a.py --url http://localhost:8000` (then `_b _c _d _e`). No runner script exists — invoke each.

---
*Generated 2026-06-26 from a 4-way subsystem diff of the two repos. Each phase is
independent; Phase 1 + Phase 2-P0 give the most value for least risk.*
