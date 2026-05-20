"""
utils/log_generator.py
Perception Layer — Simulates real-time cluster log ingestion for ClawOps Agent.
"""

import json
import random
from datetime import datetime, timezone


# ── Fault catalogue ──────────────────────────────────────────────────────────
_FAULT_SCENARIOS = [
    {
        "error_code": "OOM_KILL_001",
        "error_msg": "Kernel OOM-killer invoked: process 'postgres' (pid 4821) killed due to memory exhaustion. "
                     "Available: 0 MB, Requested: 512 MB. Swap usage at 100%.",
    },
    {
        "error_code": "DISK_FULL_002",
        "error_msg": "Filesystem /dev/sda1 at 100% capacity. Write operations failing with ENOSPC. "
                     "Inode exhaustion detected: 0 inodes free.",
    },
    {
        "error_code": "CPU_THERMAL_003",
        "error_msg": "CPU core temperature exceeded 95°C threshold (current: 102°C). "
                     "Thermal throttling engaged. Risk of hardware damage imminent.",
    },
    {
        "error_code": "NET_PARTITION_004",
        "error_msg": "Network partition detected. Node cannot reach cluster quorum peers "
                     "[10.0.1.12, 10.0.1.13]. Split-brain scenario possible. Heartbeat timeout: 30s.",
    },
    {
        "error_code": "KERNEL_PANIC_005",
        "error_msg": "Kernel panic — not syncing: Fatal exception in interrupt. "
                     "EIP: 0060:[<c0105704>] Tainted: G. Last good known state lost.",
    },
]

_SERVER_IDS = ["srv-dc1-001", "srv-dc1-002", "srv-dc1-003", "srv-dc2-001", "srv-dc2-002"]
_REGIONS    = ["us-east-1",   "us-east-1",   "us-east-1",   "eu-west-2",   "eu-west-2"]


def get_latest_server_logs() -> str:
    """
    Simulates fetching the latest aggregated server health logs from the
    DataVita monitoring platform. Returns a JSON-encoded cluster snapshot.

    In production this would call the internal metrics API endpoint.
    For simulation purposes, one server is randomly selected to be in a
    CRITICAL state with a realistic fault scenario, otherwise all servers
    are ONLINE.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    servers = []
    critical_index = random.choice(range(len(_SERVER_IDS)))        # may be suppressed below
    inject_fault   = random.random() < 0.70                        # 70% chance of a fault

    for i, (srv_id, region) in enumerate(zip(_SERVER_IDS, _REGIONS)):
        if inject_fault and i == critical_index:
            fault = random.choice(_FAULT_SCENARIOS)
            servers.append({
                "server_id":   srv_id,
                "region":      region,
                "status":      "CRITICAL",
                "cpu_pct":     round(random.uniform(88, 100), 1),
                "mem_pct":     round(random.uniform(90, 100), 1),
                "disk_pct":    round(random.uniform(85, 100), 1),
                "uptime_days": round(random.uniform(0.1, 2.0),  2),
                "error_code":  fault["error_code"],
                "error_msg":   fault["error_msg"],
                "timestamp":   now_iso,
            })
        else:
            servers.append({
                "server_id":   srv_id,
                "region":      region,
                "status":      "ONLINE",
                "cpu_pct":     round(random.uniform(10, 55), 1),
                "mem_pct":     round(random.uniform(20, 65), 1),
                "disk_pct":    round(random.uniform(15, 70), 1),
                "uptime_days": round(random.uniform(3, 180),  1),
                "error_code":  None,
                "error_msg":   None,
                "timestamp":   now_iso,
            })

    payload = {
        "cluster":        "datavita-prod",
        "snapshot_time":  now_iso,
        "total_servers":  len(servers),
        "critical_count": sum(1 for s in servers if s["status"] == "CRITICAL"),
        "servers":        servers,
    }
    return json.dumps(payload, indent=2)
