import datetime
from typing import Dict, List, Any, Optional
from backend.config import settings
from backend.database import execute_query, execute_write

class AlertEngine:
    """
    Alert Engine with Debouncing / Hysteresis per SRS 15.7 specification:
    - Partition Warning (<15% free, 2 cycles debounce)
    - Partition Critical (<5% free, immediate)
    - Queue Spike (>10GB or +20% over 10m)
    - Thread Down (DSI / DIST / RepAgent Suspended/Down, immediate)
    - High Latency (>300s, 2 cycles debounce)
    - Long-Running Blocker (>30m holding syslogshold)
    """
    def __init__(self):
        # Debounce counters: {entity_key: count}
        self.consecutive_violations: Dict[str, int] = {}
        # Active alert keys: {entity_key: alert_id}
        self.active_alert_keys: Dict[str, int] = {}

    def process_telemetry(self, server_id: int, partitions: List[Dict[str, Any]], queues: List[Dict[str, Any]], threads: List[Dict[str, Any]], lead_blocker: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc)
        current_cycle_keys = set()
        new_alerts = []

        # 1. Partitions evaluation
        for p in partitions:
            free_pct = p.get("free_pct", 100.0)
            part_name = p.get("logical_name", p.get("partition_name", "unknown"))
            key_warn = f"srv{server_id}_part_warn_{part_name}"
            key_crit = f"srv{server_id}_part_crit_{part_name}"

            if free_pct < settings.PARTITION_CRIT_FREE_PCT:
                current_cycle_keys.add(key_crit)
                alert = self._trigger_or_maintain(
                    key=key_crit,
                    server_id=server_id,
                    severity="CRITICAL",
                    category="Partition Capacity",
                    source_entity=part_name,
                    message=f"Critical disk space on {part_name}: Only {free_pct:.1f}% free ({p.get('free_mb', 0)} MB remaining). Est. {p.get('estimated_hours_until_full', 0)}h to full!",
                    immediate=True
                )
                if alert:
                    new_alerts.append(alert)
            elif free_pct < settings.PARTITION_WARN_FREE_PCT:
                current_cycle_keys.add(key_warn)
                alert = self._trigger_or_maintain(
                    key=key_warn,
                    server_id=server_id,
                    severity="WARNING",
                    category="Partition Capacity",
                    source_entity=part_name,
                    message=f"Low disk space on {part_name}: {free_pct:.1f}% free ({p.get('free_mb', 0)} MB remaining).",
                    immediate=False # requires 2 consecutive cycles
                )
                if alert:
                    new_alerts.append(alert)

        # 2. Queues evaluation
        for q in queues:
            q_name = q.get("queue_name", "unknown")
            size_mb = q.get("size_mb", 0.0)
            size_gb = size_mb / 1024.0
            key_q = f"srv{server_id}_q_spike_{q_name}"

            if size_gb >= settings.QUEUE_SPIKE_GB_CRIT:
                current_cycle_keys.add(key_q)
                alert = self._trigger_or_maintain(
                    key=key_q,
                    server_id=server_id,
                    severity="CRITICAL",
                    category="Queue Spike",
                    source_entity=q_name,
                    message=f"Queue size exceeded critical threshold: {size_gb:.2f} GB ({size_mb:,.0f} MB). Risk of stable storage exhaustion.",
                    immediate=True
                )
                if alert:
                    new_alerts.append(alert)

            # High latency check on queues
            lag = q.get("lag_seconds", 0.0)
            key_lag = f"srv{server_id}_lag_{q_name}"
            if lag > settings.LATENCY_WARN_SEC:
                current_cycle_keys.add(key_lag)
                alert = self._trigger_or_maintain(
                    key=key_lag,
                    server_id=server_id,
                    severity="WARNING",
                    category="High Latency",
                    source_entity=q_name,
                    message=f"High replication lag on {q_name}: {lag:.1f} seconds (exceeds {settings.LATENCY_WARN_SEC}s threshold).",
                    immediate=False
                )
                if alert:
                    new_alerts.append(alert)

        # 3. Threads evaluation
        for t in threads:
            t_type = t.get("thread_type", "").upper()
            state = t.get("state", "").upper()
            target = t.get("target_connection", "")
            key_thread = f"srv{server_id}_th_{t_type}_{target}"

            if t_type in ("DSI", "DIST", "REP AGENT") and state in ("SUSPENDED", "DOWN"):
                current_cycle_keys.add(key_thread)
                alert = self._trigger_or_maintain(
                    key=key_thread,
                    server_id=server_id,
                    severity="CRITICAL",
                    category="Thread Down",
                    source_entity=f"{t_type} -> {target}",
                    message=f"Critical thread status: {t_type} thread to {target} is in state {state}!",
                    immediate=True
                )
                if alert:
                    new_alerts.append(alert)

        # 4. Lead Blocker evaluation
        if lead_blocker and "lead_blocker" in lead_blocker:
            b = lead_blocker["lead_blocker"]
            duration_sec = b.get("duration_seconds", 0)
            if duration_sec >= settings.BLOCKER_WARN_MINUTES * 60:
                key_blk = f"srv{server_id}_blocker_{b.get('spid')}"
                current_cycle_keys.add(key_blk)
                alert = self._trigger_or_maintain(
                    key=key_blk,
                    server_id=server_id,
                    severity="WARNING",
                    category="Long-Running Blocker",
                    source_entity=f"SPID {b.get('spid')}",
                    message=f"Transaction '{b.get('transaction_name')}' by SPID {b.get('spid')} ({b.get('program_name')}) running for {duration_sec//60} min, holding Secondary Truncation Point on {lead_blocker.get('primary_database')}.",
                    immediate=False
                )
                if alert:
                    new_alerts.append(alert)

        # 5. Resolve alerts that are no longer violated
        keys_to_resolve = [k for k in self.active_alert_keys if k.startswith(f"srv{server_id}_") and k not in current_cycle_keys]
        for k in keys_to_resolve:
            alert_id = self.active_alert_keys.pop(k, None)
            self.consecutive_violations.pop(k, None)
            if alert_id:
                execute_write(
                    "UPDATE system_alerts SET resolved_at = ? WHERE alert_id = ?",
                    (now.isoformat(), alert_id)
                )

        return new_alerts

    def _trigger_or_maintain(self, key: str, server_id: int, severity: str, category: str, source_entity: str, message: str, immediate: bool) -> Optional[Dict[str, Any]]:
        count = self.consecutive_violations.get(key, 0) + 1
        self.consecutive_violations[key] = count
        
        # Debounce: if not immediate, require at least 2 cycles
        threshold_needed = 1 if immediate else 2
        if count >= threshold_needed and key not in self.active_alert_keys:
            now = datetime.datetime.now(datetime.timezone.utc)
            alert_id = execute_write(
                """
                INSERT INTO system_alerts (server_id, alert_time, severity, category, source_entity, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (server_id, now.isoformat(), severity, category, source_entity, message)
            )
            self.active_alert_keys[key] = alert_id
            return {
                "alert_id": alert_id,
                "server_id": server_id,
                "alert_time": now.isoformat(),
                "severity": severity,
                "category": category,
                "source_entity": source_entity,
                "message": message
            }
        return None

alert_engine = AlertEngine()
