import json
from pathlib import Path

from mcp_runtime.tier1_tools import TIER1_TOOL_NAMES
from tools.system.diagnostics import system_get_last_execution_diagnostic
from tools.fabric.overview import fabric_get_fabric_overview
from tools.fabric.health_summary import fabric_get_fabric_health_summary
from tools.fabric.health_timeline import fabric_get_fabric_health_timeline
from tools.fabric.validation_report import fabric_get_fabric_validation_report
from tools.fabric.errors_summary import fabric_get_fabric_errors_summary
from tools.fabric.execution_last_failed import fabric_get_fabric_execution_last_failed
from tools.fabric.execution_recent import fabric_get_fabric_execution_recent
from tools.fabric.efa_command_list import fabric_get_fabric_efa_command_list
from tools.inventory.fabric_switches_summary import inventory_get_fabric_switches_summary
from tools.inventory.software_version_mismatch import inventory_get_software_version_mismatch
from tools.inventory.device_health_rollup import inventory_get_device_health_rollup
from tools.inventory.unreachable_devices import inventory_get_unreachable_devices
from tools.tenant.service_epg_health_summary import tenant_get_service_epg_health_summary
from tools.tenant.service_epg_alarm_summary import tenant_get_service_epg_alarm_summary
from tools.tenant.service_epg_event_logs import tenant_get_service_epg_event_logs
from tools.tenant.service_epg_historical_report_stub import tenant_get_service_epg_historical_report_stub
from tools.faultmanager.active_alarms_top import fault_get_active_alarms_top
from tools.faultmanager.alarm_details_with_context import fault_get_alarm_details_with_context
from tools.faultmanager.fabric_health_related_alerts import fault_get_fabric_health_related_alerts
from tools.notification.recent_events_filtered import notification_get_recent_events_filtered
from tools.notification.last_failed_delivery_or_errors import notification_get_last_failed_delivery_or_errors
from tools.monitor.platform_quick_status import monitor_get_platform_quick_status
from tools.system.ha_and_node_health_summary import system_get_ha_and_node_health_summary
from tools.system.certificates_expiring_soon import system_get_certificates_expiring_soon
from tools.system.certificate_alarm_context import system_get_certificate_alarm_context
from tools.inventory.switches_widget_table import inventory_get_switches_widget_table
from restconf.tools import (
    restconf_show_firmware_version,
    restconf_get_interface_detail,
    restconf_list_operations,
    restconf_get_lldp_neighbor_detail,
    restconf_get_port_statistics_summary,
    restconf_get_media_detail,
    restconf_get_arp_table,
    restconf_get_clock,
    restconf_get_vlan_brief,
    restconf_get_vrf_summary,
    restconf_get_ip_interface,
    restconf_get_running_config,
    restconf_get_system_maintenance_status,
    restconf_get_system_maintenance_rate_monitoring,
    
)






TOOLS_FILE = Path("generated/mcp_tools.json")


class MCPRegistry:
    def __init__(self):
        # tool_name -> tool definition (JSON)
        self.tools = {}

        # tool_name -> execution handler (Python callable)
        self.handlers = {}

    def load(self):
        """
        Load MCP tools from generated/mcp_tools.json
        """
        data = json.loads(TOOLS_FILE.read_text())

        for tool in data:
            name = tool.get("name")

            # ---------------------------------------
            # 🚫 Skip disabled tools (doc-only)
            # ---------------------------------------
            if tool.get("policy", {}).get("disabled") is True:
                continue

            self.tools[name] = tool

            # Tier-1 tools use generic HTTP executor
            if name in TIER1_TOOL_NAMES:
                self.handlers[name] = None  # handled by Tier-1 executor


        # ---- Tier-2 registrations (EXPLICIT) ----
        self.handlers["system_get_last_execution_diagnostic"] = (
            system_get_last_execution_diagnostic
        )

        self.handlers["fabric_get_fabric_overview"] = (
            fabric_get_fabric_overview
        )

        
        self.handlers["fabric_get_fabric_health_summary"] = (
            fabric_get_fabric_health_summary
        )

        self.handlers["fabric_get_fabric_health_timeline"] = (
            fabric_get_fabric_health_timeline
        )

        self.handlers["fabric_get_fabric_validation_report"] = (
            fabric_get_fabric_validation_report
        )

        self.handlers["fabric_get_fabric_errors_summary"] = (
            fabric_get_fabric_errors_summary
        )

        self.handlers["fabric_get_fabric_execution_last_failed"] = (
            fabric_get_fabric_execution_last_failed
        )

        self.handlers["fabric_get_fabric_execution_recent"] = (
            fabric_get_fabric_execution_recent
        )

        self.handlers["fabric_get_fabric_efa_command_list"] = (
            fabric_get_fabric_efa_command_list
        )

        self.handlers["inventory_get_fabric_switches_summary"] = (
            inventory_get_fabric_switches_summary
        )

        self.handlers["inventory_get_software_version_mismatch"] = (
            inventory_get_software_version_mismatch
        )

        self.handlers["inventory_get_device_health_rollup"] = (
            inventory_get_device_health_rollup
        )

        self.handlers["inventory_get_unreachable_devices"] = (
            inventory_get_unreachable_devices
        )

        self.handlers["tenant_get_service_epg_health_summary"] = (
            tenant_get_service_epg_health_summary
        )

        self.handlers["tenant_get_service_epg_alarm_summary"] = (
            tenant_get_service_epg_alarm_summary
        )

        self.handlers["tenant_get_service_epg_event_logs"] = (
            tenant_get_service_epg_event_logs
        )

        self.handlers["tenant_get_service_epg_historical_report_stub"] = (
            tenant_get_service_epg_historical_report_stub
        )

        self.handlers["fault_get_active_alarms_top"] = (
            fault_get_active_alarms_top
        )

        self.handlers["fault_get_alarm_details_with_context"] = (
            fault_get_alarm_details_with_context
        )

        self.handlers["fault_get_fabric_health_related_alerts"] = (
            fault_get_fabric_health_related_alerts
        )

        self.handlers["notification_get_recent_events_filtered"] = (
            notification_get_recent_events_filtered
        )

        self.handlers["notification_get_last_failed_delivery_or_errors"] = (
            notification_get_last_failed_delivery_or_errors
        )

        self.handlers["monitor_get_platform_quick_status"] = (
            monitor_get_platform_quick_status
        )

        self.handlers["system_get_ha_and_node_health_summary"] = (
            system_get_ha_and_node_health_summary
        )

        self.handlers["system_get_certificates_expiring_soon"] = (
            system_get_certificates_expiring_soon
        )

        self.handlers["system_get_certificate_alarm_context"] = (
            system_get_certificate_alarm_context
        )

        self.handlers["inventory_get_switches_widget_table"] = (
            inventory_get_switches_widget_table
        )

        self.handlers["restconf_show_firmware_version"] = (
            restconf_show_firmware_version
        )

        self.handlers["restconf_get_interface_detail"] = (
            restconf_get_interface_detail
        )

        self.handlers["restconf_list_operations"] = (
            restconf_list_operations
        )

        self.handlers["restconf_get_lldp_neighbor_detail"] = (
            restconf_get_lldp_neighbor_detail
        )

        self.handlers["restconf_get_port_statistics_summary"] = (
            restconf_get_port_statistics_summary
        )

        self.handlers["restconf_get_media_detail"] = (
            restconf_get_media_detail
        )

        self.handlers["restconf_get_arp_table"] = (
            restconf_get_arp_table
        )

        self.handlers["restconf_get_clock"] = (
            restconf_get_clock
        )

        self.handlers["restconf_get_vlan_brief"] = (
            restconf_get_vlan_brief
        )

        self.handlers["restconf_get_vrf_summary"] = (
            restconf_get_vrf_summary
        )

        self.handlers["restconf_get_ip_interface"] = (
            restconf_get_ip_interface
        )

        self.handlers["restconf_get_running_config"] = (
            restconf_get_running_config
        )

        self.handlers["restconf_get_system_maintenance_status"] = (
            restconf_get_system_maintenance_status
        )

        self.handlers["restconf_get_system_maintenance_rate_monitoring"] = (
            restconf_get_system_maintenance_rate_monitoring
        )

       

        return self

    def list_tools(self):
        return list(self.tools.values())

    def get(self, name: str):
        return self.tools.get(name)

    def get_handler(self, name: str):
        """
        Return execution handler if this is a Tier-2 tool.
        """
        return self.handlers.get(name)
