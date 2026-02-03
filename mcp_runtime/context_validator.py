# mcp_runtime/context_validator.py

class ContextValidator:
    """
    Phase 2.6:
    - Merge context deterministically (supports dict contexts from previous calls)
    - Validate consistency across context objects (fabric/device alignment)
    """

    # -----------------------------
    # Merge
    # -----------------------------
    def merge(self, base_ctx: dict, new_ctx: dict | None) -> dict:
        """
        Deterministic context merge.

        Rules:
        - base_ctx is usually the resolved_context we’re building
        - new_ctx is the incoming `context=...` argument
        - If new_ctx provides a dict with 'id', we treat it as canonical and copy it
        - Strings are NOT resolved here (server.py resolves them), merge only
        - new_ctx overrides base_ctx for keys it includes
        """
        merged = dict(base_ctx or {})

        if not new_ctx:
            return merged

        for key, val in new_ctx.items():
            # If caller passes prior resolved context, it’s dict-like and should be kept
            if isinstance(val, dict) and "id" in val:
                merged[key] = val
            else:
                # allow server.py to resolve strings; keep as-is for now
                merged[key] = val

        return merged

    # -----------------------------
    # Validate
    # -----------------------------
    def validate(self, ctx: dict) -> None:
        """
        Validates cross-context integrity.

        Enforced in Phase 2.6:
        - If both fabric and device exist, device.fabric_id must match fabric.id
        - If device exists without fabric, it's OK (device includes fabric_id/name)
        - If tenant exists, no hard cross-check yet (future phase can enforce tenant membership)
        """
        if not ctx:
            return

        fabric = ctx.get("fabric")
        device = ctx.get("device")

        # Validate required structure if present
        if fabric is not None:
            if not isinstance(fabric, dict) or "id" not in fabric or "name" not in fabric:
                raise ValueError("Invalid fabric context shape (expected {'id', 'name'})")

        if device is not None:
            if not isinstance(device, dict) or "id" not in device or "name" not in device:
                raise ValueError("Invalid device context shape (expected at least {'id', 'name'})")

        # Cross-check device ↔ fabric consistency
        if fabric and device:
            dev_fabric_id = device.get("fabric_id")
            if dev_fabric_id is not None and dev_fabric_id != fabric["id"]:
                raise ValueError(
                    f"Device '{device.get('name')}' does not belong to fabric '{fabric.get('name')}'"
                )
