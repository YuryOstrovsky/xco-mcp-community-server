# MCP Tool Catalog

_Generated from `mcp_tools.json` on 2026-06-26_

## Summary
- Total tools: **269**
- By tier: **tier1**=216, **tier2**=53
- By risk: **SAFE_READ**=269

## Categories
- **auth**: 19
- **fabric**: 29
- **faultmanager**: 9
- **hyperv**: 5
- **inventory**: 92
- **licensing**: 2
- **monitor**: 26
- **notification**: 5
- **rbac**: 8
- **snmp**: 4
- **system**: 14
- **tenant**: 32
- **vcenter**: 9
- **restconf**: 15

---

## auth

### `auth_get_active_host_users`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/users/host-active`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the host users and the active session details

- Tags: `read`, `tier1`

### `auth_get_active_user_by_type`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/user/active`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the active users details by authentication type

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `auth_type` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `auth_get_all_token_expiry`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/token/expiry/all`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get expiry times for all tokens

- Tags: `read`, `auth`, `tier1`

### `auth_get_api_key`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/token/apikey`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **True**

> Get key for XCO client

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `clientId` | `string` | yes | `` |  |

- Tags: `read`, `tier1`, `sensitive`

### `auth_get_auth_preferences`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/authenticator/preference`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get authentication preferences

- Tags: `read`, `tier1`

### `auth_get_authentication_summary_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/authenticator/summary`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get authentication summary details

- Tags: `read`, `tier1`

### `auth_get_client_by_name`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/client`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Fetch API client details by name

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |

- Tags: `read`, `auth`, `tier1`

### `auth_get_clients`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/clientlist`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Fetch all registered API clients

- Tags: `read`, `auth`, `tier1`

### `auth_get_exec_logs`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/execution-logs`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get Execution log list with pagination

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `search` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `auth_get_execution`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/execution`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get detailed execution output by execution ID

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` | Execution ID |

- Tags: `read`, `auth`, `execution`, `tier1`

### `auth_get_executions`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the list of all previous executions, optionally filtered by status

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `10` | Limit the number of executions returned |
| `status` | `string` | no | `all` | Filter executions by status (failed \| succeeded \| all) |

- Tags: `read`, `auth`, `execution`, `tier2`

### `auth_get_host_users`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/users/host`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get host users.

- Tags: `read`, `tier1`

### `auth_get_ldap_details`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/authenticator/ldap`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Fetch registered LDAP server details

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `auth_get_ldap_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/authenticator/ldaplist`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all LDAP connection details

- Tags: `read`, `tier1`

### `auth_get_role_mappings`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/rolemappings`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Fetch role mapping details

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `auth_type` | `string` | no | `` |  |
| `auth_identifier` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `auth_get_tacacs_by_host`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/authenticator/tacacs`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Fetch TACACS  server details of a sepcific host or all hosts

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `auth_get_token_expiry`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/token/expiry`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get token expiry time for a given token type

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `type` | `string` | yes | `` | Type of the token (e.g. ACCESS) |

- Tags: `read`, `auth`, `tier1`

### `auth_get_user_by_name`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/user`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Fetch all users details or specific user detail by name

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `user_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `auth_validate_token`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/auth/token/validate`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Validate if the current authentication token is valid

- Tags: `read`, `auth`, `tier0`

## fabric

### `fabric_get_config_show`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/config`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getConfigShow

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabricName` | `string` | yes | `` |  |
| `role` | `string` | yes | `` |  |
| `ip` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `fabric_get_devices`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/devices`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all devices in the specified fabric (by fabric name)

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric-name` | `string` | yes | `` |  |

- Tags: `read`, `fabric`, `devices`, `tier1`

### `fabric_get_event_history_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/eventhistories`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getEventHistoryList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `execution_uuid` | `string` | no | `` |  |
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `fabric_get_execution_get`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/execution`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getExecutionDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `fabric_get_execution_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the list of all previous fabric executions

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `10` | Limit the number of executions returned |
| `status` | `string` | no | `all` | Filter executions by status (failed \| succeeded \| all) |

- Tags: `read`, `tier1`

### `fabric_get_fabric`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/fabric`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getFabric

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `detail` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `fabric_get_fabric_efa_command_list`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Return the EFA command/script lines (from XCO runningConfig) correlated to a specific fabric name

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` | Fabric name (e.g. DC) |
| `max_items` | `integer` | no | `200` | Max matched command lines to return (default 200) |
| `include_full_text` | `boolean` | no | `False` | Include full extracted script text (default false) |
| `include_raw` | `boolean` | no | `False` | Include raw Tier-1 outputs (default false) |

- Tags: `read`, `tier2`, `fabric`, `efa`

### `fabric_get_fabric_errors`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/errors`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> FabricErrors

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric-name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `fabric_get_fabric_errors_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Fabric errors summary. Calls Tier-1 fabric_get_fabric_errors (and optionally fabric_get_fabrics_errors + fabric_get_fabric_health) and returns an actionable summary (counts, top error types, affected devices whe…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` | Fabric name (required). |
| `include_health` | `boolean` | no | `True` | If true, also fetch fabric health (fabric_get_fabric_health) to include device health counts for context. |
| `include_global` | `boolean` | no | `False` | If true, also fetch global fabrics errors (fabric_get_fabrics_errors) for context. |
| `max_error_items` | `integer` | no | `50` | Maximum number of error items to return if the endpoint provides a list. |
| `include_raw` | `boolean` | no | `False` | If true, include raw Tier-1 payloads under raw.{...}. Output becomes large. |

- Tags: `read`, `tier2`, `fabric`, `errors`, `summary`

### `fabric_get_fabric_execution_last_failed`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Find the most recent FAILED fabric execution for a given fabric name (best-effort match), and return a compact actionable summary. Uses Tier-1 fabric_get_execution_list and optionally fabric_get_execution_get.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` | Fabric name (e.g., DC). |
| `limit` | `integer` | no | `50` | How many failed executions to request from Tier-1 list before local filtering. |
| `include_detail` | `boolean` | no | `True` | If true, fetch execution detail for the matched execution (Tier-1 fabric_get_execution_get). |
| `include_raw` | `boolean` | no | `False` | If true, include raw Tier-1 payloads (can be large). |

- Tags: `read`, `fabric`, `execution`, `tier2`

### `fabric_get_fabric_execution_recent`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: recent fabric executions (per-fabric). Fetches execution list, correlates executions to a fabric name/id using best-effort heuristics, optionally fetches execution detail for the most recent matched executions, …

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` | Fabric name. Required. |
| `limit` | `integer` | no | `50` | How many executions to request from Tier-1 execution list. |
| `status` | `string` | no | `all` | Status filter passed to execution list: failed \| succeeded \| all. |
| `max_items` | `integer` | no | `10` | Maximum matched executions returned in the output list. |
| `include_detail` | `boolean` | no | `False` | If true, fetch execution detail for up to detail_limit matched executions. |
| `detail_limit` | `integer` | no | `3` | Max number of matched executions to fetch detail for when include_detail=true. |
| `include_raw` | `boolean` | no | `False` | Include raw Tier-1 payloads under raw. |

- Tags: `read`, `tier2`, `fabric`, `executions`, `recent`

### `fabric_get_fabric_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/fabric-health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getFabricHealth

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `fabric_get_fabric_health_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: fabric health summary (global + per-fabric). Combines fabrics-health, fabric-health, service health, and optional errors into an actionable summary with next steps.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | no | `` | Fabric name. If omitted, runs in global mode. |
| `include_global` | `boolean` | no | `True` | Include global fabrics list (fabrics-health). |
| `include_service_health` | `boolean` | no | `True` | Include fabric service health (fabric_get_health / service health). |
| `include_errors` | `boolean` | no | `False` | Include errors sections using fabrics-errors and fabric-errors (with fallback). |
| `expand_unhealthy` | `boolean` | no | `False` | In global mode, expand first unhealthy fabrics into partial summaries. |
| `max_expand` | `integer` | no | `3` |  |
| `max_fabrics` | `integer` | no | `200` |  |
| `max_unhealthy_devices` | `integer` | no | `50` |  |
| `max_error_items` | `integer` | no | `50` |  |
| `include_raw` | `boolean` | no | `False` | Include raw Tier-1 per-fabric health payload as health_raw. |

- Tags: `read`, `tier2`, `fabric`, `health`, `summary`

### `fabric_get_fabric_health_timeline`
- Tier: **tier2**  
- Method: ****  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: fabric health timeline (per-fabric). Builds a chronological view by combining current fabric health, event history, and execution history. Correlation between eventhistories.execution_uuid and executions is BEST…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` | Fabric name. Required. |
| `device_ip` | `string` | no | `` | Optional device IP filter for event history (if supported by backend; backend may return empty payload). |
| `include_global` | `boolean` | no | `True` | Include global fabrics list (fabrics-health) and validate the fabric name exists. |
| `include_service_health` | `boolean` | no | `True` | Include fabric service health (fabric_get_health / service health). |
| `include_health_headline` | `boolean` | no | `True` | Include current fabric health headline (fabric-health), with fallback to global list. |
| `include_executions` | `boolean` | no | `True` | Include execution list. Note: executions endpoint may not support name filtering; tool fetches system-wide executions and filters locally when possible. |
| `include_exec_details` | `boolean` | no | `False` | Optionally fetch execution detail per execution id/uuid (best-effort, only if endpoint exists). Limited by max_exec_details. |
| `since` | `string` | no | `` | Optional ISO timestamp (UTC). Locally filter events/executions with time >= since. |
| `until` | `string` | no | `` | Optional ISO timestamp (UTC). Locally filter events/executions with time <= until. |
| `window_hours` | `integer` | no | `168` | Convenience time window (hours). Used only if since/until are not provided (now - window_hours .. now). |
| `limit_events` | `integer` | no | `200` | Backend limit for event history fetch (global fetch, then local filter to this fabric). |
| `max_events` | `integer` | no | `200` | Maximum number of filtered events returned for this fabric after local filtering/sorting. |
| `max_timeline_items` | `integer` | no | `50` | Maximum number of grouped execution timeline entries returned. |
| `exec_limit` | `integer` | no | `100` | Backend limit for execution list fetch. |
| `exec_status` | `string` | no | `all` | Execution status selector. Use 'all' for broad history (matches your working call). |
| `max_exec_details` | `integer` | no | `10` | Maximum execution detail records to fetch when include_exec_details=true. |
| `include_raw` | `boolean` | no | `False` | Include raw Tier-1 payloads as events_raw / executions_raw / health_raw when available. |

- Tags: `read`, `tier2`, `fabric`, `health`, `timeline`, `events`, `executions`

### `fabric_get_fabric_names`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2 SAFE_READ composite — lightweight fabric discovery: list fabric NAMES (and ids) in clean snake_case (fabric_name, fabric_id), ready to feed into ID-dependent tools like fabric_get_overlay_topology(fabric_name=...…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `include_raw` | `boolean` | no | `False` | Include the raw fabric_get_fabrics tier-1 response. |

- Tags: `read`, `fabric`, `discovery`, `tier2`

### `fabric_get_fabric_overview`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Compact fabric overview (headline + optional errors/devices summary). Set include_raw=true to include raw Tier-1 payloads (large).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` | Optional: filter to a single fabric by name |
| `include_health` | `boolean` | no | `True` | If true, enrich output with fabric health data (via Tier-1). |
| `include_errors` | `boolean` | no | `True` | If true, include fabric errors data when available (via Tier-1). |
| `include_devices` | `boolean` | no | `False` | If true, include per-fabric devices_summary (counts by role/firmware/config state). |
| `include_raw` | `boolean` | no | `False` | If true, include raw Tier-1 payloads (summary_raw/health_raw/devices_raw). Output becomes large. |

- Tags: `read`, `fabric`, `overview`, `tier2`

### `fabric_get_fabric_setting`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/setting`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getFabricSetting

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `fabric_get_fabric_validation_report`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Pre-change readiness / audit report for a fabric. Correlates health, errors, locks, and validation endpoints into a PASS/WARN/FAIL verdict with next actions.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | no | `` | Fabric name (preferred). |
| `fabric_name` | `string` | no | `` | Alias for name. |
| `include_health` | `boolean` | no | `True` | If true, include fabric health headline + device health counts. |
| `include_errors` | `boolean` | no | `True` | If true, include fabric errors (and fail verdict if any errors exist). |
| `include_locks` | `boolean` | no | `True` | If true, include service locks (warn verdict if any locks exist). |
| `include_validate_fabric` | `boolean` | no | `True` | If true, call fabric_validate_fabric and include its findings. |
| `include_topology_validation` | `boolean` | no | `False` | If true, call fabric_validate_physical_topology and include its findings. |
| `max_error_items` | `integer` | no | `50` |  |
| `max_lock_items` | `integer` | no | `50` |  |
| `max_validation_items` | `integer` | no | `50` |  |
| `include_raw` | `boolean` | no | `False` | If true, include raw Tier-1 responses under payload.raw (large). |

- Tags: `read`, `fabric`, `validation`, `diagnostic`, `tier2`

### `fabric_get_fabrics`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/fabrics`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all fabrics with configuration, status, and device summary

- Tags: `read`, `fabric`, `tier1`

### `fabric_get_fabrics_errors`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/fabrics/errors`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all fabrics errors configured in the application

- Tags: `read`, `fabric`, `errors`, `tier1`

### `fabric_get_fabrics_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/fabrics-health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get health status of all fabrics

- Tags: `read`, `fabric`, `health`, `tier1`

### `fabric_get_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getHealth

- Tags: `read`, `tier1`

### `fabric_get_overlay_topology`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/topology/overlay`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get fabric overlay topology for a specified fabric

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | yes | `` | Fabric whose OVERLAY topology to fetch. Snake `fabric_name` or hyphenated `fabric-name` both accepted. |
| `site` | `string` | no | `` | Site id when a fabric name exists on multiple sites (e.g. lab-a vs lab-b). |

- Tags: `read`, `fabric`, `topology`, `overlay`, `tier1`

### `fabric_get_physical_topology`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/topology/physical`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get fabric physical topology for a specified fabric

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | yes | `` | Fabric whose PHYSICAL topology (real per-port switch↔switch links) to fetch. Snake `fabric_name` or hyphenated `fabric-name` both accepted. |
| `site` | `string` | no | `` | Site id when a fabric name exists on multiple sites (e.g. lab-a vs lab-b). |

- Tags: `read`, `fabric`, `topology`, `tier1`

### `fabric_get_running_config`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/runningConfig`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the running configuration CLI commands for the fabric

- Tags: `read`, `fabric`, `running-config`, `tier1`

### `fabric_get_service_locks`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/debug/service/lock`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get fabric service lock statuses

- Tags: `read`, `fabric`, `debug`, `lock`, `tier1`

### `fabric_get_underlay_topology`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/topology/underlay`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get fabric underlay topology for a specified fabric

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | yes | `` | Fabric whose UNDERLAY topology to fetch. Snake `fabric_name` or hyphenated `fabric-name` both accepted. |
| `site` | `string` | no | `` | Site id when a fabric name exists on multiple sites (e.g. lab-a vs lab-b). |

- Tags: `read`, `fabric`, `topology`, `underlay`, `tier1`

### `fabric_validate_fabric`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/fabric/validate`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> validateFabric

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric-name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `fabric_validate_physical_topology`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `/v1/fabric/topology/validate/physical`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Validate fabric physical topology for a specified fabric

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric-name` | `string` | yes | `` |  |

- Tags: `read`, `fabric`, `topology`, `validate`, `physical`, `tier1`

## faultmanager

### `fault_get_active_alarms_top`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2fault_get_active_alarms_top`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2 (read-only, v1): Show top ACTIVE alarms by severity and the resources they attach to. Composite uses ONLY existing tier-1 tools: faultmanager_get_alarm_history (active/unacked/uncleared/closed filters) and option…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `top_n` | `integer` | no | `10` | How many alarm groups to return (1..100). |
| `max_records` | `integer` | no | `500` | Max active alarm records to process from tier-1 (1..5000). |
| `severity_min` | `string` | no | `` | Optional minimum severity (Critical>Major>Minor>Warning>Info). |
| `query` | `string` | no | `` | Optional substring search across alarm text fields (e.g., 'certificate', 'bgp'). |
| `alarm_type` | `string` | no | `` | Optional alarm_type filter passed to faultmanager_get_alarm_history (and inventory enrichment). |
| `resource` | `string` | no | `` | Optional exact resource filter passed to faultmanager_get_alarm_history. |
| `resource_query` | `string` | no | `` | Optional substring filter applied locally to resource (useful when resource needs partial match). |
| `include_inventory` | `boolean` | no | `False` | If true, calls faultmanager_get_alarm_inventory(detail=true) to enrich alarms with catalog details. |
| `include_samples` | `boolean` | no | `True` | If true, include up to sample_per_group alarm instances per top group. |
| `sample_per_group` | `integer` | no | `25` | How many sample instances to return per group (0..200). 0 = counts only. |
| `include_raw` | `boolean` | no | `False` | If true, include tier-1 raw responses (debug). |

- Tags: `read`, `tier2`

### `fault_get_alarm_details_with_context`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2fault_get_alarm_details_with_context`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2 (read-only): Explain an alarm (what it is, what it impacts, and related recent context). Composite uses ONLY existing tier-1 tools: faultmanager_get_alarm_history (instances + resource/severity), faultmanager_get…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | no | `` | Alarm name (preferred). Example: CertificateExpiration |
| `alarm_id` | `integer` | no | `` | Alarm id (if known). |
| `resource` | `string` | no | `` | Exact resource string to scope to (optional). |
| `active_only` | `boolean` | no | `True` | If true, fetches active alarms (unacked=true, acked=false, cleared=false, closed=false). |
| `window_hours` | `integer` | no | `24` | How far back to look for related alerts (and optional tenant events). |
| `max_instances` | `integer` | no | `20` | Max alarm instances to return. |
| `alert_limit` | `integer` | no | `100` | Max related alerts to fetch per selected resource. |
| `top_resources` | `integer` | no | `3` | How many top resources to include context for. |
| `include_inventory` | `boolean` | no | `True` | If true, includes faultmanager_get_alarm_inventory(detail=true) explanation. |
| `include_alerts` | `boolean` | no | `True` | If true, includes related alerts from faultmanager_get_alert_history. |
| `include_health` | `boolean` | no | `True` | If true, includes monitor_get_health_detail for selected resources. |
| `include_tenant_events` | `boolean` | no | `True` | If true, and device_ip can be derived from resource, includes tenant_get_event_history_list(device_ip). |
| `include_raw` | `boolean` | no | `False` | If true, includes tier-1 raw outputs for debugging. |

- Tags: `read`, `tier2`

### `fault_get_fabric_health_related_alerts`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2fault_get_fabric_health_related_alerts`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2 (read-only): Find alerts that indicate fabric health restored/degraded recently. Composite uses ONLY existing tier-1 tools: faultmanager_get_alert_history (filter by fabric resource + time window), fabric_get_fab…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | yes | `` | Fabric name (e.g. DC). Required. |
| `window_hours` | `integer` | no | `24` | Lookback window for alert history. |
| `max_records` | `integer` | no | `200` | Max alerts returned after filtering. |
| `alert_limit` | `integer` | no | `300` | Tier-1 fetch limit sent to faultmanager_get_alert_history. |
| `severity` | `string` | no | `` | Optional severity filter passed to Tier-1 (e.g. Critical, Major, Warning, Info). |
| `signal` | `string` | no | `` | Optional signal filter: 'restored' or 'degraded' (post-filter classification). |
| `include_other` | `boolean` | no | `False` | If true, include alerts that are fabric-scoped but not classified as restored/degraded. |
| `include_raw` | `boolean` | no | `False` | If true, include tier-1 raw outputs for debugging. |

- Tags: `read`, `tier2`

### `faultmanager_get_alarm_history`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/faultmanager/alarm/history`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get history of alarms generated by the system

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | no | `` |  |
| `alarm_id` | `integer` | no | `` |  |
| `alarm_type` | `string` | no | `` |  |
| `resource` | `string` | no | `` |  |
| `unacked` | `boolean` | no | `` |  |
| `acked` | `boolean` | no | `` |  |
| `cleared` | `boolean` | no | `` |  |
| `closed` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `faultmanager_get_alarm_inventory`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/faultmanager/alarm/inventory`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get inventory of all possible alarms

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `alarm_id` | `integer` | no | `` |  |
| `name` | `string` | no | `` |  |
| `resource` | `string` | no | `` |  |
| `alarm_type` | `string` | no | `` |  |
| `detail` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `faultmanager_get_alarm_summary`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/faultmanager/alarm/summary`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get summary of alarms grouped by severity

- Tags: `read`, `tier1`

### `faultmanager_get_alert_history`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/faultmanager/alert/history`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get history of alerts generated by the system

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `alert_id` | `integer` | no | `` |  |
| `severity` | `string` | no | `` |  |
| `resource` | `string` | no | `` |  |
| `limit` | `integer` | no | `` |  |
| `before_timestamp` | `string` | no | `` |  |
| `after_timestamp` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `faultmanager_get_alert_inventory`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/faultmanager/alert/inventory`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get inventory of all possible alerts

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `alert_id` | `integer` | no | `` |  |
| `resource` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `faultmanager_get_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/faultmanager/health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get health status of the Fault Manager service

- Tags: `read`, `tier1`

## hyperv

### `hyperv_get_executions`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/microsoft/hyperv/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get Hyper-V execution history

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | no | `` |  |
| `status` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `hyperv_get_physical_links`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/microsoft/hyperv/links/physical`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get physical NIC to switch links for Hyper-V

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |
| `hyperv_host` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `hyperv_get_servers`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/microsoft/hyperv`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get registered Hyper-V / SCVMM servers

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `hyperv_get_service_settings`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/microsoft/hyperv/settings`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get Hyper-V service settings

- Tags: `read`, `tier1`

### `hyperv_get_virtual_links`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/microsoft/hyperv/links/virtual`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get virtual NIC to logical network links for Hyper-V

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `hyperv_host` | `string` | no | `` |  |

- Tags: `read`, `tier1`

## inventory

### `inventory_get_aaa_config`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/aaa`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getAAAConfig

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_all_locations`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/locations`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Fetch locations details

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_bindings`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/policy/bindings`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getBindings

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | yes | `` |  |
| `name_of_instance` | `string` | yes | `` |  |
| `type_of_instance` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_bridge_domain`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/bridgedomain`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getBridgeDomain

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `bridge_domains` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_community_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/community-list`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getCommunityList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `communitylist_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_config_backup_detail`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/config-backup-detail`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getConfigBackupDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `cb_id` | `string` | yes | `` |  |
| `show_config` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_config_backup_historys`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/config-backups`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getConfigBackupHistorys

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_config_replay_detail`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/config-replay-detail`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getConfigReplayDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `cr_id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_config_replay_historys`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/config-replays`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getConfigReplayHistorys

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_adapter_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/debug/deviceadapterstatus`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get device adapter statuses

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |
| `fabric-all` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_certificates_expiry`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/certificate/expiry`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get Device Certificates Expiry

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |
| `fabric-all` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_details`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/device/discovery`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get device discovery interval time & device details

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` |  |
| `device_ips` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_health_rollup`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2inventory_get_device_health_rollup`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Roll up device health to explain which devices are driving fabric health (e.g., Red). Composite of monitor_get_health_inventory + fabric_get_fabrics_health + fabric_get_fabrics + inventory_getswitches.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` | Optional fabric name filter (e.g., DC). If omitted, scans all fabrics. |
| `group_by` | `string` | no | `fabric` |  |
| `min_severity` | `string` | no | `yellow` |  |
| `driver_limit` | `integer` | no | `10` | Max drivers (unhealthy devices) per group. |
| `include_healthy` | `boolean` | no | `False` | If true, includes green devices in lists (otherwise only unhealthy per min_severity). |
| `health_resource` | `string` | no | `inventory` | Resource string passed to monitor_get_health_inventory. If it returns empty/invalid, tool will try safe fallbacks. |
| `include_raw` | `boolean` | no | `False` |  |

- Tags: `read`, `tier2`, `inventory`, `health`, `rollup`

### `inventory_get_device_inventory_export`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/inventory-info-export`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **True**

> This API will export the device inventory information as a binary Excel file

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_id` | `integer` | yes | `` |  |

- Tags: `read`, `export`, `binary`, `tier2`

### `inventory_get_device_inventory_ports`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/inventory-info-ports`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> This API will return the device port inventory information

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_id` | `integer` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_inventory_structure`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/inventory-structure`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> This API will return the device inventory structure information based on the type

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_type` | `integer` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_state`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/device-current-state`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getDeviceState

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_tacacs_config`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/tacacs-config`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getDeviceTacacsConfig

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | yes | `` |  |
| `name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_tacacs_configs`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/tacacs`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getDeviceTacacsConfigs

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_device_timezone`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/timezone`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getDeviceTimezone

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_devices_lock_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/debug/deviceslock`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get devices lock statuses

- Tags: `read`, `tier1`

### `inventory_get_download_locations`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/locations-download`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **True**

> Download Locations in CSV file

- Tags: `read`, `tier1`, `sensitive`

### `inventory_get_drift_reconcile_detail`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/drift-reconcile-detail`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getDriftReconcileDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `dr_id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_drift_reconcile_historys`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/drift-reconciles`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getDriftReconcileHistorys

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_dsc_detail`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/device-state`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getDSCDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `dsc_id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_dsc_historys`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/dsc-history`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> GetDSCHistorys

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_evpn_instance`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/evpn`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getEVPNInstance

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_execution_get`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/execution`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getExecutionDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_execution_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getExecutionList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `` |  |
| `status` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_ext_community_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/extcommunity-list`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getExtCommunityList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `extcommunitylist_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_fabric_switches_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `{MCP_HOST}/invoke`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Summarize switches that belong to a specific fabric. Composite tool: validates fabric exists (fabric_get_fabrics), fetches switches from Inventory (inventory_getswitches) using fabric-id, and optionally enriches…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` | Fabric name (e.g. DC). Required. |
| `max_items` | `integer` | no | `200` | Max switches returned in signals.switches.items (after local truncation). |
| `include_per_switch_summary` | `boolean` | no | `False` | If true, fetch inventory summary-info for a limited number of switches (best-effort, requires device_id). |
| `per_switch_limit` | `integer` | no | `5` | How many switches to enrich with inventory_switch_inventory_summary_info when include_per_switch_summary=true. |
| `include_raw` | `boolean` | no | `False` | Include raw Tier-1 responses under raw (debug). |

- Tags: `read`, `tier2`, `composite`, `inventory`, `switches`, `fabric`

### `inventory_get_firmware_download_history_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/firmware-download/history`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> getFirmwareDownloadHistoryStatus

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` |  |
| `execution_id` | `string` | no | `` |  |
| `prepared_list_name` | `string` | no | `` |  |
| `device_ips` | `array` | no | `` |  |
| `device_type` | `string` | no | `` |  |
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |

- Tags: `read`, `tier1`, `sensitive`

### `inventory_get_firmware_download_operation_history`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/firmware-download/operational/history`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> getFirmwareDownloadOperationHistory

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` |  |
| `execution_id` | `string` | no | `` |  |
| `prepared_list_name` | `string` | no | `` |  |
| `device_ips` | `array` | no | `` |  |
| `device_type` | `string` | no | `` |  |
| `last_execution_history` | `boolean` | no | `` |  |
| `fwdl_task_id` | `array` | no | `` |  |
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |

- Tags: `read`, `tier1`, `sensitive`

### `inventory_get_firmware_download_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/firmware-download`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> getFirmwareDownloadStatus

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` |  |
| `execution_id` | `string` | no | `` |  |
| `prepared_list_name` | `string` | no | `` |  |
| `device_ips` | `array` | no | `` |  |
| `device_type` | `string` | no | `` |  |

- Tags: `read`, `tier1`, `sensitive`

### `inventory_get_firmware_host`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/firmware-host`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getFirmwareHost

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `ip_address` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_firmware_host_protocols`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/firmware-host/protocols`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getFirmwareHostProtocols

- Tags: `read`, `tier1`

### `inventory_get_firmware_hosts`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/firmware-hosts`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getFirmwareHosts

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_ips` | `array` | yes | `` | REQUIRED. List of firmware host IPs to look up. XCO returns 400 if omitted. |

- Tags: `read`, `tier1`

### `inventory_get_fwdl_in_progress_devices`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/debug/updatefwdlstatus`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get FWDL In progress devices

- Tags: `read`, `tier1`

### `inventory_get_getting_started`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/getting-started`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> This API will be called when very first time the user logs in

- Tags: `read`, `tier1`

### `inventory_get_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getHealth

- Tags: `read`, `tier1`

### `inventory_get_interfaces`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/interfaces`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getInterfaces

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | yes | `` | REQUIRED. List of switch management IP addresses to query interfaces for. XCO returns 404 if omitted. |
| `device_ids` | `array` | no | `` |  |
| `type` | `string` | yes | `` |  |
| `admin_state` | `string` | yes | `` |  |
| `rme` | `boolean` | no | `` |  |
| `oper_state` | `string` | yes | `` |  |
| `fabric_intf_role` | `string` | no | `` |  |
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_ip_prefix_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/ip-prefix-list`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getIPPrefixList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `prefixlist_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_key_value_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/keys`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getKeyValueList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `prefix` | `string` | no | `` |  |
| `decrypt` | `boolean` | no | `` |  |
| `limit` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_lif`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/lif`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getLIF

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_links`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/links`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getLinks

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `device_ids` | `array` | no | `` |  |
| `ids` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |
| `fabric_id` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_lldp_data`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/lldp_data`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getLldpData

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `remote_macs` | `array` | no | `` |  |
| `device_ips` | `array` | no | `` |  |
| `neighbor_type` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_mct_cluster_clients`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/mct/client`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getMCTClusterClients

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `client_ids` | `array` | no | `` |  |
| `cluster_id` | `integer` | no | `` |  |
| `ids` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_mct_cluster_configuration`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/mct/cluster`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getMCTClusterConfiguration

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `cluster_ids` | `array` | no | `` |  |
| `ids` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_mct_management_cluster`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/mct/management`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getMCTManagementCluster

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `node_ids` | `array` | no | `` |  |
| `ids` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_mirror_sessions`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/mirror-session`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getMirrorSessions

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_multi_tpvm_upgrade_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/tpvm-upgrade`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getMultiTpvmUpgradeStatus

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `ip_address` | `string` | no | `` |  |
| `execution_id` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_ntp_disable`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/ntp/disable`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getNtpDisable

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_ntp_servers`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/ntp/server`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getNtpServers

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_overlay_gateway`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/overlaygateway`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getOverlayGateway

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_policy`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/policy/policy`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> get

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `policy_type` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_port_channels`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/portchannels`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getPortChannels

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `device_ids` | `array` | no | `` |  |
| `po_numbers` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_prepared_switches`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/firmware-download/prepare`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **True**

> getPreparedSwitches

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |
| `prepared_list_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`, `sensitive`

### `inventory_get_pseudowire_profile`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/pwprofile`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getPseudowireProfile

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `pseudowire_profiles` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_rma_detail`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/rma-detail`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getRMADetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `rma_id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_rma_historys`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/rma-history`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getRMAHistorys

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_route_map`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/route-map`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getRouteMap

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `routemap_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_router_bgp`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/bgp`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the BGP configuration and operational summary for a device — local AS, router-id, peer groups, neighbors (remote-AS, BFD), and per-VRF address-family state. Target the device by management IP (device_ip) or device_i…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_router_pim`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/pim`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getRouterPim

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_running_config`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/runningConfig`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> GetRunningConfig

- Tags: `read`, `tier1`

### `inventory_get_secure_settings`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/securesettings`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSecureSettings

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_service_lock_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/servicelockstatus`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getServiceLockStatus

- Tags: `read`, `tier1`

### `inventory_get_snmp_communities`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/snmp/community`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSnmpCommunities

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_snmp_groups`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/snmp/group`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSnmpGroups

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_snmp_hosts`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/snmp/host`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSnmpHosts

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_snmp_use_vrfs`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/snmp/use-vrf`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSnmpUseVrfs

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_snmp_users`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/snmp/user`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSnmpUsers

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_snmp_views`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/snmp/view`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSnmpViews

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_software_version_mismatch`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2inventory_get_software_version_mismatch`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Scan switches per fabric and detect firmware/software version mismatches grouped by fabric/role/model/global. Uses fabric_get_fabrics + inventory_getswitches.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` | Optional fabric name filter (e.g., DC) |
| `group_by` | `string` | no | `fabric` |  |
| `include_outliers` | `boolean` | no | `True` |  |
| `outlier_limit` | `integer` | no | `20` |  |
| `min_group_size` | `integer` | no | `2` |  |
| `include_raw` | `boolean` | no | `False` |  |

- Tags: `read`, `tier2`, `inventory`, `switches`, `versions`

### `inventory_get_supported_device_timezones`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/timezone/debug-show`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSupportedDeviceTimezones

- Tags: `read`, `tier1`

### `inventory_get_switch_health_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switchhealth/status`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> switchHealthStatus

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `ip_address` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_switch_setting`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switchconfig/setting`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getSwitchSetting

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `ip_address` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_switches_widget_table`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> UI-ready switch inventory table (for MCP client widget). Composite: inventory_getswitches + optional per-switch health/status enrichment tool. Returns flat rows with fields matching widget columns (IP, Status, Name, Mod…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` | If provided, filters the resulting table to this fabric (when supported by underlying inventory tool). |
| `fabric_all` | `boolean` | no | `False` | If true, attempts to include devices across all fabrics (if supported by underlying tools). |
| `device_ips` | `array` | no | `` | Optional: restrict to specific device management IPs. |
| `device_ids` | `array` | no | `` | Optional: restrict to specific device IDs (preferred join key if available). |
| `include_status` | `boolean` | no | `True` | If true, enriches each row with Status via a secondary tool call (status_tool). |
| `status_tool` | `string` | no | `monitor_get_inventory_health_summary` | Name of an existing tool that can return per-device health/status keyed by device_id or ip. |
| `max_items` | `integer` | no | `200` | Maximum number of rows to return. |
| `include_raw` | `boolean` | no | `False` | If true, includes the raw inventory record per row (for debugging). |

- Tags: `read`, `inventory`, `switches`, `widget`, `tier2`, `table`

### `inventory_get_threshold_monitors`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/thresholdmonitor`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getThresholdMonitors

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_tpvm_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switch/tpvm/list`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getTpvmList

- Tags: `read`, `tier1`

### `inventory_get_tpvm_upgrade_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switch/tpvm-upgrade`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getTpvmUpgradeStatus

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `ip_address` | `string` | no | `` |  |
| `execution_id` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_tunnel`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/tunnel`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getTunnel

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `ids` | `array` | no | `` |  |
| `tunnel_numbers` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_unreachable_devices`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2inventory_get_unreachable_devices`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Show devices currently unreachable/down (best-effort last_seen/last_error) using inventory + faultmanager alarms.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric_name` | `string` | no | `` | Optional fabric name filter (e.g., DC). If omitted, scans all fabrics. |
| `include_alarms` | `boolean` | no | `False` | If true, include top alarm snippets per unreachable device. |
| `alarm_limit` | `integer` | no | `3` | Max alarm snippets per device when include_alarms=true (1..20). |
| `group_by` | `string` | no | `fabric` | Grouping for unreachable device rollups. |
| `unreachable_only` | `boolean` | no | `True` | If true, return only unreachable devices (default). If false, return all devices with reachability classification. |
| `include_raw` | `boolean` | no | `False` | If true, include tier-1 raw responses (debug). |

- Tags: `read`, `tier2`

### `inventory_get_v_es`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/veinterfaces`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVEs

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `device_ids` | `array` | no | `` |  |
| `ve_ids` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_value_for_key`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/keys/{name}`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get a specific key vale pair based on key_name.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `decrypt` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_vlan_ss`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/vlans`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVLANs

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `vlan_ids` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_vrf`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/vrf`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVRF

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `ids` | `array` | no | `` |  |
| `vrfs` | `array` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_get_vrrp`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/vrrp`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVRRP

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ip` | `string` | no | `` |  |
| `device_id` | `integer` | no | `` |  |
| `int_type` | `string` | no | `` |  |
| `int_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_getswitches`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get switches

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `fabric-id` | `string` | no | `` |  |
| `id` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_list_breakout_ports`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/interfaces/breakout`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> List Breakout Interface Port

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `inventory_list_device_ids`
- Tier: **tier1**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2 SAFE_READ composite — the PAIRED LIST for device-id-required inventory tools. Returns device_ids[] + devices[{device_id, ip, hostname}] in clean snake_case so a client can feed an id straight into device_id-requi…

- Tags: `read`, `inventory`, `discovery`, `ids`, `composite`

### `inventory_switch_inventory_info`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/inventory-info`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get hardware inventory information for a single switch

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `device_id` | `integer` | yes | `` | Switch device id (from inventory_getswitches or fabric switch lists) |

- Tags: `read`, `tier1`

### `inventory_switch_inventory_summary`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/inventory/switches/inventory-summary-info`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Returns summarized inventory information for switches (identity, role, model, serial, IP, health).

- Tags: `read`, `inventory`, `switch`, `tier1`

## licensing

### `licensing_get_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/licensing/health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get health status of the licensing service

- Tags: `read`, `tier1`, `health`

### `licensing_get_licenses`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/licensing/license`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Show all licenses added to XCO

- Tags: `read`, `tier1`

## monitor

### `monitor_get_all_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/all`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get complete monitoring status (services, nodes, pods, resources)

- Tags: `read`, `monitor`, `aggregate`, `tier1`

### `monitor_get_backup_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/backup`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get backup files list.

- Tags: `read`, `tier1`

### `monitor_get_certificate_expiry`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/certificate/expiry`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get expiry date of EFA certificates

- Tags: `read`, `tier1`

### `monitor_get_deployment_config`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/deployment`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get EFA deployment configuration

- Tags: `read`, `monitor`, `deployment`, `tier1`

### `monitor_get_efa_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/status/efa`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get EFA status.

- Tags: `read`, `tier1`

### `monitor_get_gluster_fs_info`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/status/glusterfs`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get GlusterFS information.

- Tags: `read`, `tier1`

### `monitor_get_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/healthmanager/health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getHealth

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `resource` | `string` | no | `` |  |
| `detail` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `monitor_get_health_detail`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/healthmanager/health/detail`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getHealthDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `resource` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `monitor_get_health_inventory`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/healthmanager/health/inventory`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getHealthInventory

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `resource` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `monitor_get_host_users`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/users/host`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get host users.

- Tags: `read`, `tier1`

### `monitor_get_k3s_nodes`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/k3s/nodes`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get K3s node information

- Tags: `read`, `monitor`, `k3s`, `nodes`, `tier1`

### `monitor_get_k3s_pods`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/k3s/pod`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get K3s pod monitoring information

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `namespace` | `string` | yes | `` |  |

- Tags: `read`, `monitor`, `k3s`, `pods`, `tier1`

### `monitor_get_k3s_resources`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/k3s/resources`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get K3s cluster resource usage

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `namespace` | `string` | yes | `` |  |

- Tags: `read`, `monitor`, `k3s`, `resources`, `tier1`

### `monitor_get_k3s_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/status/k3s`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get K3s monitoring status

- Tags: `read`, `monitor`, `k3s`, `tier1`

### `monitor_get_keep_alived_info`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/status/keepalived`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get Keepalived information.

- Tags: `read`, `tier1`

### `monitor_get_maria_db_info`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/status/mariadb`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get MariaDB information.

- Tags: `read`, `tier1`

### `monitor_get_platform_quick_status`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Single view platform status (EFA + services + health). Optionally fetch health detail for problematic resources. Set include_raw=true for Tier-1 evidence (large).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `include_efa` | `boolean` | no | `True` | If true, include EFA status (monitor_get_efa_status). |
| `include_services` | `boolean` | no | `True` | If true, include service status summary (monitor_get_service_status). |
| `include_health` | `boolean` | no | `True` | If true, include platform health summary (monitor_get_health). |
| `include_health_detail` | `boolean` | no | `False` | If true, fetch monitor_get_health_detail for selected resources (see detail_only_on_problem/max_detail). |
| `detail_only_on_problem` | `boolean` | no | `True` | If true, only fetch health detail for resources considered unhealthy/degraded. |
| `max_detail` | `integer` | no | `10` | Max number of resources to fetch health detail for. |
| `include_raw` | `boolean` | no | `False` | If true, include raw Tier-1 responses under tier1_raw (large). |

- Tags: `read`, `monitor`, `platform`, `status`, `tier2`

### `monitor_get_redeploy_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/redeploy/{redeployId}`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Redeploy status.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `redeployId` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `monitor_get_restore_history`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/restore-history`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Restore history.

- Tags: `read`, `tier1`

### `monitor_get_restore_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/restore/{restoreId}`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Restore status.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `restoreId` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `monitor_get_service_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/monitor/status`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get monitoring status of all services

- Tags: `read`, `monitor`, `tier1`

### `monitor_get_static_i_ps`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/mgmt/subinterface/staticips`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get static IPs.

- Tags: `read`, `tier1`

### `monitor_get_sub_interface`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/mgmt/subinterface`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get subinterface.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `monitor_get_support_save`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/supportsave`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get support.

- Tags: `read`, `tier1`

### `monitor_get_support_save_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/supportsavelist`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get support.

- Tags: `read`, `tier1`

### `monitor_get_virtual_route`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/mgmt/virtualroute`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get virtual route.

- Tags: `read`, `tier1`

## notification

### `notification_get_executions`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/notification/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get notification service execution list

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `10` | Limit the number of executions returned |
| `status` | `string` | no | `all` | Filter executions by status (failed \| succeeded \| all) |

- Tags: `read`, `notification`, `execution`, `disabled`, `tier1`

### `notification_get_last_failed_delivery_or_errors`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Find the most recent FAILED notification execution (notification pipeline issues). Uses Tier-1 notification_get_executions. If backend returns no failures, can optionally fallback to status=all and detect non-su…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `window_hours` | `integer` | no | `168` | Local time filter over execution start/end time (best-effort). 168h=7d. |
| `limit` | `integer` | no | `200` | How many executions to request from Tier-1 notification_get_executions before local filtering. |
| `status` | `string` | no | `failed` | Tier-1 status filter: failed \| succeeded \| all. |
| `query` | `string` | no | `` | Optional keyword search over command/parameters/status/user_name. |
| `max_items` | `integer` | no | `10` | Maximum number of recent failed executions returned under recent_failed. |
| `fallback_detect_non_success` | `boolean` | no | `True` | If Tier-1 status=failed returns none, optionally re-query status=all and detect non-success statuses locally. |
| `include_raw` | `boolean` | no | `False` | If true, include raw Tier-1 responses under tier1_raw (can be large). |

- Tags: `read`, `tier2`, `notification`, `executions`, `diagnostic`, `errors`

### `notification_get_recent_events_filtered`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get recent execution-derived events across services and filter by severity/type/resource/query (Tier-2 composite).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `sources` | `array` | no | `['system', 'fabric', 'tenant', 'inventory', 'snmp', 'auth', 'rbac']` | Which execution sources to query (uses existing Tier-1 execution tools). |
| `status` | `string` | no | `all` | Filter executions by status when supported (failed \| succeeded \| all). |
| `last_n` | `integer` | no | `20` | Return the last N events after filtering. |
| `limit_per_source` | `integer` | no | `5` | How many executions to pull per source before extracting events. Each unit makes one HTTP call to XCO, so keep low (3-5) for fast responses. |
| `severity_min` | `string` | no | `` | Minimum normalized severity (Info\|Warning\|Major\|Critical). |
| `event_type` | `string` | no | `` | Substring match against normalized event type. |
| `resource` | `string` | no | `` | Substring match against normalized resource. |
| `query` | `string` | no | `` | Substring match across type/resource/message. |
| `include_raw` | `boolean` | no | `False` | Include tier1_raw payloads for troubleshooting. |

- Tags: `read`, `tier2`, `notification`, `events`, `composite`

### `notification_get_subscriber`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/notification/subscribers/{id}`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get a notification subscriber by ID

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `integer` | yes | `` | Subscriber ID |

- Tags: `read`, `notification`, `subscriber`, `tier1`

### `notification_get_subscribers`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/notification/subscribers`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all notification subscribers

- Tags: `read`, `notification`, `subscriber`, `tier1`

## rbac

### `rbac_get_authorized_tenants`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/tenant/authorized-tenants`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get list of tenants authorized for a dynamic role

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `roles` | `array` | yes | `` |  |

- Tags: `read`, `tier1`

### `rbac_get_execution_detail`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/execution`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get detailed output of a specific RBAC execution

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `rbac_get_executions`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get list of previous RBAC executions

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `10` |  |
| `status` | `string` | no | `all` |  |

- Tags: `read`, `tier1`

### `rbac_get_role`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/role`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get specific role defined in EFA

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `role_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `rbac_get_roles`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/roles`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all roles defined in EFA

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `include_internal` | `boolean` | no | `` |  |

- Tags: `read`, `tier1`

### `rbac_get_user_permissions`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/permissions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get user view permissions

- Tags: `read`, `tier1`

### `rbac_validate_authorization`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/isauthorized`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Validate authorization for one or more roles against a method and path

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `roles` | `array` | yes | `` |  |
| `method` | `string` | yes | `` |  |
| `path` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `rbac_validate_tenant_authorization`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/rbac/tenant/isauthorized`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Validate tenant authorization for one or more roles

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `roles` | `array` | yes | `` |  |
| `tenant-name` | `string` | no | `` |  |
| `method` | `string` | yes | `` |  |
| `path` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

## snmp

### `snmp_get_execution`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/snmp/execution`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get detailed SNMP execution output by execution ID

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` | Execution ID |

- Tags: `read`, `snmp`, `execution`, `disabled`, `tier1`

### `snmp_get_executions`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/snmp/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get list of SNMP execution records

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `10` | Limit the number of executions returned |
| `status` | `string` | no | `all` | Filter executions by status (failed \| succeeded \| all) |

- Tags: `read`, `snmp`, `execution`, `disabled`, `tier1`

### `snmp_get_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/snmp/health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get health status of the SNMP service

- Tags: `read`, `snmp`, `health`, `tier1`

### `snmp_get_trap_subscribers`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/snmp/subscribers`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all SNMP trap subscribers

- Tags: `read`, `snmp`, `subscriber`, `tier1`

## system

### `system_get_certificate_alarm_context`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Any current alarms about certificate expiry and which cert is it? Composite of faultmanager alarms filtered to certificate/expiry + certificate expiry metadata (monitor + device).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `active_only` | `boolean` | no | `True` |  |
| `severity_min` | `string` | no | `` |  |
| `require_expiry_terms` | `boolean` | no | `True` |  |
| `max_alarms` | `integer` | no | `200` |  |
| `name` | `string` | no | `` |  |
| `alarm_id` | `integer` | no | `` |  |
| `alarm_type` | `string` | no | `` |  |
| `resource` | `string` | no | `` |  |
| `include_expiry_context` | `boolean` | no | `True` |  |
| `include_efa_certs` | `boolean` | no | `True` |  |
| `include_device_certs` | `boolean` | no | `True` |  |
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |
| `fabric_all` | `boolean` | no | `` |  |
| `include_raw` | `boolean` | no | `False` |  |

- Tags: `read`, `system`, `certificates`, `alarms`, `tier2`

### `system_get_certificates_expiring_soon`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Show certificates expiring soon (bucketed 30/60/90 days, UI-style color/severity). Composite of monitor cert expiry + device cert expiry.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `window_days` | `integer` | no | `90` |  |
| `include_efa_certs` | `boolean` | no | `True` |  |
| `include_device_certs` | `boolean` | no | `True` |  |
| `device_ips` | `array` | no | `` |  |
| `fabric_name` | `string` | no | `` |  |
| `fabric_all` | `boolean` | no | `` |  |
| `max_items` | `integer` | no | `200` |  |
| `include_ok` | `boolean` | no | `False` |  |
| `include_raw` | `boolean` | no | `False` |  |

- Tags: `read`, `tier2`

### `system_get_execution`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/execution`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the detailed output of a request previously executed, based on a given request ID

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` | Execution ID |

- Tags: `read`, `system`, `execution`, `tier2`

### `system_get_executions`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get the list of all the requests previously executed

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `10` | Limit the number of executions returned |
| `status` | `string` | no | `all` | Filter executions by status (failed \| succeeded \| all) |

- Tags: `read`, `system`, `execution`, `tier2`

### `system_get_feature_settings`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/feature`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get system feature settings list

- Tags: `read`, `system`, `feature`, `tier1`

### `system_get_file_download`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/file/download`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **True**

> Get any file from XCO system.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `file_type` | `string` | yes | `` |  |

- Tags: `read`, `tier1`, `sensitive`

### `system_get_ha_and_node_health_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Summarize HA redundancy + node health + storage signals, and correlate with HealthManager resources. Uses only existing Tier-1 tools: system_get_health_status, monitor_get_keep_alived_info, monitor_get_gluster_f…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `include_system_health_status` | `boolean` | no | `True` |  |
| `include_monitor` | `boolean` | no | `True` |  |
| `include_keepalived` | `boolean` | no | `True` |  |
| `include_gluster` | `boolean` | no | `True` |  |
| `include_k3s_nodes` | `boolean` | no | `True` |  |
| `include_health` | `boolean` | no | `True` |  |
| `include_health_inventory` | `boolean` | no | `True` |  |
| `include_health_detail` | `boolean` | no | `False` |  |
| `detail_only_on_problem` | `boolean` | no | `True` |  |
| `max_detail` | `integer` | no | `10` |  |
| `include_raw` | `boolean` | no | `False` |  |

- Tags: `read`, `system`, `ha`, `health`, `tier2`

### `system_get_health_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/proxy/status`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get overall system health and node status

- Tags: `read`, `system`, `health`, `tier1`

### `system_get_last_execution_diagnostic`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> Show the most recent failed system execution and why it failed

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | no | `10` |  |
| `status` | `string` | no | `failed` |  |

- Tags: `read`, `system`, `diagnostic`, `tier2`

### `system_get_logging_customization`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/logging`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get Logging Customization configuration.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `services` | `string` | no | `` |  |
| `logging_types` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `system_get_running_config`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/runningConfig`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get running configuration CLI commands

- Tags: `read`, `system`, `config`, `tier2`

### `system_get_settings`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/settings`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get system configuration settings

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `decrypt` | `boolean` | no | `False` | Decrypt sensitive values |

- Tags: `read`, `system`, `settings`, `tier1`

### `system_get_supportsave_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/proxy/supportsave`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get list of available SupportSave files

- Tags: `read`, `system`, `supportsave`, `tier1`

### `system_get_supportsave_status`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/system/proxy/supportsavestatus`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> Get the execution status of a SupportSave request using its request ID

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` | Request ID returned when a SupportSave operation is initiated |

- Tags: `read`, `system`, `supportsave`, `execution`, `tier3`

## tenant

### `tenant_get_all_endpoint_groups`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2tenant_get_all_endpoint_groups`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Discover all tenants and return every Endpoint Group (EPG) across the system, grouped by tenant, with aggregate counts.

- Tags: `read`, `tenant`, `tier2`

### `tenant_get_bgp_peer`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/bgp/service/peer`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> Get BGP peer configuration for a tenant

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` |  |
| `vrf_name` | `string` | no | `` |  |

- Tags: `read`, `tenant`, `bgp`, `tier2`

### `tenant_get_bgp_peer_operational`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/bgp/service/peer/operational`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get operational state of BGP peers for a tenant

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` | Tenant to which this BGP peer belongs |
| `vrf_name` | `string` | no | `` | Optional VRF name to filter BGP peers |

- Tags: `read`, `tenant`, `bgp`, `operational`, `tier2`

### `tenant_get_bgp_peers`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/bgp/service/peers`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> Get list of BGP peer configurations for a tenant

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` | Tenant to which the BGP peers belong |
| `vrf_name` | `string` | no | `` | Optional VRF name |

- Tags: `read`, `tenant`, `bgp`, `tier2`

### `tenant_get_bgp_service_peer_group`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/bgp/service/peer-group`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getBgpServicePeerGroup

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_bgp_service_peer_groups`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/bgp/service/peer-groups`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getBgpServicePeerGroups

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |
| `tenant_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_endpoint_group`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/endpointgroup`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getEndpointGroup

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_endpoint_group_error`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/endpointgroup/errors`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getEndpointGroupError

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_endpoint_groups`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/endpointgroups`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> List all endpoint groups (EPGs) belonging to a tenant. tenant_name is required.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` | Tenant name (required). Use tenant_get_tenants to list available tenant names. |
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_event_history_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/eventhistories`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getEventHistoryList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `execution_uuid` | `string` | no | `` |  |
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_execution_get`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/execution`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getExecutionDetail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `id` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_execution_list`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getExecutionList

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | yes | `` |  |
| `status` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_health`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/health`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get health status of the Tenant service

- Tags: `read`, `tenant`, `health`, `tier1`

### `tenant_get_locks`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/debug/lock`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get lock detail

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `type` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_mirror_service_session`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/mirror/service/session`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getMirrorServiceSession

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_mirror_sessions`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/mirror/service/sessions`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> Get mirror service sessions for a tenant

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tenant`, `mirror`, `tier2`

### `tenant_get_portchannel`
- Tier: **tier2**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/portchannel`  
- Risk: **SAFE_READ**, auto_mode: **False**, confirm: **False**

> Get detailed Portchannel configuration for a tenant

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | no | `` |  |
| `tenant_name` | `string` | yes | `` |  |
| `po_id` | `string` | no | `` |  |
| `device_ip` | `string` | no | `` |  |

- Tags: `read`, `tenant`, `portchannel`, `tier2`

### `tenant_get_portchannels`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/portchannels`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all port-channels configured for a tenant

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` | Tenant to which this port-channel belongs |
| `search` | `object` | no | `` | Optional search filter |
| `pagination` | `object` | no | `` | Optional pagination options |

- Tags: `read`, `tenant`, `portchannel`, `tier1`

### `tenant_get_running_config`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/runningConfig`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> GetRunningConfig

- Tags: `read`, `tier1`

### `tenant_get_service_epg_alarm_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2tenant_get_service_epg_alarm_summary`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Show tenant-scoped Service/EPG alarms/alerts with filters (severity/type/state) using faultmanager history + tenant EPG scoping.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` | Tenant name (required). If not found, tool returns suggested_tenants via tenant_get_tenants. |
| `include_alarms` | `boolean` | no | `True` | Include FaultManager alarms (faultmanager_get_alarm_history). |
| `include_alerts` | `boolean` | no | `True` | Include FaultManager alerts (faultmanager_get_alert_history). |
| `severity` | `string` | no | `` | Optional exact severity filter (alerts, and best-effort for alarms). Example: Critical. |
| `severity_min` | `string` | no | `` | Optional minimum severity (Critical>Major>Minor>Warning>Info). Applies to alerts and best-effort alarms. |
| `alarm_type` | `string` | no | `` | Optional alarm_type filter for alarms (passed to faultmanager_get_alarm_history). |
| `resource_contains` | `string` | no | `` | Optional substring filter applied to resource/name/message (post-filter). |
| `message_contains` | `string` | no | `` | Optional substring filter applied to message/description fields (post-filter). |
| `epg_name_contains` | `string` | no | `` | Optional substring filter applied to EPG matching (limits to alarms that match this EPG). |
| `unacked` | `boolean` | no | `True` | Alarm state filter (alarms only). |
| `acked` | `boolean` | no | `False` | Alarm state filter (alarms only). |
| `cleared` | `boolean` | no | `False` | Alarm state filter (alarms only). |
| `closed` | `boolean` | no | `False` | Alarm state filter (alarms only). |
| `alert_limit` | `integer` | no | `300` | Limit parameter for alert history (1..500). |
| `max_records` | `integer` | no | `200` | Max matched records returned (1..2000). |
| `include_raw` | `boolean` | no | `False` | If true, include tier-1 raw responses (debug). |

- Tags: `read`, `tier2`

### `tenant_get_service_epg_event_logs`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2tenant_get_service_epg_event_logs`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Event logs for a tenant/service scope (filters: date range, severity, fuzzy query). Tier-2 composite over tenant executions + event histories.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` |  |
| `service_name_contains` | `string` | no | `` |  |
| `epg_name_contains` | `string` | no | `` |  |
| `start_time` | `string` | no | `` |  |
| `end_time` | `string` | no | `` |  |
| `severity_min` | `string` | no | `` |  |
| `query` | `string` | no | `` |  |
| `execution_status` | `string` | no | `` |  |
| `execution_limit` | `integer` | no | `` |  |
| `execution_uuid` | `string` | no | `` |  |
| `device_ip` | `string` | no | `` |  |
| `max_events` | `integer` | no | `` |  |
| `allow_unscoped` | `boolean` | no | `` |  |
| `include_raw` | `boolean` | no | `` |  |

- Tags: `read`, `tier2`, `tenant`, `events`, `logs`

### `tenant_get_service_epg_health_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2tenant_get_service_epg_health_summary`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Real-time, table-friendly health summary for a tenant's VRFs + Endpoint Groups (EPGs), enriched via per-object error endpoints and optional recent execution signals.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` | Tenant name to summarize (required). |
| `include_rows` | `boolean` | no | `True` | If true, include per-EPG table rows. |
| `include_vrf_summary` | `boolean` | no | `True` | If true, include per-VRF summary rows. |
| `max_epgs` | `integer` | no | `300` | Max EPGs to scan (cap 300). |
| `max_vrfs` | `integer` | no | `200` | Max VRFs to scan (cap 200). |
| `max_rows` | `integer` | no | `2000` | Max rows to return in 'rows' (cap 2000). |
| `include_recent_executions` | `boolean` | no | `True` | If true, include recent tenant execution rollup (tenant_get_execution_list). |
| `execution_limit` | `integer` | no | `20` | How many executions to fetch (1..200). |
| `execution_status` | `string` | no | `` | Optional execution status filter (e.g., FAILED). |
| `include_events` | `boolean` | no | `False` | If true, fetch event history for the most recent FAILED execution (best-effort). |
| `include_locks` | `boolean` | no | `False` | If true, include lock counts for service/vrf/epg. |
| `include_raw` | `boolean` | no | `False` | If true, include tier-1 raw responses (debug). |

- Tags: `read`, `tier2`

### `tenant_get_service_epg_historical_report_stub`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2tenant_get_service_epg_historical_report_stub`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2 (read-only, v1): Generate a simple historical health/alarm summary for a tenant's Service/EPG scope for the last 7/30 days. Use-cases: (1) Weekly tenant health pulse (7d) summary + top impacted resources. (2) Mon…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` | Tenant name (required). If not found, tool returns suggested_tenants via tenant_get_tenants. |
| `window_days` | `integer` | no | `7` | How many days back to summarize (commonly 7 or 30). |
| `include_alerts` | `boolean` | no | `True` | Include FaultManager alerts (faultmanager_get_alert_history). |
| `include_alarms` | `boolean` | no | `True` | Include FaultManager alarms (faultmanager_get_alarm_history, time-bounded locally). |
| `severity` | `string` | no | `` | Optional exact severity filter (alerts, and best-effort for alarms). Example: Critical. |
| `severity_min` | `string` | no | `` | Optional minimum severity (Critical>Major>Minor>Warning>Info). Applies to alerts and best-effort alarms. |
| `query` | `string` | no | `` | Optional fuzzy substring filter across alert/alarm text (e.g., 'BGP', 'VXLAN'). |
| `alert_limit` | `integer` | no | `300` | Limit parameter for alert history (1..500). |
| `max_records` | `integer` | no | `200` | Max records returned per section (alerts/alarms) (1..2000). |
| `allow_unscoped` | `boolean` | no | `False` | If true, include system/global (unscoped) alerts/alarms when tenant-scoped matches are sparse. |
| `include_raw` | `boolean` | no | `False` | If true, include tier-1 raw responses (debug). |

- Tags: `read`, `tier2`

### `tenant_get_tenant`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/tenant`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get tenant details by tenant name

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` | Name of the tenant |
| `include` | `array` | no | `` | Optional fields to include |

- Tags: `read`, `tenant`, `tier1`

### `tenant_get_tenants`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/tenants`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get all tenants configured in the Tenant service

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |
| `include` | `array` | no | `` |  |

- Tags: `read`, `tenant`, `tier1`

### `tenant_get_vrf`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/vrf`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVrf

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_vrf_error`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/vrf/errors`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVrfError

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_vrf_route_target`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/vrf/route-target`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVrfRouteTarget

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_vrf_static_routes`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/vrf/static-routes`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVrfStaticRoutes

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_vrf_static_routes_bfd`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/vrf/static-routes-bfd`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVrfStaticRoutesBFD

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |
| `name` | `string` | yes | `` |  |
| `tenant_name` | `string` | yes | `` |  |

- Tags: `read`, `tier1`

### `tenant_get_vrfs`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/tenant/vrfs`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> getVrfs

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `tenant_name` | `string` | yes | `` |  |
| `search` | `string` | no | `` |  |
| `pagination` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `tenant_list_ids`
- Tier: **tier1**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2 SAFE_READ composite — the PAIRED LIST for tenant-required tenant tools. Returns tenant_ids[] + tenants[{tenant_id, tenant_name}] in clean snake_case so a client never hard-codes a tenant name from a cached sample…

- Tags: `read`, `tenant`, `discovery`, `ids`, `composite`

## vcenter

### `vcenter_get_esxi_details`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/vcenter/host/details`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get ESXi host details from vCenter

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |
| `server_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_events`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/events`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get vCenter events

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |
| `page_number` | `integer` | no | `` |  |
| `limit` | `integer` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_executions`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/executions`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get vCenter service executions

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `limit` | `integer` | no | `` |  |
| `status` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_physical_links`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/links/physical`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get physical NIC to switch links

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |
| `server_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_tenant_details`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/vcenter/tenant`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get tenant mapping for vCenter

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_unconnected_pnics`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/pnics/disconnected`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get disconnected physical NICs

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |
| `server_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_vcenter_details`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/vcenter/details`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get vCenter detailed information

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_vcenters`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/vcenter`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get registered vCenter servers

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `host_name` | `string` | no | `` |  |

- Tags: `read`, `tier1`

### `vcenter_get_virtual_links`
- Tier: **tier1**  
- Method: **GET**  
- Endpoint: `{XCO_HOST}/v1/vmware/links/virtual`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Get virtual NIC links

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `server_ip` | `string` | no | `` |  |

- Tags: `read`, `tier1`

## restconf

### `restconf_get_arp_table`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Show ARP table (IP→MAC→interface) via RESTCONF RPC (brocade-arp:get-arp).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string\|array` | yes | `` | Switch management IP/FQDN.  Pass a single string for single-switch probe (original response shape) OR an array of strings for parallel multi-switch fan-out (v2 response shape: meta.multi_switch=true, switch_level_data_by_ip, errors_by_ip; per-switch failures non-fatal).  Single-element list also returns the multi-switch shape so widgets can render consistently. |
| `ip_filter` | `string` | no | `` | Optional substring match on IP address. |
| `mac_filter` | `string` | no | `` | Optional substring match on MAC (case-insensitive). |
| `interface_name` | `string` | no | `` | Optional substring match on interface/port. |
| `max_items` | `integer` | no | `200` | Max entries to return (default 200). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `arp`

### `restconf_get_clock`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Show device clock/time status via RESTCONF RPC (brocade-clock:show-clock).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `clock`, `time`

### `restconf_get_interface_all`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Get all interfaces (management, ethernet, port-channel) via RESTCONF GET (brocade-interface:interface?depth=unbounded). Returns name, type, shutdown status, description, IP addresses, and channel-group membershi…

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `interface`, `ethernet`, `management`, `port-channel`, `status`

### `restconf_get_interface_detail`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2restconf_get_interface_detail`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Read-only: Query an SLX switch directly via RESTCONF RPC (get-interface-detail) to return rich port/interface statistics (RX/TX octets/packets/errors) and state. Optional interface_name filter.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Management IP/FQDN of the target switch (required). |
| `interface_name` | `string` | no | `` | Optional. Example: 'Ethernet 0/1' or '0/1' or 'Port-channel 64' or '64'. |
| `username` | `string` | no | `` | Optional override RESTCONF username (falls back to RESTCONF_USERNAME/RESTCONF_USER env). |
| `password` | `string` | no | `` | Optional override RESTCONF password (falls back to RESTCONF_PASSWORD/RESTCONF_PASS env). |
| `verify_tls` | `boolean` | no | `False` | If true, verify TLS cert (else insecure). Defaults to RESTCONF_VERIFY_TLS env if set. |
| `max_items` | `integer` | no | `200` | Limit number of returned interfaces in items[]. |
| `include_raw` | `boolean` | no | `False` | If true, include raw RESTCONF RPC response for debugging. |

- Tags: `read`, `restconf`, `switch`, `interface`, `statistics`, `tier2`

### `restconf_get_ip_interface`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Show L3 IP addressing per interface (IPv4/IPv6) via RESTCONF data tree (brocade-interface:interface). Uses XML parsing fallback for SLX builds that return non-strict JSON.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `interface_name` | `string` | no | `` | Optional filter: match interface (e.g. 'Ethernet 0/1', '0/1', 've 10', '10'). |
| `include_ipv6` | `boolean` | no | `True` | If true, attempt to include IPv6 addresses when present. |
| `max_items` | `integer` | no | `200` | Max interfaces to return (default 200). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `interface`, `ip`, `ipv4`, `ipv6`, `l3`

### `restconf_get_lldp_neighbor_detail`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Get LLDP neighbor details directly from a switch via RESTCONF RPC (brocade-lldp-ext:get-lldp-neighbor-detail).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP. |
| `interface_name` | `string` | no | `` | Optional: filter to a specific local interface (e.g. Ethernet 0/1). |
| `max_items` | `integer` | no | `200` | Max neighbors returned (default 200). |
| `username` | `string` | no | `` | Optional override (otherwise uses env/defaults). |
| `password` | `string` | no | `` | Optional override (otherwise uses env/defaults). |
| `verify_tls` | `boolean` | no | `` | Optional override for TLS verification. |

- Tags: `read`, `tier2`, `restconf`, `lldp`, `neighbors`

### `restconf_get_media_detail`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Show media/transceiver (SFP/QSFP) details via RESTCONF (vendor/serial/temp/RX/TX power when available).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `interface_name` | `string` | no | `` | Optional port name, e.g. 'Ethernet 0/1'. |
| `max_items` | `integer` | no | `200` | Max entries to return. |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `media`, `optics`

### `restconf_get_port_statistics_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Summarize Ethernet port counters (octets/errors) across ports using RESTCONF RPC (get-interface-detail).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `max_ports` | `integer` | no | `64` | Max ethernet ports to include (default 64). |
| `top_n` | `integer` | no | `5` | Top N ports by total octets (default 5). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `interface`, `statistics`

### `restconf_get_running_config`
- Tier: **tier1**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Retrieve a running configuration snapshot via SLX /rest/config/running (vendor XML). Returns top-level config sections + key identity fields (hostname/chassis).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `config_path` | `string` | no | `` | Optional subpath under /rest/config/running (example: 'interface', 'threshold-monitor'). If omitted, fetches the full running config root. |
| `max_bytes` | `integer` | no | `200000` | Max bytes of raw XML snippet to include when include_raw=true. |
| `include_raw` | `boolean` | no | `False` | Include raw XML snippet for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `restconf`, `config`, `running`

### `restconf_get_system_maintenance_rate_monitoring`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Get system maintenance rate monitoring status via RESTCONF RPC (brocade-system-maintenance:get-system-maintenance-rate-monitoring). Some builds return HTTP 204 when not configured.

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `system`, `maintenance`, `rate`, `monitoring`, `status`

### `restconf_get_system_maintenance_status`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Get system maintenance / maintenance-mode status via RESTCONF RPC (brocade-system-maintenance:get-maint-mode-status).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `system`, `maintenance`, `mode`, `status`

### `restconf_get_vlan_brief`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: Show VLAN brief summary via RESTCONF RPC (brocade-interface-ext:get-vlan-brief).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP/FQDN (required). |
| `vlan_id` | `integer` | no | `` | Optional exact match VLAN ID. |
| `name_filter` | `string` | no | `` | Optional substring match on VLAN name (case-insensitive). |
| `port_filter` | `string` | no | `` | Optional substring match inside VLAN ports/membership text. |
| `max_items` | `integer` | no | `200` | Max VLANs to return (default 200). |
| `include_raw` | `boolean` | no | `False` | Include raw RESTCONF payload for troubleshooting. |
| `username` | `string` | no | `` | Optional override RESTCONF username. |
| `password` | `string` | no | `` | Optional override RESTCONF password. |
| `verify_tls` | `boolean` | no | `` | Optional override TLS verification. |
| `timeout_seconds` | `integer` | no | `` | Optional override request timeout. |

- Tags: `read`, `tier2`, `restconf`, `vlan`

### `restconf_get_vrf_summary`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2restconf_get_vrf_summary`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Read-only: Query an SLX switch directly via RESTCONF data tree to list configured VRFs (bypasses XCO).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Management IP/FQDN of the target switch (required). |
| `name_filter` | `string` | no | `` | Optional substring filter on VRF name. |
| `max_items` | `integer` | no | `200` | Maximum number of VRF items to return. |
| `username` | `string` | no | `` | Optional override RESTCONF username (falls back to RESTCONF_USERNAME env). |
| `password` | `string` | no | `` | Optional override RESTCONF password (falls back to RESTCONF_PASSWORD env). |
| `verify_tls` | `boolean` | no | `False` | If true, verify TLS cert (else -k / insecure). Defaults to RESTCONF_VERIFY_TLS env if set. |
| `timeout_seconds` | `integer` | no | `20` | RESTCONF request timeout seconds (defaults to RESTCONF_TIMEOUT_SECONDS env). |
| `include_raw` | `boolean` | no | `False` | If true, include raw RESTCONF response for debugging. |

- Tags: `read`, `restconf`, `switch`, `vrf`, `l3`, `tier2`

### `restconf_list_operations`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: ``  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Tier-2: List RESTCONF RPC operations exposed by a switch (useful for discovery; filterable).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Switch management IP. |
| `filter` | `string` | no | `` | Optional substring filter (case-insensitive). Example: lldp |
| `max_items` | `integer` | no | `200` | Max operations returned (default 200). |
| `username` | `string` | no | `` | Optional override (otherwise uses env/defaults). |
| `password` | `string` | no | `` | Optional override (otherwise uses env/defaults). |
| `verify_tls` | `boolean` | no | `` | Optional override for TLS verification. |

- Tags: `read`, `tier2`, `restconf`, `discovery`

### `restconf_show_firmware_version`
- Tier: **tier2**  
- Method: **COMPOSITE**  
- Endpoint: `tier2restconf_show_firmware_version`  
- Risk: **SAFE_READ**, auto_mode: **True**, confirm: **False**

> Read-only: Query an SLX switch directly via RESTCONF RPC to return OS/firmware version + uptime (bypasses XCO).

**Inputs**

| name | type | required | default | description |
|---|---|---:|---|---|
| `switch_ip` | `string` | yes | `` | Management IP/FQDN of the target switch (required). |
| `username` | `string` | no | `` | Optional override RESTCONF username (falls back to RESTCONF_USER env). |
| `password` | `string` | no | `` | Optional override RESTCONF password (falls back to RESTCONF_PASS env). |
| `verify_tls` | `boolean` | no | `False` | If true, verify TLS cert (else -k / insecure). Defaults to RESTCONF_VERIFY_TLS env if set. |
| `include_raw` | `boolean` | no | `False` | If true, include raw RESTCONF RPC response for debugging. |

- Tags: `read`, `restconf`, `switch`, `firmware`, `tier2`
