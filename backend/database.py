import os
import datetime
from typing import List, Dict, Any, Optional
from backend.config import settings

# Global flag to track whether pyodbc is available
try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    HAS_PYODBC = False

import sqlite3

def get_ase_connection_string() -> str:
    pwd = settings.ASE_PASSWORD if settings.ASE_PASSWORD else ""
    return (
        f"DRIVER={{{settings.ASE_DRIVER}}};"
        f"SERVER={settings.ASE_HOST};"
        f"PORT={settings.ASE_PORT};"
        f"DATABASE={settings.ASE_DATABASE};"
        f"UID={settings.ASE_USER};"
        f"PWD={pwd};"
    )

def get_db_connection():
    if settings.DB_BACKEND == "ase" and HAS_PYODBC:
        try:
            conn_str = get_ase_connection_string()
            return ("ase", pyodbc.connect(conn_str, timeout=10))
        except Exception as e:
            print(f"[SRSMon Database Warning] Failed to connect to SAP ASE ({settings.ASE_HOST}:{settings.ASE_PORT}): {e}")
            print("[SRSMon Database Warning] Falling back to SQLite local storage...")

    # Fallback SQLite
    conn = sqlite3.connect(settings.DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return ("sqlite", conn)

def init_db():
    """Initializes tables on SAP ASE 16 (INFODB) or SQLite."""
    db_type, conn = get_db_connection()
    cursor = conn.cursor()

    if db_type == "ase":
        print(f"[SRSMon Database] Initializing schema on SAP Sybase ASE 16 ({settings.ASE_HOST}:{settings.ASE_PORT} - {settings.ASE_DATABASE})...")
        
        tables_check = [
            ("monitored_servers", """
            CREATE TABLE monitored_servers (
                server_id INT IDENTITY PRIMARY KEY,
                server_name VARCHAR(128) NOT NULL UNIQUE,
                host_address VARCHAR(255) NOT NULL,
                admin_port INT NOT NULL,
                environment VARCHAR(32) DEFAULT 'Production',
                is_active BIT DEFAULT 1,
                created_at DATETIME DEFAULT GETDATE()
            )
            """),
            ("partition_metrics", """
            CREATE TABLE partition_metrics (
                metric_id NUMERIC(18,0) IDENTITY PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                server_id INT NOT NULL,
                partition_name VARCHAR(255) NOT NULL,
                logical_name VARCHAR(128) NOT NULL,
                partition_id INT NOT NULL,
                total_mb FLOAT NOT NULL,
                used_mb FLOAT NOT NULL,
                free_pct FLOAT NOT NULL,
                device_state VARCHAR(32) NOT NULL
            )
            """),
            ("queue_metrics", """
            CREATE TABLE queue_metrics (
                metric_id NUMERIC(18,0) IDENTITY PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                server_id INT NOT NULL,
                queue_name VARCHAR(255) NOT NULL,
                queue_type VARCHAR(16) NOT NULL,
                size_mb FLOAT NOT NULL,
                first_seg_block VARCHAR(64) NOT NULL,
                last_seg_block VARCHAR(64) NOT NULL,
                next_read VARCHAR(64) NULL,
                readers_count INT DEFAULT 1,
                status VARCHAR(32) NOT NULL
            )
            """),
            ("thread_status", """
            CREATE TABLE thread_status (
                metric_id NUMERIC(18,0) IDENTITY PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                server_id INT NOT NULL,
                thread_spid INT NOT NULL,
                thread_type VARCHAR(32) NOT NULL,
                target_connection VARCHAR(255) NOT NULL,
                state VARCHAR(32) NOT NULL,
                lag_seconds FLOAT DEFAULT 0.0,
                throughput_tps FLOAT DEFAULT 0.0
            )
            """),
            ("open_transactions_log", """
            CREATE TABLE open_transactions_log (
                log_id NUMERIC(18,0) IDENTITY PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                server_id INT NOT NULL,
                primary_db VARCHAR(128) NOT NULL,
                spid INT NOT NULL,
                tx_status VARCHAR(64) NULL,
                login_time DATETIME NULL,
                hostname VARCHAR(128) NULL,
                program_name VARCHAR(128) NULL,
                cmd VARCHAR(128) NULL,
                transaction_name VARCHAR(128) NULL,
                duration_seconds INT NULL
            )
            """),
            ("system_alerts", """
            CREATE TABLE system_alerts (
                alert_id NUMERIC(18,0) IDENTITY PRIMARY KEY,
                server_id INT NOT NULL,
                alert_time DATETIME NOT NULL,
                severity VARCHAR(16) NOT NULL,
                category VARCHAR(32) NOT NULL,
                source_entity VARCHAR(255) NOT NULL,
                message VARCHAR(1000) NOT NULL,
                resolved_at DATETIME NULL
            )
            """)
        ]

        for tbl_name, create_sql in tables_check:
            cursor.execute(f"SELECT COUNT(*) FROM sysobjects WHERE name = '{tbl_name}' AND type = 'U'")
            if cursor.fetchone()[0] == 0:
                cursor.execute(create_sql)
                conn.commit()

        # Seed initial servers if empty
        cursor.execute("SELECT COUNT(*) FROM monitored_servers")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
            INSERT INTO monitored_servers (server_name, host_address, admin_port, environment)
            VALUES ('REP_PROD_01', 'srs-prod-01.corp.local', 5005, 'Production')
            """)
            cursor.execute("""
            INSERT INTO monitored_servers (server_name, host_address, admin_port, environment)
            VALUES ('REP_DR_02', 'srs-dr-01.corp.local', 5005, 'Disaster Recovery')
            """)
            cursor.execute("""
            INSERT INTO monitored_servers (server_name, host_address, admin_port, environment)
            VALUES ('REP_UAT_01', 'srs-uat-01.corp.local', 5005, 'Staging / UAT')
            """)
            conn.commit()

    else:
        # SQLite
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitored_servers (
            server_id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL UNIQUE,
            host_address TEXT NOT NULL,
            admin_port INTEGER NOT NULL,
            environment TEXT DEFAULT 'Production',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS partition_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            server_id INTEGER REFERENCES monitored_servers(server_id),
            partition_name TEXT NOT NULL,
            logical_name TEXT NOT NULL,
            partition_id INTEGER NOT NULL,
            total_mb REAL NOT NULL,
            used_mb REAL NOT NULL,
            free_pct REAL NOT NULL,
            device_state TEXT NOT NULL
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS queue_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            server_id INTEGER REFERENCES monitored_servers(server_id),
            queue_name TEXT NOT NULL,
            queue_type TEXT NOT NULL,
            size_mb REAL NOT NULL,
            first_seg_block TEXT NOT NULL,
            last_seg_block TEXT NOT NULL,
            next_read TEXT,
            readers_count INTEGER DEFAULT 1,
            status TEXT NOT NULL
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS thread_status (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            server_id INTEGER REFERENCES monitored_servers(server_id),
            thread_spid INTEGER NOT NULL,
            thread_type TEXT NOT NULL,
            target_connection TEXT NOT NULL,
            state TEXT NOT NULL,
            lag_seconds REAL DEFAULT 0.0,
            throughput_tps REAL DEFAULT 0.0
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS open_transactions_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            server_id INTEGER REFERENCES monitored_servers(server_id),
            primary_db TEXT NOT NULL,
            spid INTEGER NOT NULL,
            tx_status TEXT,
            login_time TIMESTAMP,
            hostname TEXT,
            program_name TEXT,
            cmd TEXT,
            transaction_name TEXT,
            duration_seconds INTEGER
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER REFERENCES monitored_servers(server_id),
            alert_time TIMESTAMP NOT NULL,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            source_entity TEXT NOT NULL,
            message TEXT NOT NULL,
            resolved_at TIMESTAMP NULL
        );
        """)
        cursor.execute("SELECT COUNT(*) FROM monitored_servers")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
            INSERT INTO monitored_servers (server_id, server_name, host_address, admin_port, environment)
            VALUES (?, ?, ?, ?, ?)
            """, [
                (1, "REP_PROD_01", "srs-prod-01.corp.local", 5005, "Production"),
                (2, "REP_DR_02", "srs-dr-01.corp.local", 5005, "Disaster Recovery"),
                (3, "REP_UAT_01", "srs-uat-01.corp.local", 5005, "Staging / UAT")
            ])
        conn.commit()

    conn.close()

def format_param(p: Any) -> Any:
    """Format datetime objects to ASE-compatible string '%Y-%m-%d %H:%M:%S'."""
    if isinstance(p, datetime.datetime):
        return p.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(p, str) and "T" in p:
        try:
            dt = datetime.datetime.fromisoformat(p.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return p[:19].replace("T", " ")
    return p

def execute_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    db_type, conn = get_db_connection()
    try:
        cursor = conn.cursor()
        formatted_params = tuple(format_param(p) for p in params)

        if db_type == "ase":
            import re
            # Automatically translate 'SELECT ... LIMIT n' to 'SELECT TOP n ...' for Sybase ASE 16
            limit_match = re.search(r'\s+LIMIT\s+(\d+)', query, re.IGNORECASE)
            if limit_match:
                limit_val = limit_match.group(1)
                query = re.sub(r'\s+LIMIT\s+\d+', '', query, flags=re.IGNORECASE)
                query = re.sub(r'SELECT\s+', f'SELECT TOP {limit_val} ', query, count=1, flags=re.IGNORECASE)

        cursor.execute(query, formatted_params)
        
        if db_type == "ase":
            columns = [col[0].lower() for col in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            results = []
            for row in rows:
                row_dict = {}
                for idx, col in enumerate(columns):
                    val = row[idx]
                    if isinstance(val, datetime.datetime):
                        val = val.isoformat()
                    row_dict[col] = val
                results.append(row_dict)
            return results
        else:
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()

def execute_write(query: str, params: tuple = ()) -> int:
    db_type, conn = get_db_connection()
    try:
        cursor = conn.cursor()
        formatted_params = tuple(format_param(p) for p in params)
        cursor.execute(query, formatted_params)
        conn.commit()

        if db_type == "ase":
            try:
                cursor.execute("SELECT @@IDENTITY")
                ident = cursor.fetchone()[0]
                return int(ident) if ident else 1
            except Exception:
                return 1
        else:
            return cursor.lastrowid or 1
    finally:
        conn.close()
