"""
database.py
-----------
Minimal SQLite persistence for telemetry and detected anomalies.
Kept dependency-free (stdlib sqlite3) so the base project runs anywhere.
"""

import sqlite3
import threading

DB_PATH = "idc_ops.db"

_lock = threading.Lock()


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id TEXT NOT NULL,
            timestamp REAL NOT NULL,
            cpu_pct REAL,
            mem_pct REAL,
            inlet_temp_c REAL,
            power_w REAL,
            net_mbps REAL
        );

        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id TEXT NOT NULL,
            timestamp REAL NOT NULL,
            metric TEXT NOT NULL,
            value REAL,
            score REAL,
            message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_metrics_server_ts
            ON metrics (server_id, timestamp);
        """
    )
    conn.commit()
    conn.close()


def insert_metrics(readings: list[dict]):
    with _lock:
        conn = get_conn()
        conn.executemany(
            """INSERT INTO metrics
               (server_id, timestamp, cpu_pct, mem_pct, inlet_temp_c, power_w, net_mbps)
               VALUES (:server_id, :timestamp, :cpu_pct, :mem_pct, :inlet_temp_c, :power_w, :net_mbps)""",
            readings,
        )
        conn.commit()
        conn.close()


def insert_anomalies(anomalies: list[dict]):
    if not anomalies:
        return
    with _lock:
        conn = get_conn()
        conn.executemany(
            """INSERT INTO anomalies (server_id, timestamp, metric, value, score, message)
               VALUES (:server_id, :timestamp, :metric, :value, :score, :message)""",
            anomalies,
        )
        conn.commit()
        conn.close()


def recent_metrics(server_id: str, limit: int = 60) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM metrics WHERE server_id = ?
           ORDER BY timestamp DESC LIMIT ?""",
        (server_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def recent_anomalies(limit: int = 25) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM anomalies ORDER BY timestamp DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def latest_snapshot() -> list[dict]:
    """Latest reading per server_id."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT m.* FROM metrics m
           INNER JOIN (
               SELECT server_id, MAX(timestamp) AS ts
               FROM metrics GROUP BY server_id
           ) latest
           ON m.server_id = latest.server_id AND m.timestamp = latest.ts"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
