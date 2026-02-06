# mcp_runtime/metrics.py

from prometheus_client import Counter, Histogram

# ----------------------------------------
# Global metrics registry
# ----------------------------------------

MCP_INVOKE_TOTAL = Counter(
    "mcp_invoke_total",
    "Total number of MCP tool invocations",
    ["tool"],
)

MCP_INVOKE_SUCCESS = Counter(
    "mcp_invoke_success_total",
    "Total successful MCP tool invocations",
    ["tool"],
)

MCP_INVOKE_FAILURE = Counter(
    "mcp_invoke_failure_total",
    "Total failed MCP tool invocations",
    ["tool"],
)

MCP_INVOKE_LATENCY = Histogram(
    "mcp_invoke_latency_seconds",
    "Latency of MCP tool invocations",
    ["tool"],
    buckets=(
        0.05,   # 50ms
        0.1,    # 100ms
        0.25,
        0.5,
        0.75,
        1.0,
        1.5,
        2.0,
        3.0,
        5.0,
        10.0,
        float("inf"),
    ),
)

MCP_INVOKE_STATUS = Counter(
    "mcp_invoke_status_total",
    "MCP tool invocations by HTTP status code",
    ["tool", "status"],
)


