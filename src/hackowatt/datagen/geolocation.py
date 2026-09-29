"""Geolocation stage: her phone's position every 15 minutes for the whole year (columns as before: timestamp, lat, lon, accuracy_m).

Positions come from the itinerary (the same timeline the consumption model uses) plus GPS-like noise: the reported accuracy is
log-normally distributed (indoors worse than outdoors), the error is normal with sigma = accuracy / 2, and about 1.5 % of the
fixes are poor ones (multipath between buildings).
"""
import csv
import math
from datetime import timedelta

from .geo import shift_m

STEP_MIN = 15
MEDIAN_ACCURACY = {"home": 18, "place": 22, "walk": 9, "transit": 12, "car": 8, "train": 20, "flight": 250}


def write_positions(cfg, itin):
    rng = cfg.rng("geolocation")
    out = cfg.data / "geolocation"
    out.mkdir(parents=True, exist_ok=True)
    rows = 0
    with open(out / "positions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "lat", "lon", "accuracy_m"])
        for minute in range(0, itin.N, STEP_MIN):
            lat, lon, mode = itin.position(minute)
            acc = MEDIAN_ACCURACY.get(mode, 15) * math.exp(rng.gauss(0, 0.35))
            if rng.random() < 0.015 and mode != "flight":
                acc = rng.uniform(55, 110)
            acc = max(3.0, min(acc, 1500.0))
            lat, lon = shift_m((lat, lon), rng.gauss(0, acc / 2), rng.gauss(0, acc / 2))
            w.writerow([cfg.stamp(cfg.start + timedelta(minutes=minute)), f"{lat:.6f}", f"{lon:.6f}", int(round(acc))])
            rows += 1
    return rows
