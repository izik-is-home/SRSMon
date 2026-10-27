import os
import json
from pydantic import BaseModel
from typing import Optional

class AppConfig(BaseModel):
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Polling & Intervals
    POLL_INTERVAL_CORE_SEC: int = 15     # Stable storage, sqm queues, threads
    POLL_INTERVAL_PRIMARY_SEC: int = 30  # Primary ASE blocker check
    POLL_INTERVAL_PERF_SEC: int = 60     # admin stats, tps, backlog
    WS_PUSH_INTERVAL_SEC: int = 5        # WebSocket broadcast interval
    
    # Alerting Thresholds
    PARTITION_WARN_FREE_PCT: float = 15.0
    PARTITION_CRIT_FREE_PCT: float = 5.0
    QUEUE_SPIKE_GB_CRIT: float = 10.0
    QUEUE_SPIKE_GROWTH_PCT: float = 20.0
    QUEUE_SPIKE_WINDOW_MIN: int = 10
    LATENCY_WARN_SEC: float = 300.0
    BLOCKER_WARN_MINUTES: int = 30
    
    # Mode: 'simulation' or 'live'
    DATA_MODE: str = os.getenv("SRSMON_DATA_MODE", "simulation")
    
    # Metrics Storage Database Backend: 'ase' (SAP Sybase ASE 16) or 'sqlite'
    DB_BACKEND: str = os.getenv("SRSMON_DB_BACKEND", "ase")
    
    # SAP Sybase ASE 16 Settings (TESTDB / INFODB on 10.0.0.18:5002)
    ASE_SERVER_NAME: str = os.getenv("SRSMON_ASE_SERVER", "TESTDB")
    ASE_HOST: str = os.getenv("SRSMON_ASE_HOST", "10.0.0.18")
    ASE_PORT: int = int(os.getenv("SRSMON_ASE_PORT", "5002"))
    ASE_DATABASE: str = os.getenv("SRSMON_ASE_DATABASE", "INFODB")
    ASE_USER: str = os.getenv("SRSMON_ASE_USER", "sa")
    ASE_PASSWORD: str = os.getenv("SRSMON_ASE_PASSWORD", "")
    ASE_DRIVER: str = os.getenv("SRSMON_ASE_DRIVER", "Adaptive Server Enterprise")

    # SQLite Database Fallback Path
    DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "srsmon_metrics.db")

def load_settings() -> AppConfig:
    conf = AppConfig()
    cfg_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "srs_config.json")
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                ms = data.get("metrics_storage", {})
                if ms:
                    conf.DB_BACKEND = ms.get("backend", conf.DB_BACKEND)
                    conf.ASE_SERVER_NAME = ms.get("server_alias", conf.ASE_SERVER_NAME)
                    conf.ASE_HOST = ms.get("host", conf.ASE_HOST)
                    conf.ASE_PORT = int(ms.get("port", conf.ASE_PORT))
                    conf.ASE_DATABASE = ms.get("database", conf.ASE_DATABASE)
                    conf.ASE_USER = ms.get("user", conf.ASE_USER)
                    conf.ASE_PASSWORD = ms.get("password", conf.ASE_PASSWORD)
                    conf.ASE_DRIVER = ms.get("driver", conf.ASE_DRIVER)
        except Exception as e:
            print(f"[SRSMon Config Warning] Error loading srs_config.json: {e}")
    return conf

settings = load_settings()
