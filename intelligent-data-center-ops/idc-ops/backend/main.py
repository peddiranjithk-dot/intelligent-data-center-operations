"""
main.py
-------
FastAPI service for Intelligent Data Center Operations.

Runs a background loop that simulates telemetry for a server fleet,
persists it, scores it with the anomaly detector, and exposes it all
over a small REST API consumed by the frontend dashboard.

Run with:
    uvicorn backend.main:app --reload --port 8000
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import database as db
from backend.data_simulator import DataCenterSimulator
from backend.anomaly_detector import AnomalyDetector

TICK_SECONDS = 3

simulator = DataCenterSimulator()
detector = AnomalyDetector()


async def simulation_loop():
    while True:
        readings = simulator.tick()
        db.insert_metrics(readings)

        anomalies = detector.process_batch(readings)
        db.insert_anomalies(anomalies)

        await asyncio.sleep(TICK_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()


app = FastAPI(title="Intelligent Data Center Operations", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/servers")
def list_servers():
    """Static fleet inventory (rack, unit, role)."""
    return simulator.servers()


@app.get("/api/snapshot")
def snapshot():
    """Latest reading for every server, joined with inventory metadata."""
    inventory = {s["server_id"]: s for s in simulator.servers()}
    latest = db.latest_snapshot()
    merged = []
    for row in latest:
        meta = inventory.get(row["server_id"], {})
        merged.append({**meta, **row})
    merged.sort(key=lambda r: (r.get("rack", ""), r.get("unit", 0)))
    return merged


@app.get("/api/metrics/{server_id}")
def metrics(server_id: str, limit: int = 60):
    """Recent time-series for one server, for charting."""
    return db.recent_metrics(server_id, limit=limit)


@app.get("/api/anomalies")
def anomalies(limit: int = 25):
    """Most recent detected anomalies across the fleet."""
    return db.recent_anomalies(limit=limit)


@app.get("/api/health")
def health():
    return {"status": "ok", "server_time": time.time()}


# Serve the dashboard as static files at the root path.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
