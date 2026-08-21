# Intelligent Data Center Operations

A base project for a data-center monitoring & anomaly-detection platform.
It simulates a fleet of servers across four racks, streams live telemetry
(CPU, memory, inlet temperature, power draw, network throughput), flags
anomalies with an IsolationForest model, and visualizes everything in a
live ops-console dashboard.

## Architecture

```
idc-ops/
├── backend/
│   ├── data_simulator.py   # generates realistic per-server telemetry + injected faults
│   ├── anomaly_detector.py # rolling-window IsolationForest (+ z-score cold-start fallback)
│   ├── database.py         # SQLite persistence for metrics & anomalies
│   └── main.py             # FastAPI app: background sim loop + REST API + serves dashboard
├── frontend/
│   └── index.html          # single-page ops dashboard (vanilla JS + Chart.js)
├── requirements.txt
└── README.md
```

**Data flow:** a background loop ticks every 3 seconds → the simulator produces
one reading per server → readings are written to SQLite → each reading is
scored by the anomaly detector → any anomalies are also written to SQLite →
the dashboard polls the REST API and re-renders.

## Why this design

- **Cold-start-safe anomaly detection.** A brand-new IsolationForest has
  nothing to learn from on server 1. The detector falls back to a z-score
  rule until each server has enough history (15 readings), then switches to
  a proper multivariate IsolationForest fit on that server's own rolling
  window — so what counts as "normal" adapts per server (a GPU node runs
  hotter than a network switch, and that's fine).
- **Explainable output.** Every anomaly record names the specific metric
  that deviated most, not just "something's wrong."
- **No external services required.** SQLite + stdlib keep the base project
  runnable anywhere with just `pip install`.

## Run it

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Then open **http://localhost:8000** — the dashboard is served directly by
the API, so there's nothing else to start.

## REST API

| Endpoint                       | Description                                   |
|---------------------------------|------------------------------------------------|
| `GET /api/servers`             | Static fleet inventory (rack, unit, role)      |
| `GET /api/snapshot`            | Latest reading for every server                |
| `GET /api/metrics/{server_id}` | Recent time-series for one server (for charts) |
| `GET /api/anomalies`           | Most recent detected anomalies                 |
| `GET /api/health`              | Liveness check                                 |

## Extending this base

- Swap `data_simulator.py` for a real collector (SNMP, IPMI, Prometheus
  exporters, cloud provider metrics APIs) — the rest of the pipeline is
  unchanged as long as it emits the same reading shape.
- Add alerting (email/Slack/PagerDuty) by hooking into
  `db.insert_anomalies()` in `main.py`.
- Add authentication and a proper Postgres/Timescale backend for
  production scale — SQLite here is intentionally minimal.
- Extend the ML layer: seasonal models (time-of-day load patterns),
  forecasting for capacity planning, or a supervised model once you have
  labeled incident data.
