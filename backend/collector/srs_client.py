import subprocess
import shutil
import json
import os
from typing import Dict, Any, List, Optional
from backend.config import settings
from backend.collector.simulator import SRSSimulator
from backend.collector.parsers import (
    calculate_queue_size_mb, 
    parse_queue_type, 
    parse_thread_type,
    parse_raw_disk_space,
    parse_raw_who_sqm
)

class LiveSRSConnector:
    """
    Connects to live SAP Replication Server (SRS) and SAP ASE instances
    using the standard Sybase 'isql' utility or ODBC/TDS.
    """
    def __init__(self, config: Dict[str, Any]):
        self.server_id = config.get("server_id", 1)
        self.server_name = config.get("server_name", "REP_PROD_01")
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 5005)
        self.user = config.get("user", "sa")
        self.password = config.get("password", "")
        self.isql_path = config.get("isql_path", "isql")
        
        # Primary ASE DB config for blocker checking
        self.primary_ase = config.get("primary_ase", {
            "server_name": "ASE_PROD",
            "host": "localhost",
            "port": 5000,
            "user": "sa",
            "password": "",
            "database": "erpdb"
        })

    def run_isql(self, server_target: str, user: str, password: str, sql_commands: str) -> str:
        """Executes commands via isql: isql -S <server> -U <user> -P <password> -w 999 -b"""
        cmd = [self.isql_path, "-S", server_target, "-U", user, "-P", password, "-w", "999", "-b"]
        input_data = f"{sql_commands}\ngo\nquit\n"
        try:
            proc = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=15.0
            )
            return proc.stdout if proc.returncode == 0 else (proc.stdout + "\n" + proc.stderr)
        except Exception as e:
            return f"Error executing isql: {e}"

    def run_srs_admin(self, cmd: str) -> str:
        """Executes an admin command on the Replication Server."""
        target = f"{self.host}:{self.port}"
        return self.run_isql(target, self.user, self.password, cmd)

    def run_primary_sql(self, sql: str) -> str:
        """Executes SQL against Primary SAP ASE."""
        target = f"{self.primary_ase.get('host')}:{self.primary_ase.get('port')}"
        return self.run_isql(target, self.primary_ase.get("user", "sa"), self.primary_ase.get("password", ""), sql)


class SRSClientManager:
    """
    Manages connections to SAP Replication Servers and Primary ASE instances.
    Provides either live query execution or simulator telemetry.
    """
    def __init__(self):
        self.simulators: Dict[int, SRSSimulator] = {
            1: SRSSimulator(server_id=1, server_name="REP_PROD_01"),
            2: SRSSimulator(server_id=2, server_name="REP_DR_02"),
            3: SRSSimulator(server_id=3, server_name="REP_UAT_01")
        }
        self.live_connectors: Dict[int, LiveSRSConnector] = {}
        self.load_live_config()

    def load_live_config(self):
        """Loads live server connection details from srs_config.json if it exists."""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "srs_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for srv in data.get("servers", []):
                        srv_id = srv.get("server_id", 1)
                        self.live_connectors[srv_id] = LiveSRSConnector(srv)
                print(f"[SRSMon] Loaded live connection settings for {len(self.live_connectors)} servers from srs_config.json")
            except Exception as e:
                print(f"[SRSMon] Error reading srs_config.json: {e}")

    def get_simulator(self, server_id: int) -> SRSSimulator:
        if server_id not in self.simulators:
            self.simulators[server_id] = SRSSimulator(server_id=server_id, server_name=f"REP_SRV_{server_id}")
        return self.simulators[server_id]

    def get_connector(self, server_id: int) -> Optional[LiveSRSConnector]:
        return self.live_connectors.get(server_id)

    def execute_admin_command(self, server_id: int, cmd: str) -> Dict[str, Any]:
        """
        Executes an SRS admin command (e.g. 'admin who', 'admin disk_space', 'admin who, sqm').
        In live mode, executes via isql to the real SRS.
        In simulation mode, generates parsed and raw output matching real SAP SRS 15.7.
        """
        connector = self.get_connector(server_id)
        if settings.DATA_MODE == "live" and connector:
            raw_output = connector.run_srs_admin(cmd)
            clean_cmd = cmd.strip().lower()
            parsed = None
            if "disk_space" in clean_cmd:
                parsed = parse_raw_disk_space(raw_output)
            elif "who, sqm" in clean_cmd:
                parsed = parse_raw_who_sqm(raw_output)
            return {
                "command": cmd,
                "server_id": server_id,
                "raw_output": raw_output,
                "parsed": parsed
            }

        # Simulation Mode
        clean_cmd = cmd.strip().lower()
        sim = self.get_simulator(server_id)

        if "disk_space" in clean_cmd:
            parts = sim.collect_partition_metrics()
            raw_lines = [
                "Partition                               Logical         Part.Id  Total Segs  Used Segs   State",
                "--------------------------------------  --------------  -------  ----------  ----------  -------"
            ]
            for p in parts:
                tot_segs = int(p["total_mb"])
                used_segs = int(p["used_mb"])
                raw_lines.append(f"{p['partition_name']:<38}  {p['logical_name']:<14}  {p['partition_id']:<7}  {tot_segs:<10}  {used_segs:<10}  {p['device_state']}")
            return {
                "command": cmd,
                "server_id": server_id,
                "raw_output": "\n".join(raw_lines),
                "parsed": parts
            }
        
        elif "who, sqm" in clean_cmd or "who , sqm" in clean_cmd:
            queues = sim.collect_queue_metrics()
            raw_lines = [
                "Spid  State             Info                     First Seg.Block  Last Seg.Block   Next Read        Readers  Truncs",
                "----  ----------------  -----------------------  ---------------  ---------------  ---------------  -------  ------"
            ]
            spid = 40
            for q in queues:
                raw_lines.append(f"{spid:<4}  {q['status']:<16}  {q['queue_name']:<23}  {q['first_seg_block']:<15}  {q['last_seg_block']:<15}  {q['next_read']:<15}  {q['readers_count']:<7}  1")
                spid += 1
            return {
                "command": cmd,
                "server_id": server_id,
                "raw_output": "\n".join(raw_lines),
                "parsed": queues
            }

        elif "who, sqt" in clean_cmd or "who , sqt" in clean_cmd:
            raw_lines = [
                "Spid  State             Info                     Open Trans  Oldest Trans SPID  Truncation Delay",
                "----  ----------------  -----------------------  ----------  -----------------  ----------------",
                "43    Active            102:1 ERP_DS.erpdb       14          348                3h 27m",
                "44    Active            104:0 BI_DS.dwdb         2           None               0s",
                "45    Suspended         103:0 CRM_DS.crmdb       0           None               0s"
            ]
            return {
                "command": cmd,
                "server_id": server_id,
                "raw_output": "\n".join(raw_lines)
            }

        elif "stats, tps" in clean_cmd:
            raw_lines = [
                "Report: admin stats, tps",
                "Instance: REP_PROD_01",
                "----------------------------------------",
                "Inbound Throughput:      142.5 TPS",
                "DSI CRM_DS.crmdb:          0.0 TPS (Suspended)",
                "DSI BI_DS.dwdb:          210.3 TPS",
                "DSI AUDIT_DS.auditdb:     15.2 TPS",
                "Peak TPS (last 1 hour):  480.0 TPS"
            ]
            return {"command": cmd, "server_id": server_id, "raw_output": "\n".join(raw_lines)}

        elif "health" in clean_cmd:
            raw_lines = [
                "Server Health Check: REP_PROD_01",
                "Overall Status: WARNING",
                "- Partition /sybase/srs_devices/part02.dat is 95% full (CRITICAL)",
                "- Thread DSI CRM_DS.crmdb is Suspended (CRITICAL)",
                "- Secondary Truncation Point held on Primary erpdb by SPID 348 (WARNING)"
            ]
            return {"command": cmd, "server_id": server_id, "raw_output": "\n".join(raw_lines)}

        else: # admin who
            threads = sim.collect_threads_status()
            raw_lines = [
                "Spid  State             Info",
                "----  ----------------  --------------------------------------------------"
            ]
            for t in threads:
                raw_lines.append(f"{t['thread_spid']:<4}  {t['state']:<16}  {t['thread_type']} {t['target_connection']}")
            return {
                "command": cmd,
                "server_id": server_id,
                "raw_output": "\n".join(raw_lines),
                "parsed": threads
            }

srs_client = SRSClientManager()
