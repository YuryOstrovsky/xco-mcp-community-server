# Roadmap

This is a **read-only** MCP server for ExtremeCloud Orchestrator (XCO) and SLX
RESTCONF. The roadmap reflects direction, not commitments — priorities shift with
community feedback (open a [Discussion](../../discussions) or issue to weigh in).

## Now
- Stabilize the MCP JSON-RPC transport (`/mcp`) against MCP Inspector / Claude
  Desktop and broaden conformance coverage.
- Grow the offline test suite (more catalog/tool-parsing unit tests; mock-XCO
  integration tests).

## Next
- Expand discovery/paired-listing tools so every ID-required tool has a partner.
- Optional progress notifications on long-running fan-out tools.
- Per-tool latency estimates surfaced to clients.

## Later / under consideration
- Optional response caching for hot read paths.
- Richer observability (per-tool dashboards, exemplars).
- PyPI distribution once the package surface stabilizes.

## Explicitly out of scope (community edition)
This edition is intentionally read-only and single-tenant. The following stay in
the enterprise edition and will **not** be added here:
- Mutating/destructive operations, plan-approval pipelines, undo/ledger.
- OAuth2 / scope enforcement / multi-tenant auth.
- Multi-site routing, RoCE/QoS/firmware-mutation tooling, secret managers.
