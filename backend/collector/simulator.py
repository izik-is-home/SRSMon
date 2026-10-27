import datetime
import random
from typing import List, Dict, Any
from backend.collector.parsers import calculate_queue_size_mb

class SRSSimulator:
    """
    High-fidelity stateful simulator for SAP Replication Server 15.7
    and Primary SAP ASE database.
    Allows DBA testing with dynamic time-series fluctuations and
    scenario injections (spikes, suspended threads, lead blockers).
    """
    def __init__(self, server_id: int = 1, server_name: str = "REP_PROD_01"):
        self.server_id = server_id
        self.server_name = server_name
        self.simulation_step = 0
        
        # Scenarios state
        self.spike_active = False
        self.spike_magnitude_mb = 0.0
        self.crm_dsi_suspended = True
        self.low_partition_space = True
        self.has_active_blocker = True
        self.blocker_spid = 348
        self.blocker_duration_seconds = 12450
        
        # Partitions
        self.partitions = [
            {
                "partition_id": 101,
                "logical_name": "partition_1",
                "device_path": "/sybase/srs_devices/part01.dat",
                "total_mb": 102400.0,
                "used_mb": 79872.0,
                "state": "ON-LINE",
                "base_growth_rate": 8.5 # MB/min
            },
            {
                "partition_id": 102,
                "logical_name": "partition_2",
                "device_path": "/sybase/srs_devices/part02.dat",
                "total_mb": 102400.0,
                "used_mb": 97280.0, # 95% full
                "state": "ON-LINE",
                "base_growth_rate": 15.0 # MB/min
            },
            {
                "partition_id": 103,
                "logical_name": "partition_3",
                "device_path": "/sybase/srs_devices/part03.dat",
                "total_mb": 204800.0,
                "used_mb": 92160.0, # 45% full
                "state": "ON-LINE",
                "base_growth_rate": 2.0
            }
        ]
        
        # Queues
        self.queues = [
            {
                "queue_name": "102:1 ERP_DS.erpdb",
                "queue_type": "Inbound",
                "base_size_mb": 12450.0,
                "status": "Active",
                "first_seg": 1420,
                "first_block": 12,
                "readers": 2,
                "lag_seconds": 1.4,
                "base_throughput": 4.8
            },
            {
                "queue_name": "103:0 CRM_DS.crmdb",
                "queue_type": "Outbound",
                "base_size_mb": 120.0,
                "status": "Suspended",
                "first_seg": 500,
                "first_block": 0,
                "readers": 0,
                "lag_seconds": 185.0,
                "base_throughput": 0.0
            },
            {
                "queue_name": "104:0 BI_DS.dwdb",
                "queue_type": "Outbound",
                "base_size_mb": 3850.0,
                "status": "Active",
                "first_seg": 820,
                "first_block": 4,
                "readers": 4,
                "lag_seconds": 12.8,
                "base_throughput": 8.5
            },
            {
                "queue_name": "105:1 HR_DS.hrdb",
                "queue_type": "Inbound",
                "base_size_mb": 85.0,
                "status": "Active",
                "first_seg": 210,
                "first_block": 1,
                "readers": 1,
                "lag_seconds": 0.4,
                "base_throughput": 1.2
            },
            {
                "queue_name": "106:0 AUDIT_DS.auditdb",
                "queue_type": "Outbound",
                "base_size_mb": 420.0,
                "status": "Active",
                "first_seg": 310,
                "first_block": 18,
                "readers": 1,
                "lag_seconds": 2.1,
                "base_throughput": 0.9
            }
        ]

    def trigger_scenario(self, scenario_name: str, enable: bool = True) -> Dict[str, Any]:
        """Allows DBA to trigger simulated scenarios for testing."""
        if scenario_name == "spike":
            self.spike_active = enable
            self.spike_magnitude_mb = 14500.0 if enable else 0.0
            return {"scenario": "spike", "status": enable, "message": f"Inbound 15GB spike {'activated' if enable else 'cleared'}"}
        elif scenario_name == "crm_dsi_suspend":
            self.crm_dsi_suspended = enable
            for q in self.queues:
                if "CRM_DS" in q["queue_name"]:
                    q["status"] = "Suspended" if enable else "Active"
                    q["lag_seconds"] = 185.0 if enable else 1.1
                    q["base_throughput"] = 0.0 if enable else 3.2
            return {"scenario": "crm_dsi_suspend", "status": enable, "message": f"CRM DSI {'suspended' if enable else 'resumed'}"}
        elif scenario_name == "kill_blocker":
            self.has_active_blocker = not enable
            return {"scenario": "kill_blocker", "status": enable, "message": f"SPID {self.blocker_spid} {'terminated' if enable else 'restored'}"}
        elif scenario_name == "partition_critical":
            self.low_partition_space = enable
            self.partitions[1]["used_mb"] = 99800.0 if enable else 82000.0
            return {"scenario": "partition_critical", "status": enable, "message": f"Partition 2 set to {'97.5% critical' if enable else '80% normal'}"}
        return {"error": f"Unknown scenario {scenario_name}"}

    def collect_partition_metrics(self) -> List[Dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc)
        results = []
        for p in self.partitions:
            noise = (random.random() - 0.48) * 12.0
            used = p["used_mb"] + noise
            if self.spike_active and p["partition_id"] == 102:
                used += 1200.0
            used = min(p["total_mb"] - 100.0, max(1000.0, used))
            p["used_mb"] = used
            
            free_mb = round(p["total_mb"] - used, 2)
            used_pct = round((used / p["total_mb"]) * 100.0, 2)
            free_pct = round(100.0 - used_pct, 2)
            
            # Predict hours until full
            growth_mb_per_hour = p["base_growth_rate"] * 60.0
            if self.spike_active and p["partition_id"] == 102:
                growth_mb_per_hour *= 4.0
            est_hours = round(free_mb / max(0.1, growth_mb_per_hour), 1) if free_mb > 0 else 0.0

            results.append({
                "server_id": self.server_id,
                "timestamp": now.isoformat(),
                "partition_id": p["partition_id"],
                "logical_name": p["logical_name"],
                "partition_name": p["device_path"],
                "total_mb": p["total_mb"],
                "used_mb": round(used, 2),
                "free_mb": free_mb,
                "used_percent": used_pct,
                "free_pct": free_pct,
                "device_state": p["state"],
                "estimated_hours_until_full": est_hours
            })
        return results

    def collect_queue_metrics(self) -> List[Dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc)
        results = []
        for q in self.queues:
            size_mb = q["base_size_mb"] + (random.random() - 0.5) * 50.0
            if self.spike_active and q["queue_type"] == "Inbound" and "ERP_DS" in q["queue_name"]:
                size_mb += self.spike_magnitude_mb
            size_mb = max(0.0, round(size_mb, 2))
            
            # compute block offset representation
            total_blocks = int((size_mb * 1024.0) / 16.0)
            added_segs = total_blocks // 64
            rem_blocks = total_blocks % 64
            
            first_seg_block = f"{q['first_seg']}.{q['first_block']}"
            last_seg_block = f"{q['first_seg'] + added_segs}.{rem_blocks}"
            next_read = f"{q['first_seg'] + added_segs//2}.{rem_blocks//2}.1"
            
            lag = q["lag_seconds"] + (random.random() - 0.5) * 0.4
            if self.crm_dsi_suspended and "CRM_DS" in q["queue_name"]:
                lag = q["lag_seconds"] + (self.simulation_step * 5)
            lag = max(0.1, round(lag, 1))

            throughput = max(0.0, round(q["base_throughput"] + (random.random() - 0.5) * 0.8, 2))
            if q["status"] == "Suspended":
                throughput = 0.0

            results.append({
                "server_id": self.server_id,
                "timestamp": now.isoformat(),
                "queue_name": q["queue_name"],
                "queue_type": q["queue_type"],
                "size_mb": size_mb,
                "status": q["status"],
                "first_seg_block": first_seg_block,
                "last_seg_block": last_seg_block,
                "next_read": next_read,
                "readers_count": q["readers"],
                "lag_seconds": lag,
                "throughput_mb_sec": throughput
            })
        self.simulation_step += 1
        return results

    def collect_threads_status(self) -> List[Dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc)
        threads = [
            {"spid": 14, "type": "DIST", "target": "ERP_DS.erpdb", "state": "Active", "lag": 0.2, "tps": 120.0},
            {"spid": 18, "type": "DSI", "target": "CRM_DS.crmdb", "state": "Suspended" if self.crm_dsi_suspended else "Active", "lag": 185.0 if self.crm_dsi_suspended else 1.2, "tps": 0.0 if self.crm_dsi_suspended else 45.0},
            {"spid": 22, "type": "DSI", "target": "BI_DS.dwdb", "state": "Active", "lag": 12.5, "tps": 210.0},
            {"spid": 26, "type": "DSI", "target": "AUDIT_DS.auditdb", "state": "Active", "lag": 2.1, "tps": 15.0},
            {"spid": 31, "type": "REP AGENT", "target": "ERP_PROD.erpdb", "state": "Active", "lag": 0.1, "tps": 135.0},
            {"spid": 34, "type": "REP AGENT", "target": "HR_PROD.hrdb", "state": "Active", "lag": 0.1, "tps": 12.0},
            {"spid": 39, "type": "RSI", "target": "REP_DR_02", "state": "Active", "lag": 3.4, "tps": 75.0},
            {"spid": 42, "type": "SQM", "target": "102:1 ERP_DS.erpdb", "state": "Active", "lag": 0.0, "tps": 0.0},
            {"spid": 43, "type": "SQT", "target": "102:1 ERP_DS.erpdb", "state": "Active", "lag": 0.0, "tps": 0.0},
        ]
        results = []
        for t in threads:
            results.append({
                "server_id": self.server_id,
                "timestamp": now.isoformat(),
                "thread_spid": t["spid"],
                "thread_type": t["type"],
                "target_connection": t["target"],
                "state": t["state"],
                "lag_seconds": t["lag"],
                "throughput_tps": t["tps"]
            })
        return results

    def get_lead_blocker(self, queue_name: str) -> Optional[Dict[str, Any]]:
        """
        Returns the oldest transaction blocking the Secondary Truncation Point
        in Primary ASE (master..sysprocesses / master..syslogshold).
        """
        if not self.has_active_blocker:
            return None
        
        # Primary blocker only affects erpdb inbound queue
        if "erpdb" not in queue_name and "102:1" not in queue_name:
            return None

        login_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=self.blocker_duration_seconds)
        return {
            "queue_name": queue_name,
            "primary_database": "erpdb",
            "lead_blocker": {
                "spid": self.blocker_spid,
                "transaction_name": "$batch_update",
                "status": "running",
                "login_time": login_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "duration_seconds": self.blocker_duration_seconds,
                "duration_formatted": "3h 27m 30s",
                "hostname": "app-worker-09",
                "program_name": "SAP_BATCH_APPL",
                "cmd": "UPDATE",
                "impact": "Holding Secondary Truncation Point in master..syslogshold, preventing log truncation and causing Inbound Queue expansion.",
                "recommended_action": f"Examine application batch query or execute 'KILL {self.blocker_spid}' on Primary ASE."
            }
        }
