"""Blocks 3 (baseload) and 5 (activities when home): averages per hour of day from past metered data."""
from collections import defaultdict

from ..data import ACTIVITIES, BASELOAD, history, home_hours_observed

AWAY_CONFIDENT = 85
STANDBY_SAVED_KWH = 0.015   # ideal: power strip off while away (≈ 15 W)


def _pct(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0.0


def baseload(start, ish):
    """Fridge + router + standby. Real vs ideal differ only in standby while surely away."""
    per_hour = defaultdict(list)
    for ts, row in history().items():
        if ts < start:
            per_hour[ts.hour].append(sum(row[a] for a in BASELOAD))
    out = []
    for r in ish:
        v = per_hour[r["timestamp"].hour]
        mean = sum(v) / len(v)
        saving = STANDBY_SAVED_KWH if r["away_score"] >= AWAY_CONFIDENT else 0.0
        out.append(dict(real=mean, ideal=mean - saving, low=_pct(v, 0.1), high=_pct(v, 0.9)))
    return out


def activities(start, ish):
    """Kettle, coffee, oven, TV, laptop, lighting, charging as one group.
    Learned only from past hours she was home (phone positions); forecast = average × chance she is home."""
    home = home_hours_observed()
    per_hour = defaultdict(list)
    for ts, row in history().items():
        if ts < start and home.get(ts):
            per_hour[ts.hour].append(sum(row[a] for a in ACTIVITIES))
    out = []
    for r in ish:
        v = per_hour[r["timestamp"].hour] or [0.0]
        p_home = 1 - r["away_score"] / 100
        mean = sum(v) / len(v) * p_home
        out.append(dict(real=mean, ideal=mean, low=_pct(v, 0.1) * p_home, high=_pct(v, 0.9) * p_home))
    return out
