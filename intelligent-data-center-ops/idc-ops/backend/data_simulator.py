"""
data_simulator.py
------------------
Generates synthetic telemetry for a fleet of data center servers.

Each server has a stable "personality" (baseline load, rack location) and
emits noisy-but-realistic readings for CPU, memory, inlet temperature,
power draw and network throughput. A small, controllable probability of
injecting an anomaly (thermal spike, power surge, CPU pegged, etc.) lets
the anomaly detector have something real to catch.
"""

import random
import time
from dataclasses import dataclass, field


RACKS = ["A", "B", "C", "D"]
ANOMALY_KINDS = ["thermal_spike", "power_surge", "cpu_saturation", "network_stall"]


@dataclass
class Server:
    server_id: str
    rack: str
    unit: int  # rack-unit position (1-42)
    role: str
    baseline_cpu: float
    baseline_temp: float
    baseline_power: float
    active_anomaly: str | None = field(default=None)
    anomaly_ticks_left: int = 0

    def to_dict(self):
        return {
            "server_id": self.server_id,
            "rack": self.rack,
            "unit": self.unit,
            "role": self.role,
        }


def _make_fleet(n_per_rack: int = 6) -> list[Server]:
    fleet = []
    roles = ["compute", "compute", "storage", "gpu", "network", "compute"]
    unit_cursor = {r: 2 for r in RACKS}
    idx = 0
    for rack in RACKS:
        for i in range(n_per_rack):
            role = roles[i % len(roles)]
            unit = unit_cursor[rack]
            unit_cursor[rack] += 4 if role == "gpu" else 2
            fleet.append(
                Server(
                    server_id=f"{rack}-{unit:02d}",
                    rack=rack,
                    unit=unit,
                    role=role,
                    baseline_cpu=random.uniform(20, 45)
                    if role != "gpu"
                    else random.uniform(40, 65),
                    baseline_temp=random.uniform(28, 34),
                    baseline_power=random.uniform(180, 260)
                    if role != "gpu"
                    else random.uniform(350, 480),
                )
            )
            idx += 1
    return fleet


class DataCenterSimulator:
    """Owns fleet state and produces one telemetry snapshot per call to tick()."""

    def __init__(self, n_per_rack: int = 6, anomaly_probability: float = 0.02):
        self.fleet = _make_fleet(n_per_rack)
        self.anomaly_probability = anomaly_probability

    def servers(self):
        return [s.to_dict() for s in self.fleet]

    def _maybe_start_anomaly(self, s: Server):
        if s.active_anomaly is None and random.random() < self.anomaly_probability:
            s.active_anomaly = random.choice(ANOMALY_KINDS)
            s.anomaly_ticks_left = random.randint(4, 10)

    def _reading_for(self, s: Server) -> dict:
        self._maybe_start_anomaly(s)

        cpu = s.baseline_cpu + random.gauss(0, 3)
        mem = 40 + (s.baseline_cpu / 2) + random.gauss(0, 4)
        temp = s.baseline_temp + random.gauss(0, 0.6)
        power = s.baseline_power + random.gauss(0, 8)
        net_mbps = random.uniform(50, 400)
        status = "healthy"

        if s.active_anomaly:
            kind = s.active_anomaly
            if kind == "thermal_spike":
                temp += random.uniform(18, 30)
            elif kind == "power_surge":
                power += random.uniform(150, 300)
            elif kind == "cpu_saturation":
                cpu = min(100, cpu + random.uniform(40, 55))
            elif kind == "network_stall":
                net_mbps = random.uniform(0, 5)
            status = "critical"

            s.anomaly_ticks_left -= 1
            if s.anomaly_ticks_left <= 0:
                s.active_anomaly = None

        return {
            "server_id": s.server_id,
            "timestamp": time.time(),
            "cpu_pct": round(max(0, min(100, cpu)), 1),
            "mem_pct": round(max(0, min(100, mem)), 1),
            "inlet_temp_c": round(max(15, temp), 1),
            "power_w": round(max(0, power), 1),
            "net_mbps": round(max(0, net_mbps), 1),
            "status_hint": status,
            "injected_anomaly": s.active_anomaly,
        }

    def tick(self) -> list[dict]:
        """Produce one telemetry reading per server."""
        return [self._reading_for(s) for s in self.fleet]
