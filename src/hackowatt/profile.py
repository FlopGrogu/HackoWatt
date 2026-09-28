"""What the app knows about the user before reading the calendar: the home address she entered at setup,
plus facts learned automatically from observable past data (hourly consumption and phone positions)
up to LEARN_UNTIL. No hand-written knowledge about her life or her calendar.

Standalone on purpose (reads the CSV files itself) so llm_ishome can import it without import cycles.
"""
import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

from .paths import ROOT

HOME_ADDRESS = "ul. Chmielna 71, Warsaw, Poland"
HOME = (52.2296, 21.0030)
LEARN_UNTIL = datetime(2026, 9, 29)      # "today" is 28 Sep: only data observed before this is used
KITCHEN = ("kettle", "coffee_machine")
EVENING = ("lighting", "tv", "laptop", "kettle", "oven")


def _km(lat, lon):
    return math.hypot((lat - HOME[0]) * 111.32, (lon - HOME[1]) * 111.32 * math.cos(math.radians(HOME[0])))


def _hhmm(minutes):
    minutes = int(round(minutes)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _consumption():
    with open(ROOT / "data" / "consumption" / "hourly_consumption.csv") as f:
        return [(datetime.fromisoformat(r["timestamp"][:16]), r) for r in csv.DictReader(f)
                if datetime.fromisoformat(r["timestamp"][:16]) < LEARN_UNTIL]


def _positions():
    with open(ROOT / "data" / "geolocation" / "positions.csv") as f:
        return [(datetime.fromisoformat(r["timestamp"][:16]), float(r["lat"]), float(r["lon"]))
                for r in csv.DictReader(f) if datetime.fromisoformat(r["timestamp"][:16]) < LEARN_UNTIL]


def learned_facts():
    lines = []
    rows = _consumption()

    # first kitchen activity in the morning (≈ wake-up) and last evening activity (≈ bedtime), per day
    first, last = defaultdict(list), []
    by_day = defaultdict(dict)
    for ts, r in rows:
        by_day[ts.date()][ts.hour] = r
    for day, hours in by_day.items():
        morning = [h for h in range(4, 12) if h in hours and sum(float(hours[h][f"{a}_kwh"]) for a in KITCHEN) > 0.05]
        if morning:
            first["weekend" if day.weekday() >= 5 else "weekday"].append(morning[0] * 60)
        evening = [h for h in range(19, 24) if h in hours and sum(float(hours[h][f"{a}_kwh"]) for a in EVENING) > 0.03]
        if evening:
            last.append(evening[-1] * 60 + 59)
    for kind in ("weekday", "weekend"):
        if first[kind]:
            lines.append(f"- First kitchen use in the morning (kettle/coffee) on {kind}s at home: usually in the hour "
                         f"starting {_hhmm(median(first[kind]))} ({len(first[kind])} days observed).")
    if last:
        lines.append(f"- Last evening activity (lights/TV/laptop) usually ends around {_hhmm(median(last))}.")

    # phone positions: nights away, weekday leave/return times, frequent places
    pos = _positions()
    nights = defaultdict(list)
    for ts, lat, lon in pos:
        if ts.hour == 3:
            nights[ts.date()].append(_km(lat, lon) > 1)
    away_nights = sum(1 for v in nights.values() if any(v))
    lines.append(f"- Nights spent away from home: {away_nights} of {len(nights)} observed nights.")

    leave, back = [], []
    day_pos = defaultdict(list)
    for p in pos:
        day_pos[p[0].date()].append(p)
    for day, ps in day_pos.items():
        if day.weekday() >= 5:
            continue
        ps.sort()
        home_night = [p for p in ps if p[0].hour < 5 and _km(p[1], p[2]) < 0.15]
        home_late = [p for p in ps if p[0].hour >= 21 and _km(p[1], p[2]) < 0.15]
        away = [p for p in ps if 5 <= p[0].hour < 21 and 1 < _km(p[1], p[2]) < 30]
        if home_night and home_late and len(away) >= 8:          # a normal day out in Warsaw
            leave.append(away[0][0].hour * 60 + away[0][0].minute)
            back.append(away[-1][0].hour * 60 + away[-1][0].minute + 15)
    if leave:
        lines.append(f"- On weekdays spent out in the city she usually leaves home around {_hhmm(median(leave))} "
                     f"and is back around {_hhmm(median(back))} ({len(leave)} days observed).")

    places = []   # greedy clustering: within ~1 km in the city, ~30 km for other cities
    for ts, lat, lon in pos:
        if _km(lat, lon) <= 1:
            continue
        radius = 1.0 if _km(lat, lon) < 30 else 30.0
        for pl in places:
            if math.hypot((lat - pl["lat"]) * 111.32, (lon - pl["lon"]) * 111.32 * 0.61) < radius:
                break
        else:
            pl = {"lat": lat, "lon": lon, "seen": defaultdict(list), "nights": set()}
            places.append(pl)
        pl["seen"][ts.date()].append(ts.hour * 60 + ts.minute)
        if ts.hour == 3:
            pl["nights"].add(ts.date())
    places.sort(key=lambda pl: -len(pl["seen"]))
    if places:
        lines.append("- Places where her phone was seen away from home (most frequent first):")
    for pl in places[:8]:
        where = f"{pl['lat']:.3f}, {pl['lon']:.3f} ({_km(pl['lat'], pl['lon']):.0f} km from home)"
        if pl["nights"]:
            lines.append(f"  - {where}: on {len(pl['seen'])} days, {len(pl['nights'])} night(s) spent there")
        else:
            arrive = median(min(m) for m in pl["seen"].values())
            leave_ = median(max(m) for m in pl["seen"].values()) + 15
            lines.append(f"  - {where}: on {len(pl['seen'])} days, usually {_hhmm(arrive)}–{_hhmm(leave_)}")
    return "\n".join(lines)


def profile_text():
    return (f"Home address (entered by the user): {HOME_ADDRESS}\n\n"
            f"Learned automatically from past electricity use and phone positions "
            f"(until {LEARN_UNTIL - timedelta(days=1):%d %b %Y}):\n{learned_facts()}")
