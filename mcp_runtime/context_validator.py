# mcp_runtime/context_validator.py

class ContextValidationError(ValueError):
    pass


class ContextValidator:
    """
    Enforces context consistency and scope narrowing rules.
    """

    def validate(self, resolved_context: dict):
        fabric = resolved_context.get("fabric")
        tenant = resolved_context.get("tenant")
        device = resolved_context.get("device")

        # ---- Device must belong to fabric ----
        if device and fabric:
            if device.get("fabric_id") != fabric.get("id"):
                raise ContextValidationError(
                    f"Device '{device['name']}' does not belong to fabric '{fabric['name']}'"
                )

        # ---- (Future) tenant-device ownership checks ----
        # XCO does not always expose this directly, so kept optional
        # if device and tenant:
        #     if device.get("tenant_id") != tenant.get("id"):
        #         raise ContextValidationError(
        #             f"Device '{device['name']}' not owned by tenant '{tenant['name']}'"
        #         )

        # ---- Context is valid ----
        return True

