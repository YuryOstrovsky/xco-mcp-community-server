# mcp_runtime/context_resolver.py

class ContextResolver:
    def __init__(self, transport):
        self.transport = transport

    # -----------------------------
    # Fabric resolution
    # -----------------------------
    def resolve_fabric(self, name: str):
        if not isinstance(name, str):
            raise ValueError("Fabric name must be a string")

        name_norm = name.strip().lower()

        fabrics = self._get_fabrics()

        for f in fabrics:
            fabric_name = f.get("fabric-name")
            if not fabric_name:
                continue

            if fabric_name.strip().lower() == name_norm:
                return {
                    "id": f.get("fabric-id"),
                    "name": fabric_name,   # preserve canonical casing
                }

        raise ValueError(f"Fabric '{name}' not found")

    def _get_fabrics(self):
        resp = self.transport.request(
            method="GET",
            port=443,
            path="/v1/fabric/fabrics",
        )
        return resp["payload"].get("items", [])

    # -----------------------------
    # Tenant resolution
    # -----------------------------
    def resolve_tenant(self, name: str):
        if not isinstance(name, str):
            raise ValueError("Tenant name must be a string")

        name_norm = name.strip().lower()

        tenants = self._get_tenants()

        for t in tenants:
            tenant_name = t.get("name")
            if tenant_name and tenant_name.strip().lower() == name_norm:
                return {
                    "id": t.get("id"),
                    "name": tenant_name,
                }

        raise ValueError(f"Tenant '{name}' not found")

    def _get_tenants(self):
        resp = self.transport.request(
            method="GET",
            port=443,
            path="/v1/tenant/tenants",
        )
        return resp["payload"].get("tenant", [])

    # -----------------------------
    # Device resolution
    # -----------------------------
    def resolve_device(self, identifier: str, fabric_ctx=None, tenant_ctx=None):
        if not isinstance(identifier, str):
            raise ValueError("Device identifier must be a string")

        ident_norm = identifier.strip().lower()

        devices = self._get_devices()

        for d in devices:
            # ---- Canonical fields (REAL XCO schema) ----
            name = d.get("name")
            ip = d.get("ip_address")
            role = d.get("role")
            device_id = d.get("id")

            fabric = d.get("fabric") or {}
            fabric_id = fabric.get("fabric_id")
            fabric_name = fabric.get("fabric_name")

            # ---- Identifier match (name OR IP, case-insensitive) ----
            if (
                (name and name.strip().lower() == ident_norm)
                or (ip and ip.strip().lower() == ident_norm)
            ):
                return {
                    "id": device_id,
                    "name": name,
                    "role": role,
                    "mgmt_ip": ip,
                    "fabric_id": fabric_id,
                    "fabric_name": fabric_name,
                }

        raise ValueError(f"Device '{identifier}' not found")

    def _get_devices(self):
        resp = self.transport.request(
            method="GET",
            port=443,
            path="/v1/inventory/switches",
        )
        return resp["payload"].get("items", [])
