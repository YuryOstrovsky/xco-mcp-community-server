# tools/system/diagnostics.py

def system_get_last_execution_diagnostic(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
):
    """
    Tier-2 diagnostic tool.

    Find the most recent system execution matching the requested status
    (default: failed) and return both the summary and detailed execution log.
    """

    limit = inputs.get("limit", 10)
    status = inputs.get("status", "failed")

    # --------------------------------------------------
    # 1. Call Tier-1: system_get_executions
    # --------------------------------------------------
    executions_resp = transport.request(
        method="GET",
        path="/v1/system/executions",
        params={
            "limit": limit,
            "status": status,
        },
        context=context,
    )

    if executions_resp["status"] != 200:
        return {
            "error": "Failed to retrieve execution list",
            "details": executions_resp,
        }

    items = executions_resp["payload"].get("items", [])
    if not items:
        return {
            "message": f"No executions found with status='{status}'",
            "execution": None,
        }

    latest = items[0]
    execution_id = latest.get("id")

    if not execution_id:
        return {
            "message": "Execution entry missing ID",
            "execution": latest,
        }

    # --------------------------------------------------
    # 2. Call Tier-1: system_get_execution
    # --------------------------------------------------
    detail_resp = transport.request(
        method="GET",
        path="/v1/system/execution",
        params={"id": execution_id},
        context=context,
    )

    if detail_resp["status"] != 200:
        return {
            "execution_id": execution_id,
            "summary": latest,
            "error": "Failed to retrieve execution details",
            "details": detail_resp,
        }

    # --------------------------------------------------
    # 3. Return correlated diagnostic result
    # --------------------------------------------------
    return {
        "execution_id": execution_id,
        "status": status,
        "summary": latest,
        "details": detail_resp["payload"],
    }
