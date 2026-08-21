"""
anomaly_detector.py
--------------------
Per-server anomaly detection over the telemetry stream.

Approach:
  - Keep a rolling window of recent readings per server.
  - Once enough history exists, fit a lightweight IsolationForest on
    [cpu_pct, mem_pct, inlet_temp_c, power_w, net_mbps] and score the
    newest point.
  - Before enough history exists (cold start), fall back to a simple
    z-score rule so the system is never "blind" on day one.

This mirrors a common real-world pattern: rule-based guards for cold
start / explainability, ML for catching subtler multivariate drift.
"""

import numpy as np
from collections import defaultdict, deque
from sklearn.ensemble import IsolationForest

FEATURES = ["cpu_pct", "mem_pct", "inlet_temp_c", "power_w", "net_mbps"]
WINDOW_SIZE = 50
MIN_TRAIN_SIZE = 15
CONTAMINATION = 0.06
Z_SCORE_THRESHOLD = 4.0


class AnomalyDetector:
    def __init__(self):
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=WINDOW_SIZE))

    def _to_vector(self, reading: dict) -> list[float]:
        return [reading[f] for f in FEATURES]

    def _zscore_check(self, history: list[list[float]], point: list[float]) -> tuple[bool, float, str]:
        arr = np.array(history)
        mean = arr.mean(axis=0)
        std = arr.std(axis=0) + 1e-6
        z = (np.array(point) - mean) / std
        worst_idx = int(np.argmax(np.abs(z)))
        worst_z = float(z[worst_idx])
        return abs(worst_z) > Z_SCORE_THRESHOLD, worst_z, FEATURES[worst_idx]

    def _isoforest_check(self, history: list[list[float]], point: list[float]) -> tuple[bool, float, str]:
        model = IsolationForest(
            n_estimators=100,
            contamination=CONTAMINATION,
            random_state=42,
        )
        model.fit(history)
        score = float(model.decision_function([point])[0])  # lower = more anomalous
        is_anomaly = model.predict([point])[0] == -1

        # attribute the anomaly to the metric that deviates most from history mean
        arr = np.array(history)
        mean = arr.mean(axis=0)
        std = arr.std(axis=0) + 1e-6
        z = (np.array(point) - mean) / std
        worst_idx = int(np.argmax(np.abs(z)))
        return bool(is_anomaly), score, FEATURES[worst_idx]

    def process(self, reading: dict) -> dict | None:
        """Feed one reading in; returns an anomaly record or None."""
        server_id = reading["server_id"]
        vector = self._to_vector(reading)
        history = self._history[server_id]

        result = None
        if len(history) >= MIN_TRAIN_SIZE:
            is_anomaly, score, metric = self._isoforest_check(list(history), vector)
        elif len(history) >= 10:
            is_anomaly, score, metric = self._zscore_check(list(history), vector)
        else:
            is_anomaly, score, metric = False, 0.0, ""

        if is_anomaly:
            result = {
                "server_id": server_id,
                "timestamp": reading["timestamp"],
                "metric": metric,
                "value": reading[metric],
                "score": round(score, 3),
                "message": f"{server_id}: unusual {metric.replace('_', ' ')} "
                           f"({reading[metric]})",
            }

        history.append(vector)
        return result

    def process_batch(self, readings: list[dict]) -> list[dict]:
        out = []
        for r in readings:
            res = self.process(r)
            if res:
                out.append(res)
        return out
