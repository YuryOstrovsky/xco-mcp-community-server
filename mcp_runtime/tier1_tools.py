# mcp_runtime/tier1_tools.py

TIER1_TOOL_NAMES = {
    "fabric_get_fabrics",
    "fabric_get_fabrics_health",  
    "fabric_get_fabrics_errors",
    "fabric_get_devices",
    "fabric_get_physical_topology",
    "fabric_get_topology_overlay",
    "fabric_get_underlay_topology",
    "fabric_get_overlay_topology",
    "fabric_validate_physical_topology",
    "fabric_get_service_locks",
    "fabric_get_running_config",

    "inventory_getswitches",
    "inventory_switch_inventory_summary",
    "inventory_switch_inventory_info"

    "inventory_get_rma_history",
    "inventory_get_rma_detail",
    "inventory_get_tpvm_upgrade_status",
    "inventory_get_firmware_download_status",
    "inventory_get_firmware_download_history",
    "inventory_get_firmware_download_operation_history",
    "inventory_get_device_inventory_structure",
    "inventory_get_device_inventory_summary",
    "inventory_get_device_inventory_info",
    "inventory_get_device_inventory_ports",
    "inventory_get_device_inventory_export",

    "auth_validate_token",
    "auth_get_token_expiry",
    "auth_get_all_token_expiry",
    "auth_get_clients",
    "auth_get_client_by_name",
    "auth_get_execution",
    "auth_get_executions",

    "system_get_feature_settings",
    "system_get_settings",
    "system_get_running_config",
    "system_get_health_status",
    "system_get_supportsave_list",
    "system_get_supportsave_status",
    "system_get_executions",
    "system_get_execution",
    "system_get_last_execution_diagnostic",


    "monitor_get_service_status",
    "monitor_get_k3s_status",
    "monitor_get_k3s_nodes",
    "monitor_get_k3s_pods",
    "monitor_get_k3s_resources",
    "monitor_get_deployment_config",
    "monitor_get_all_status",
   

   "notification_get_subscribers",
   "notification_get_subscriber",
   "notification_get_executions",


   "faultmanager_get_health",
   "faultmanager_get_alert_inventory",
   "faultmanager_get_alert_history",
   "faultmanager_get_alarm_inventory",
   "faultmanager_get_alarm_history",
   "faultmanager_get_alarm_summary",


   "snmp_get_health",
   "snmp_get_trap_subscribers",
   "snmp_get_executions",
   "snmp_get_execution",


   "tenant_get_health",
   "tenant_get_tenants",
   "tenant_get_tenant",
   "tenant_get_portchannels",
   "tenant_get_portchannel",
   "tenant_get_bgp_peer_operational",
   "tenant_get_bgp_peers",
   "tenant_get_bgp_peer",
   "tenant_get_mirror_sessions",





    
}

