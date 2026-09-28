"""isHome – combines the LLM calendar reading, geolocation and habits into an hourly away score.

Priority order (first clear answer wins):
  current hour : geolocation (position < 30 min old) -> LLM (if confident) -> habits
  later hours  : LLM (if confident) -> habits
"Confident" = away score <= 15 or >= 85. If geolocation contradicts a confident LLM answer for the current
hour (trip delayed/cancelled), the LLM result is not trusted for the rest of that day.

Output per hour: away_score (0 = home for sure, 100 = away for sure), people, source, reason.
Absences (away score >= 85 in a row, from the LLM intervals): departure, return, nights.
"""
import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta

from .llm_ishome import cached_results
from .paths import ROOT

HOME = (52.2296, 21.0030)
CONFIDENT_HOME, CONFIDENT_AWAY = 15, 85
GEO_MAX_AGE = timedelta(minutes=30)


# ---------- inputs ----------
def load_llm_results():
    """{date: day result} from the LLM cache of the selected provider/model (current prompt only)."""
    return cached_results()


def load_positions():
    rows = []
    with open(ROOT / "data" / "geolocation" / "positions.csv") as f:
        for r in csv.DictReader(f):
            rows.append((datetime.fromisoformat(r["timestamp"][:16]), float(r["lat"]), float(r["lon"])))
    return rows


def distance_m(lat, lon):
    return math.hypot((lat - HOME[0]) * 111320, (lon - HOME[1]) * 111320 * math.cos(math.radians(HOME[0])))


def geo_score(lat, lon):
    d = distance_m(lat, lon)
    return 0 if d < 150 else 100 if d > 1000 else 50


def habits_table(positions, until):
    """Usual away score per (weekend?, hour), from past positions before `until`."""
    acc = defaultdict(list)
    for ts, lat, lon in positions:
        if ts < until:
            acc[(ts.weekday() >= 5, ts.hour)].append(0 if distance_m(lat, lon) < 150 else 100)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def _minute(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def llm_hour(result, hour):
    """Time-weighted away score, people and reason of one hour from a day's LLM intervals."""
    a, b = hour * 60, hour * 60 + 60
    score = people = 0.0
    reasons = []
    for iv in result["intervals"]:
        overlap = min(b, _minute(iv["end"])) - max(a, _minute(iv["start"]))
        if overlap > 0:
            score += iv["away_score"] * overlap / 60
            people += iv["people"] * overlap / 60
            reasons.append(iv["reason"])
    return score, people, " / ".join(dict.fromkeys(reasons))


# ---------- combination ----------
def is_confident(score):
    return score <= CONFIDENT_HOME or score >= CONFIDENT_AWAY


def ishome(start, hours, llm=None, positions=None):
    """Hourly isHome for [start, start + hours). `start` = forecast time ("now"), on the hour."""
    llm = load_llm_results() if llm is None else llm
    positions = load_positions() if positions is None else positions
    habits = habits_table(positions, start)
    past = [p for p in positions if start - GEO_MAX_AGE <= p[0] <= start]
    last_pos = past[-1] if past else None
    distrust_day = None

    rows = []
    for k in range(hours):
        ts = start + timedelta(hours=k)
        day_result = llm.get(ts.date())
        llm_s = llm_p = None
        if day_result and ts.date() != distrust_day:
            llm_s, llm_p, llm_reason = llm_hour(day_result, ts.hour)

        if k == 0 and last_pos:
            g = geo_score(last_pos[1], last_pos[2])
            if g != 50:
                if llm_s is not None and is_confident(llm_s) and (llm_s >= CONFIDENT_AWAY) != (g == 100):
                    distrust_day = ts.date()     # calendar contradicted by reality -> trust LLM less today
                people = (llm_p if llm_s is not None and g == 0 and llm_p >= 1 else (1 if g == 0 else 0))
                rows.append(dict(timestamp=ts, away_score=g, people=round(people, 2), source="geolocation",
                                 reason=f"phone {'at home' if g == 0 else 'away from home'} at {last_pos[0]:%H:%M}"))
                continue
        if llm_s is not None and is_confident(llm_s):
            rows.append(dict(timestamp=ts, away_score=round(llm_s, 1), people=round(llm_p, 2), source="llm",
                             reason=llm_reason))
            continue
        h = habits.get((ts.weekday() >= 5, ts.hour), 50.0)
        rows.append(dict(timestamp=ts, away_score=round(h, 1), people=round(1 - h / 100, 2), source="habits",
                         reason=f"usual for {'weekend' if ts.weekday() >= 5 else 'weekday'} {ts.hour:02d}:00"))
    return rows


def absences(start, end, llm=None):
    """Absences between start and end from the LLM intervals: consecutive time with away score >= 85.
    Returns dicts: departure, return, nights, min_score."""
    llm = load_llm_results() if llm is None else llm
    spans = []
    d = start.date()
    while d <= end.date():
        for iv in (llm.get(d) or {}).get("intervals", []):
            s = datetime.combine(d, datetime.min.time()) + timedelta(minutes=_minute(iv["start"]))
            e = datetime.combine(d, datetime.min.time()) + timedelta(minutes=_minute(iv["end"]))
            if iv["away_score"] >= CONFIDENT_AWAY and e > start and s < end:
                if spans and spans[-1]["return"] == s:
                    spans[-1]["return"] = e
                    spans[-1]["min_score"] = min(spans[-1]["min_score"], iv["away_score"])
                else:
                    spans.append({"departure": s, "return": e, "min_score": iv["away_score"]})
        d += timedelta(days=1)
    for sp in spans:
        sp["nights"] = (sp["return"].date() - sp["departure"].date()).days
    return spans
