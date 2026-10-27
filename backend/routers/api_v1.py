from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import datetime
from backend.database import execute_query, execute_write
from backend.collector.engine import collector_engine
from backend.collector.srs_client import srs_client

router = APIRouter(prefix="/api/v1", tags=["SRS Monitoring API v1"])

class AdminCommandRequest(BaseModel):
    command: str

class ScenarioRequest(BaseModel):
    scenario: str
    enable: bool = True

@router.get("/servers")
def get_monitored_servers():
    """Returns list of all monitored SAP Replication Servers."""
    return execute_query("SELECT * FROM monitored_servers ORDER BY server_id ASC")

@router.get("/servers/{server_id}/health")
def get_server_health(server_id: int):
    """GET /api/v1/servers/{server_id}/health matching specification section 4."""
    snapshot = collector_engine.latest_snapshots.get(server_id)
    if not snapshot:
        # Fallback if collector hasn't completed first cycle yet
        sim = srs_client.get_simulator(server_id)
        parts = sim.collect_partition_metrics()
        queues = sim.collect_queue_metrics()
        threads = sim.collect_threads_status()
        return {
            "server_id": server_id,
            "server_name": f"REP_SRV_{server_id}",
            "status": "HEALTHY",
            "quiesce_status": False,
            "threads_summary": {"total": len(threads), "active": len(threads)-1, "suspended": 1, "down": 0, "awaiting": 0},
            "overall_lag_seconds": 1.45,
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    return {
        "server_id": snapshot["server_id"],
        "server_name": snapshot["server_name"],
        "status": snapshot["system_health"],
        "quiesce_status": snapshot["quiesce_status"],
        "threads_summary": snapshot["threads_summary"],
        "overall_lag_seconds": snapshot["overall_lag_seconds"],
        "active_alerts_count": snapshot["active_alerts_count"],
        "last_updated": snapshot["timestamp"]
    }

@router.get("/servers/{server_id}/partitions")
def get_server_partitions(server_id: int):
    """GET /api/v1/servers/{server_id}/partitions matching specification section 4."""
    snapshot = collector_engine.latest_snapshots.get(server_id)
    if snapshot:
        return snapshot["partitions"]
    sim = srs_client.get_simulator(server_id)
    return sim.collect_partition_metrics()

@router.get("/servers/{server_id}/queues")
def get_server_queues(server_id: int):
    """GET /api/v1/servers/{server_id}/queues matching specification section 4."""
    snapshot = collector_engine.latest_snapshots.get(server_id)
    if snapshot:
        return snapshot["queues"]
    sim = srs_client.get_simulator(server_id)
    return sim.collect_queue_metrics()

@router.get("/servers/{server_id}/queues/{queue_id}/blockers")
def get_queue_lead_blocker(server_id: int, queue_id: str):
    """GET /api/v1/servers/{server_id}/queues/{queue_id}/blockers matching specification section 4."""
    sim = srs_client.get_simulator(server_id)
    blocker_info = sim.get_lead_blocker(queue_id)
    if not blocker_info:
        return {
            "queue_name": queue_id,
            "primary_database": "erpdb",
            "lead_blocker": None,
            "message": "No active transactions currently blocking Secondary Truncation Point."
        }
    return blocker_info

@router.get("/servers/{server_id}/threads")
def get_server_threads(server_id: int):
    """Returns thread status for the specified server."""
    snapshot = collector_engine.latest_snapshots.get(server_id)
    if snapshot:
        return snapshot["threads"]
    sim = srs_client.get_simulator(server_id)
    return sim.collect_threads_status()

@router.get("/servers/{server_id}/history")
def get_server_history(server_id: int, range_hours: int = Query(default=1)):
    """Returns time-series history from RingBuffer for dual-axis trend canvas."""
    ring_buf = collector_engine.get_ring_buffer(server_id)
    items = ring_buf.get_all()
    history = []
    for snap in items:
        tot_queue_mb = sum(q.get("size_mb", 0.0) for q in snap.get("queues", []))
        in_tput = sum(q.get("throughput_mb_sec", 0.0) for q in snap.get("queues", []) if q.get("queue_type") == "Inbound")
        out_tput = sum(q.get("throughput_mb_sec", 0.0) for q in snap.get("queues", []) if q.get("queue_type") == "Outbound")
        history.append({
            "timestamp": snap.get("timestamp"),
            "total_queue_mb": round(tot_queue_mb, 1),
            "inbound_throughput_mb_sec": round(in_tput, 2),
            "outbound_throughput_mb_sec": round(out_tput, 2),
            "overall_lag_seconds": snap.get("overall_lag_seconds", 0.0)
        })
    return history

@router.get("/alerts")
def get_system_alerts(active_only: bool = Query(default=True)):
    """Returns active or all system alerts."""
    if active_only:
        return execute_query("SELECT * FROM system_alerts WHERE resolved_at IS NULL ORDER BY alert_id DESC")
    return execute_query("SELECT * FROM system_alerts ORDER BY alert_id DESC LIMIT 100")

@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int):
    """Acknowledge / resolve an alert."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    execute_write("UPDATE system_alerts SET resolved_at = ? WHERE alert_id = ?", (now_iso, alert_id))
    return {"status": "success", "alert_id": alert_id, "resolved_at": now_iso}

@router.post("/servers/{server_id}/admin_cmd")
def execute_admin_cmd(server_id: int, req: AdminCommandRequest):
    """DBA Diagnostic Console: Executes SRS admin commands."""
    return srs_client.execute_admin_command(server_id=server_id, cmd=req.command)

@router.post("/servers/{server_id}/simulate_scenario")
def simulate_scenario(server_id: int, req: ScenarioRequest):
    """DBA Simulation Controls: Injects or clears test scenarios."""
    sim = srs_client.get_simulator(server_id)
    return sim.trigger_scenario(req.scenario, req.enable)

@router.get("/servers/{server_id}/topology")
def get_replication_topology(server_id: int):
    """
    Returns Multi-Site Topology DAG (Primary ASE -> SRS -> Queues -> Targets)
    as outlined in section 5 (Future extensions & Topology visualization).
    """
    return {
        "server_id": server_id,
        "nodes": [
            {"id": "primary_erp", "name": "ERP_PROD (Primary ASE)", "type": "primary_db", "status": "HEALTHY", "host": "ase-erp-01:5000", "dbname": "erpdb"},
            {"id": "rep_agent_erp", "name": "RepAgent (erpdb)", "type": "rep_agent", "status": "HEALTHY", "tps": 135.0},
            {"id": "srs_core", "name": "REP_PROD_01 (SRS 15.7)", "type": "replication_server", "status": "WARNING", "host": "srs-prod-01:5005"},
            {"id": "q_in_erp", "name": "102:1 ERP Inbound Queue", "type": "inbound_queue", "size_mb": 12450.0, "status": "HEALTHY"},
            {"id": "dist", "name": "DIST Thread (Distributor)", "type": "dist_thread", "status": "HEALTHY"},
            {"id": "q_out_crm", "name": "103:0 CRM Outbound Queue", "type": "outbound_queue", "size_mb": 120.0, "status": "SUSPENDED"},
            {"id": "q_out_bi", "name": "104:0 BI Outbound Queue", "type": "outbound_queue", "size_mb": 3850.0, "status": "HEALTHY"},
            {"id": "dsi_crm", "name": "DSI CRM_DS.crmdb", "type": "dsi_thread", "status": "SUSPENDED"},
            {"id": "dsi_bi", "name": "DSI BI_DS.dwdb", "type": "dsi_thread", "status": "HEALTHY"},
            {"id": "rep_dr", "name": "REP_DR_02 (RSI Route)", "type": "rsi_target", "status": "HEALTHY"},
            {"id": "db_crm", "name": "CRM_DS (Replicate DB)", "type": "target_db", "status": "SUSPENDED"},
            {"id": "db_dw", "name": "BI_DS (Replicate DB)", "type": "target_db", "status": "HEALTHY"}
        ],
        "links": [
            {"source": "primary_erp", "target": "rep_agent_erp", "label": "TDS Log Scan"},
            {"source": "rep_agent_erp", "target": "q_in_erp", "label": "Stream Changes"},
            {"source": "q_in_erp", "target": "dist", "label": "Read & Parse"},
            {"source": "dist", "target": "q_out_crm", "label": "Route CRM"},
            {"source": "dist", "target": "q_out_bi", "label": "Route BI"},
            {"source": "dist", "target": "rep_dr", "label": "RSI Sync"},
            {"source": "q_out_crm", "target": "dsi_crm", "label": "DSI Apply"},
            {"source": "q_out_bi", "target": "dsi_bi", "label": "DSI Apply"},
            {"source": "dsi_crm", "target": "db_crm", "label": "Target DDL/DML"},
            {"source": "dsi_bi", "target": "db_dw", "label": "Target DDL/DML"}
        ]
    }
