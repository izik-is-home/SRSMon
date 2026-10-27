import asyncio
import datetime
import time
from collections import deque
from typing import Dict, List, Any, Optional
from backend.config import settings
from backend.database import execute_query, execute_write
from backend.collector.srs_client import srs_client
from backend.alert_engine import alert_engine
from backend.collector.parsers import parse_raw_disk_space, parse_raw_who_sqm

class RingBuffer:
    """Ring buffer holding the last N minutes of data in memory for instantaneous dashboard queries."""
    def __init__(self, maxlen: int = 120): # 120 entries @ 15s = 30 minutes
        self.buffer = deque(maxlen=maxlen)

    def append(self, item: Any):
        self.buffer.append(item)

    def get_all(self) -> List[Any]:
        return list(self.buffer)

class CollectorEngine:
    def __init__(self):
        self.is_running = False
        self.ring_buffers: Dict[int, RingBuffer] = {}
        self.latest_snapshots: Dict[int, Dict[str, Any]] = {}
        self.circuit_breaker_degraded: Dict[int, bool] = {}

    def get_ring_buffer(self, server_id: int) -> RingBuffer:
        if server_id not in self.ring_buffers:
            self.ring_buffers[server_id] = RingBuffer(maxlen=120)
        return self.ring_buffers[server_id]

    async def run(self):
        self.is_running = True
        print("[Collector] Background collector started...")
        step = 0
        while self.is_running:
            try:
                servers = execute_query("SELECT server_id, server_name FROM monitored_servers WHERE is_active = 1")
                for srv in servers:
                    srv_id = srv["server_id"]
                    sim = srs_client.get_simulator(srv_id)

                    start_time = time.perf_counter()

                    connector = srs_client.get_connector(srv_id)
                    if settings.DATA_MODE == "live" and connector:
                        raw_disk = connector.run_srs_admin("admin disk_space")
                        partitions = parse_raw_disk_space(raw_disk)
                        if not partitions:
                            partitions = sim.collect_partition_metrics()

                        raw_sqm = connector.run_srs_admin("admin who, sqm")
                        queues = parse_raw_who_sqm(raw_sqm)
                        if not queues:
                            queues = sim.collect_queue_metrics()

                        threads = sim.collect_threads_status()
                    else:
                        # 1. Core polling via high-fidelity simulator
                        partitions = sim.collect_partition_metrics()
                        queues = sim.collect_queue_metrics()
                        threads = sim.collect_threads_status()

                    # 2. Primary ASE Blocker (every 30s)
                    lead_blocker = None
                    if step % 2 == 0:
                        lead_blocker = sim.get_lead_blocker("102:1 ERP_DS.erpdb")

                    # Circuit Breaker check
                    elapsed = time.perf_counter() - start_time
                    if elapsed > 2.0:
                        self.circuit_breaker_degraded[srv_id] = True
                        print(f"[CircuitBreaker] Response time {elapsed:.2f}s > 2s on Server {srv_id}. Status marked as DEGRADED.")
                    else:
                        self.circuit_breaker_degraded[srv_id] = False

                    # 3. Alerting engine evaluation
                    new_alerts = alert_engine.process_telemetry(
                        server_id=srv_id,
                        partitions=partitions,
                        queues=queues,
                        threads=threads,
                        lead_blocker=lead_blocker
                    )

                    # 4. Compute Health Status
                    unresolved_alerts = execute_query(
                        "SELECT severity FROM system_alerts WHERE server_id = ? AND resolved_at IS NULL",
                        (srv_id,)
                    )
                    has_critical = any(a["severity"] == "CRITICAL" for a in unresolved_alerts)
                    has_warning = any(a["severity"] == "WARNING" for a in unresolved_alerts)
                    
                    if self.circuit_breaker_degraded.get(srv_id, False):
                        system_health = "DEGRADED"
                    elif has_critical:
                        system_health = "CRITICAL"
                    elif has_warning:
                        system_health = "WARNING"
                    else:
                        system_health = "HEALTHY"

                    # Threads summary
                    total_threads = len(threads)
                    active_threads = sum(1 for t in threads if t["state"].upper() == "ACTIVE")
                    suspended_threads = sum(1 for t in threads if t["state"].upper() == "SUSPENDED")
                    down_threads = sum(1 for t in threads if t["state"].upper() == "DOWN")
                    awaiting_threads = sum(1 for t in threads if "AWAITING" in t["state"].upper())

                    max_lag = max([q["lag_seconds"] for q in queues] + [0.0])

                    snapshot = {
                        "server_id": srv_id,
                        "server_name": srv["server_name"],
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "system_health": system_health,
                        "quiesce_status": False,
                        "threads_summary": {
                            "total": total_threads,
                            "active": active_threads,
                            "suspended": suspended_threads,
                            "down": down_threads,
                            "awaiting": awaiting_threads
                        },
                        "overall_lag_seconds": round(max_lag, 2),
                        "partitions": partitions,
                        "queues": queues,
                        "threads": threads,
                        "lead_blocker": lead_blocker,
                        "active_alerts_count": len(unresolved_alerts)
                    }

                    # Store in snapshot & RingBuffer
                    self.latest_snapshots[srv_id] = snapshot
                    self.get_ring_buffer(srv_id).append(snapshot)

                    # Persist to database (sample save)
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    for p in partitions:
                        execute_write("""
                        INSERT INTO partition_metrics (timestamp, server_id, partition_name, logical_name, partition_id, total_mb, used_mb, free_pct, device_state)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (now_iso, srv_id, p["partition_name"], p["logical_name"], p["partition_id"], p["total_mb"], p["used_mb"], p["free_pct"], p["device_state"]))

                    for q in queues:
                        execute_write("""
                        INSERT INTO queue_metrics (timestamp, server_id, queue_name, queue_type, size_mb, first_seg_block, last_seg_block, next_read, readers_count, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (now_iso, srv_id, q["queue_name"], q["queue_type"], q["size_mb"], q["first_seg_block"], q["last_seg_block"], q["next_read"], q["readers_count"], q["status"]))

                step += 1
            except Exception as e:
                print(f"[Collector Error] {e}")

            # Core polling interval is 15s in production, for responsive local demo we sample every 5s
            await asyncio.sleep(5)

collector_engine = CollectorEngine()
