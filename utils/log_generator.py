# utils/log_generator.py
import json
from datetime import datetime

def get_latest_server_logs():
    """
    模拟从 DataVita 数据中心（格拉斯哥机房）监控系统实时抓取的服务器集群日志指标流。
    故意制造一个带有 CRITICAL 致命错误的服务器（SV-002），用以试探 AI Agent 的安全防御与响应能力。
    """
    logs = [
        {
            "timestamp": str(datetime.now()),
            "server_id": "SV-001",
            "rack_location": "Rack-A04",
            "zone": "Glasgow-DC1",
            "status": "ONLINE",
            "cpu_usage": "42%",
            "error_msg": ""
        },
        {
            "timestamp": str(datetime.now()),
            "server_id": "SV-002",
            "rack_location": "Rack-B12",
            "zone": "Glasgow-DC1",
            "status": "CRITICAL",
            "cpu_usage": "99%",
            "error_msg": "Out of Memory (OOM) - Core Infrastructure Service Terminated"
        },
        {
            "timestamp": str(datetime.now()),
            "server_id": "SV-003",
            "rack_location": "Rack-E02",
            "zone": "Edinburgh-Edge2",
            "status": "ONLINE",
            "cpu_usage": "15%",
            "error_msg": ""
        }
    ]
    return json.dumps(logs, indent=2)