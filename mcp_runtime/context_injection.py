# mcp_runtime/context_injection.py

class ContextInjector:
    """
    Converts resolved context objects into API query parameters.
    """

    def inject(self, params: dict, context: dict) -> dict:
        injected = dict(params) if params else {}

        # ---- Fabric scoping ----
        if "fabric" in context:
            injected["fabric-id"] = context["fabric"]["id"]

        # ---- Tenant scoping ----
        if "tenant" in context:
            injected["tenant-id"] = context["tenant"]["id"]

        # ---- Device scoping ----
        if "device" in context:
            injected["id"] = context["device"]["id"]

        return injected

