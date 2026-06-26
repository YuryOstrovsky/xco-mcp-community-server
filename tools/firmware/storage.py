# tools/firmware/storage.py
"""Firmware storage pre-flight (read-only).

firmware_check_storage — check available flash/disk space on switches before a
firmware download, plus whether core/FFDC files are present. Read-only: it only
runs `dir` and `show support` over SSH (no changes are made).
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from mcp_runtime.logging import get_logger

logger = get_logger("mcp.firmware")

# Minimum free space (MB) typically needed for a firmware download (~1.1 GB image).
_MIN_FREE_MB = 2000


def _ssh_commands(ip: str, username: str, password: str, commands: List[str],
                  timeout: int = 15) -> Dict[str, Any]:
    """Run command(s) on an SLX switch via SSH in one session.
    Returns {ok, outputs: {command: output}, error}."""
    import paramiko  # lazy import — only the SSH-based tools pull this in
    import time

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            ip, username=username, password=password,
            timeout=10, look_for_keys=False, allow_agent=False,
            disabled_algorithms={"pubkeys": ["rsa-sha2-512", "rsa-sha2-256"]},
        )

        shell = client.invoke_shell()
        time.sleep(0.5)
        shell.recv(65535)  # clear banner

        outputs: Dict[str, str] = {}
        for cmd in commands:
            shell.send(cmd + "\n")
            output = b""
            deadline = time.time() + timeout
            idle_count = 0
            while time.time() < deadline:
                time.sleep(0.5)
                if shell.recv_ready():
                    output += shell.recv(65535)
                    idle_count = 0
                else:
                    idle_count += 1
                    if idle_count >= 4 and output:
                        break
            outputs[cmd] = output.decode("utf-8", errors="replace")

        shell.send("exit\n")
        client.close()
        return {"ok": True, "outputs": outputs, "error": None}

    except Exception as e:  # noqa: BLE001
        return {"ok": False, "outputs": {}, "error": str(e)}


def firmware_check_storage(
    *,
    inputs: Dict[str, Any],
    registry=None,
    transport=None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Check available storage (and core/FFDC presence) on switches for a firmware
    download. SSHs to each switch and runs `dir` + `show support` (read-only).

    Inputs:
      device_ips: list of switch IPs (or a single IP string)
      username / password: SSH creds (default: RESTCONF_USERNAME / RESTCONF_PASSWORD env)
    """
    device_ips = inputs.get("device_ips", [])
    if isinstance(device_ips, str):
        device_ips = [device_ips]
    username = inputs.get("username") or os.environ.get("RESTCONF_USERNAME", "admin")
    password = inputs.get("password") or os.environ.get("RESTCONF_PASSWORD", "")

    if not device_ips:
        return {"status": 400, "payload": {"error": "device_ips required (string or list)"}}

    results: List[Dict[str, Any]] = []
    all_sufficient = True

    for ip in device_ips:
        logger.info("firmware_check_storage: checking %s", ip)
        ssh = _ssh_commands(ip, username, password, ["dir", "show support"])

        total_mb = 0
        free_mb = 0
        sufficient = False
        core_files_present = False
        support_info = ""

        if ssh["ok"]:
            dir_output = ssh["outputs"].get("dir", "")
            match = re.search(r"(\d+)\s+bytes\s+total\s*\((\d+)\s+bytes\s+free\)", dir_output)
            if match:
                total_mb = int(match.group(1)) // (1024 * 1024)
                free_mb = int(match.group(2)) // (1024 * 1024)
                sufficient = free_mb >= _MIN_FREE_MB

            support_output = ssh["outputs"].get("show support", "")
            if "core" in support_output.lower() or "ffdc" in support_output.lower():
                core_files_present = True
                support_info = support_output.strip()[:500]

        if not sufficient:
            all_sufficient = False

        results.append({
            "ip": ip,
            "total_mb": total_mb,
            "free_mb": free_mb,
            "required_mb": _MIN_FREE_MB,
            "sufficient": sufficient,
            "core_files_present": core_files_present,
            "support_info": support_info if core_files_present else "",
            "error": ssh.get("error") if not ssh["ok"] else None,
        })

    return {"status": 200, "payload": {
        "devices": results,
        "all_sufficient": all_sufficient,
        "min_required_mb": _MIN_FREE_MB,
        "recommendation": (
            "All switches have sufficient space."
            if all_sufficient
            else "Some switches have low free space — clear core/FFDC files before upgrade."
        ),
    }}
