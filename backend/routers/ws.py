import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, Dict, Any
from backend.collector.engine import collector_engine

router = APIRouter(tags=["WebSockets"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.client_subscriptions: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.client_subscriptions[websocket] = {"server_id": 1, "interval_seconds": 5}

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self.client_subscriptions.pop(websocket, None)

    async def update_subscription(self, websocket: WebSocket, data: Dict[str, Any]):
        sub = self.client_subscriptions.get(websocket, {})
        sub["server_id"] = int(data.get("server_id", sub.get("server_id", 1)))
        sub["interval_seconds"] = int(data.get("interval_seconds", 5))
        self.client_subscriptions[websocket] = sub

manager = ConnectionManager()

@router.websocket("/ws/v1/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Task for receiving client messages (like subscribe / interval change)
        async def client_listener():
            while True:
                msg_text = await websocket.receive_text()
                try:
                    data = json.loads(msg_text)
                    if data.get("action") == "subscribe":
                        await manager.update_subscription(websocket, data)
                except Exception:
                    pass

        listener_task = asyncio.create_task(client_listener())

        # Push loop
        while True:
            sub = manager.client_subscriptions.get(websocket, {"server_id": 1, "interval_seconds": 5})
            srv_id = sub.get("server_id", 1)
            snapshot = collector_engine.latest_snapshots.get(srv_id)

            if snapshot:
                # Format payload matching specification section 4.2
                payload = {
                    "event": "METRICS_UPDATE",
                    "server_id": srv_id,
                    "server_name": snapshot.get("server_name"),
                    "timestamp": snapshot.get("timestamp"),
                    "system_health": snapshot.get("system_health"),
                    "quiesce_status": snapshot.get("quiesce_status"),
                    "threads_summary": snapshot.get("threads_summary"),
                    "overall_lag_seconds": snapshot.get("overall_lag_seconds"),
                    "active_alerts_count": snapshot.get("active_alerts_count"),
                    "partitions": [
                        {
                            "partition_id": p.get("partition_id"),
                            "name": p.get("logical_name"),
                            "device_path": p.get("partition_name"),
                            "total_mb": p.get("total_mb"),
                            "used_mb": p.get("used_mb"),
                            "free_mb": p.get("free_mb"),
                            "used_pct": p.get("used_percent"),
                            "state": p.get("device_state"),
                            "estimated_hours_until_full": p.get("estimated_hours_until_full")
                        }
                        for p in snapshot.get("partitions", [])
                    ],
                    "queues": [
                        {
                            "name": q.get("queue_name"),
                            "type": q.get("queue_type"),
                            "size_mb": q.get("size_mb"),
                            "status": q.get("status"),
                            "first_seg_block": q.get("first_seg_block"),
                            "last_seg_block": q.get("last_seg_block"),
                            "next_read": q.get("next_read"),
                            "readers": q.get("readers_count"),
                            "lag": q.get("lag_seconds"),
                            "throughput_mb_sec": q.get("throughput_mb_sec")
                        }
                        for q in snapshot.get("queues", [])
                    ],
                    "threads": snapshot.get("threads", []),
                    "lead_blocker": snapshot.get("lead_blocker")
                }
                await websocket.send_text(json.dumps(payload))

            interval = sub.get("interval_seconds", 5)
            await asyncio.sleep(max(1, interval))

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
