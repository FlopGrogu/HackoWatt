"""Step 5 – export the forecast as JSON for the app: data/app/forecast.json.

Same keys as the app's demo data (app/js/data/demo.js): meta, user, now, overview, peak, home, usage
(24h / 3d / 7d). Not included (not computed by the forecast): humidity and the device list.

HOW TO GENERATE
1. Environment (once): Python >= 3.10, `pip install -r requirements.txt`; the year of data comes from `python src/generate_all.py`.
2. Everything the forecast reads is limited to the 30 days before "now"; a date in any year maps to the same month/day of 2026
   and the year wraps around (see hackowatt/wrap.py). Forecasts are precomputed for 00/06/12/18 h of every day:
       python src/export_app_data.py --all        # -> data/app/forecast/<date>.json (365 files, the app reads these)
       python src/export_app_data.py 2026-10-04T09:00   # one moment -> data/app/forecast.json (--out to change)
3. Only needed if the calendar changed: first let the LLM read the changed days (python src/interpret_calendar.py, Gemini key as
   API_KEY=... in the git-ignored .secret). Without LLM results the forecast falls back to her habits.

Usage:  python src/export_app_data.py [now] [--out file.json]
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from hackowatt.data import history, price, set_now
from hackowatt.wrap import WINDOW_DAYS, YEAR
from hackowatt.forecast import explain, forecast, reminders_and_tips
from hackowatt.ishome import load_llm_results
from hackowatt.llm_ishome import MODEL, PROVIDER
from hackowatt.paths import ROOT

OUT = ROOT / "data" / "app" / "forecast.json"
USER = {"name": "Aleksandra", "initials": "A", "status": "All systems running normally"}
BLOCK_TITLES = {"space_heating_kwh": "Space heating", "hot_water_kwh": "Hot-water reheat",
                "appliances_kwh": "Washer / dishwasher", "activities_kwh": "Cooking & activities",
                "baseload_kwh": "Baseload"}
# what drives each block: the plain explanation shown in the chart tooltips
BLOCK_WHY = {"space_heating_kwh": "Heat pump keeps the flat warm",
             "hot_water_kwh": "Heat pump reheats the hot-water tank",
             "appliances_kwh": "Washing machine / dishwasher run",
             "activities_kwh": "Cooking, TV and lighting at home",
             "baseload_kwh": "Fridge, router and standby, always on"}
APPLIANCE_NAMES = {"washing_machine": "Washing machine", "dishwasher": "Dishwasher"}
APPLIANCE_ICONS = {"washing_machine": "washer", "dishwasher": "dishwasher"}
HUMAN = {"fridge": "the fridge", "heat_pump_space_heating": "space heating", "heat_pump_hot_water": "hot water",
         "kettle": "the kettle", "coffee_machine": "the coffee machine", "oven": "the oven",
         "washing_machine": "the washing machine", "dishwasher": "the dishwasher", "tv": "the TV",
         "laptop": "the laptop", "wifi_router": "the router", "lighting": "lighting",
         "phone_tablet_charging": "device charging", "standby": "standby devices"}
RANGES = {"24h": (24, 1, "Hour-level granularity (next 24 h)"),
          "3d": (72, 4, "4-hour totals (next 3 days)"),
          "7d": (168, 24, "Daily totals (next 7 days)")}


def cents(euros):
    """Amounts under one euro are shown in cents (¢) in the app, larger ones in euros."""
    return f"{euros * 100:.0f}¢" if abs(euros) < 1 else f"€{euros:.2f}"


def r1(x, n=1):
    return round(x, n)


def group(values, size):
    return [sum(values[i:i + size]) / len(values[i:i + size]) for i in range(0, len(values), size)]


def accumulate(values, size):
    """kWh summed over consecutive blocks of `size` hours (size 1 = the hourly values themselves)."""
    return [sum(values[i:i + size]) for i in range(0, len(values), size)]


def daily_history(now, days):
    per_day = defaultdict(float)
    for ts, row in history().items():
        if now - timedelta(days=days) <= ts < now.replace(hour=0):
            per_day[ts.date()] += sum(row.values())
    return [per_day[d] for d in sorted(per_day)]


def overview(now):
    """Home card: daily kWh of the last 28 metered days + of the next 7 forecast days."""
    past = daily_history(now, 28)
    rows = forecast(now.replace(hour=0) + timedelta(days=1), 24 * 7)[0]
    future = [sum(r["total_real_kwh"] for r in rows[d * 24:(d + 1) * 24]) for d in range(7)]
    first = now.replace(hour=0) - timedelta(days=len(past))
    start = now.replace(hour=0) + timedelta(days=1)
    day = lambda d: f"{d:%-d %b}"
    return {"actual": [r1(v) for v in past], "forecast": [r1(v) for v in future],
            "pointLabels": [day(first + timedelta(days=i)) for i in range(len(past))] +
                           [day(start + timedelta(days=i)) for i in range(len(future))],   # one label per point (tooltips)
            "labels": [day(first), day(first + timedelta(days=14)), day(now), day(start + timedelta(days=6))]}


def peak_hours(now):
    """Average kWh per hour of day on past weekdays; peak = the 4 consecutive hours with most demand."""
    per_hour = defaultdict(list)
    for ts, row in history().items():
        if ts < now and ts.weekday() < 5:
            per_hour[ts.hour].append(sum(row.values()))
    hours = [sum(per_hour[h]) / len(per_hour[h]) for h in range(24)]
    start = max(range(21), key=lambda h: sum(hours[h:h + 4]))
    used = defaultdict(float)             # what makes those hours peak: kWh per appliance inside the window
    for ts, row in history().items():
        if ts < now and ts.weekday() < 5 and start <= ts.hour < start + 4:
            for name, kwh in row.items():
                used[name] += kwh
    top = [HUMAN[n] for n in sorted(used, key=used.get, reverse=True)[:2]]
    return {"hours": [r1(v, 3) for v in hours], "from": start, "to": start + 3,
            "text": f"Your highest energy demand is typically between {start}–{start + 4} h on weekdays, "
                    f"mostly {' and '.join(top)}."}


def highlights(rows, size, count, runs=()):
    """The `count` highest points of the (accumulated) series. Each is titled by the block that pushes it above
    its usual level, with the plain reason it is high (what runs then)."""
    chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
    parts = [{b: sum(r[b] for r in chunk) for b in BLOCK_TITLES} for chunk in chunks]
    typical = {b: sum(p[b] for p in parts) / len(parts) for b in BLOCK_TITLES}
    points = []
    for i, (chunk, part) in enumerate(zip(chunks, parts)):
        ts = chunk[0]["timestamp"]
        total = sum(r["total_real_kwh"] for r in chunk)
        driver = max(BLOCK_TITLES, key=lambda b: part[b] - typical[b])
        if part[driver] - typical[driver] <= 0:
            driver = max(BLOCK_TITLES, key=part.get)
        when = (f"{ts:%a %-d %b}" if size == 24 else f"{ts:%a %-d %b %H:%M}" if len(rows) > 24 else f"{ts:%H:%M}")
        explanation = BLOCK_WHY[driver]
        if driver == "appliances_kwh":
            end = ts + timedelta(hours=size)
            due = [r for r in runs if r["p"] >= 0.5 and ts <= r["usual_start"] < end]
            if due:
                explanation = ", ".join(f"{APPLIANCE_NAMES[r['appliance']]} ({r['reason']})" for r in due)
        points.append(dict(index=i, title=BLOCK_TITLES[driver], detail=f"{when} • {total:.2f} kWh",
                           explain=[explanation], total=total))
    gap = 3 if size == 1 else 1 if size < 24 else 0     # don't pick neighbouring points of the same peak
    top = []
    for p in sorted(points, key=lambda p: -p["total"]):
        if len(top) < count and all(abs(p["index"] - q["index"]) > gap for q in top):
            top.append(p)
    return [{k: v for k, v in p.items() if k != "total"} for p in sorted(top, key=lambda p: p["index"])]


PERIOD = {24: "previous 24 h", 72: "previous 3 days", 168: "previous week"}


def why(now, hours, rows):
    """Biggest changes per block against the same period just before `now` (hackowatt.forecast.explain)."""
    return [{"label": g.capitalize(), "before": r1(before, 2), "after": r1(after, 2), "delta": r1(diff, 2),
             "text": f"{g.capitalize()}: {after:.1f} kWh, {diff:+.1f} kWh vs the {PERIOD[hours]}"}
            for diff, g, before, after in explain(now, hours, rows)[:3]]


def shifts(now, runs):
    """Predicted washer / dishwasher runs that would be cheaper at another time. The frontend lets the user
    schedule one: it removes `removes` (the expected profile at the usual time) and adds `adds` (the run at the
    cheaper time), both as {hours from now: kWh}."""
    from hackowatt.blocks.appliances import SHAPE
    hour = lambda ts: int((ts - now).total_seconds() // 3600)
    out = []
    for run in runs:
        if run["p"] < 0.3 or run["ideal_start"] == run["usual_start"] or run["saving_eur"] < 0.01:
            continue
        removes, adds = defaultdict(float), defaultdict(float)
        base = run["usual_start"].replace(hour=0)
        for h, w in run["hours"].items():
            for j, share in enumerate(SHAPE[run["appliance"]]):
                removes[hour(base + timedelta(hours=h + j))] += run["kwh"] * share * run["p"] * w
        for j, share in enumerate(SHAPE[run["appliance"]]):
            adds[hour(run["ideal_start"]) + j] += run["kwh"] * share * run["p"]
        out.append({
            "id": f"{run['appliance']}-{run['usual_start']:%Y%m%dT%H}",
            "device": APPLIANCE_NAMES[run["appliance"]], "icon": APPLIANCE_ICONS[run["appliance"]],
            "reason": run["reason"], "p": r1(run["p"], 2), "kwh": r1(run["kwh"], 2),
            "usual": run["usual_start"].isoformat(timespec="minutes"),
            "ideal": run["ideal_start"].isoformat(timespec="minutes"),
            "usualIndex": hour(run["usual_start"]), "idealIndex": hour(run["ideal_start"]),
            "usualPrice": price(run["usual_start"]), "idealPrice": price(run["ideal_start"]),
            "saving": r1(run["saving_eur"], 2),
            "removes": {str(k): r1(v, 3) for k, v in sorted(removes.items()) if k >= 0 and v > 0.0005},
            "adds": {str(k): r1(v, 3) for k, v in sorted(adds.items()) if k >= 0},
        })
    return sorted(out, key=lambda x: x["usualIndex"])


def incidents(now, hours, rows, runs, trips, llm):
    """Reminders/tips first (as savings), then the biggest hours (as peaks) – three tiles."""
    out = []
    short = {"away-mode reminder": "Away mode", "dishwasher tip": "Dishwasher", "washing machine tip": "Washer",
             "heat pump setting tip": "HP schedule"}
    for t in reminders_and_tips(now, hours, rows, runs, trips, llm=llm)[:2]:
        out.append({"title": short.get(t["kind"], t["kind"]), "value": f"−{cents(t['saving_eur'])}",
                    "time": f"{t['send_at']:%a %H:%M}", "tone": "green"})
    for r in sorted(rows, key=lambda r: -r["total_real_kwh"]):
        if len(out) == 3:
            break
        block = max(BLOCK_TITLES, key=lambda b: r[b])
        out.append({"title": BLOCK_TITLES[block].split(" ")[0], "value": f"+{r['total_real_kwh']:.1f} kW",
                    "time": f"{r['timestamp']:%a %H:%M}", "tone": "accent"})
    return out


def summary(now, hours, rows):
    days = hours / 24
    real = sum(r["total_real_kwh"] for r in rows)
    past = [sum(history()[now - timedelta(hours=k + 1)].values()) for k in range(hours)
            if now - timedelta(hours=k + 1) in history()]
    past_total = sum(past) * hours / max(len(past), 1)
    peak = max(r["total_real_kwh"] for r in rows)
    usual_peak = sum(sorted(past, reverse=True)[:max(1, int(days))]) / max(1, int(days)) if past else peak
    cost = sum(r["cost_real_eur"] for r in rows)
    saved = cost - sum(r["cost_ideal_eur"] for r in rows)
    change = (real - past_total) / past_total if past_total else 0.0
    peak_change = (peak - usual_peak) / usual_peak if usual_peak else 0.0
    first = ({"label": "Total", "value": f"{real:.1f} kWh"} if hours == 24
             else {"label": "Avg daily", "value": f"{real / days:.1f} kWh"})
    return [
        {**first, "delta": f"{abs(change):.0%} vs " + {24: "yesterday", 72: "prev 3 d", 168: "prev wk"}[hours],
         "good": change <= 0},
        {"label": "Peak usage", "value": f"{peak:.1f} kW", "delta": f"{abs(peak_change):.0%} vs normal",
         "good": peak_change <= 0},
        {"label": "Total cost", "value": cents(cost), "delta": f"{cents(saved)} to save", "good": True,
         "accent": True},
    ]


def labels_for(rows, name):
    if name == "24h":
        return [f"{rows[i]['timestamp']:%H:%M}" for i in (0, 6, 12, 18, 23)]
    return [f"{rows[i]['timestamp']:%a}" for i in range(0, len(rows), 24)]


def label_indexes(rows, size, name):
    """Index (in the accumulated series) of each axis label, so the app can put them under their data points."""
    if name == "24h":
        return [0, 6, 12, 18, 23]
    return [i // size for i in range(0, len(rows), 24)]


SLOT_HOURS = (0, 6, 12, 18)                       # forecasts are precomputed for these hours of every day
DAY_DIR = ROOT / "data" / "app" / "forecast"      # one file per day: {"slots": {"00": {...}, "06": {...}, ...}}


def build(now, llm=None):
    """The forecast JSON (as a dict) for the moment `now`, using only the 30 days before it (year wraps around)."""
    set_now(now)
    llm = load_llm_results() if llm is None else llm
    usage = {}
    for name, (hours, size, subtitle) in RANGES.items():
        rows, runs, trips = forecast(now, hours, llm=llm)
        usage[name] = {
            "title": "Forecast Profile", "subtitle": subtitle, "stepHours": size, "labels": labels_for(rows, name),
            "labelIndexes": label_indexes(rows, size, name),
            "values": [r1(v, 3) for v in accumulate([r["total_real_kwh"] for r in rows], size)],
            "highlights": highlights(rows, size, 2 if name != "7d" else 3, runs),
            "why": why(now, hours, rows),
            "incidents": incidents(now, hours, rows, runs, trips, llm),
            "summaryTitle": {"24h": "Daily Summary", "3d": "3-Day Summary", "7d": "Weekly Summary"}[name],
            "summary": summary(now, hours, rows),
        }
        if name == "24h":
            indoor = rows[0]["indoor_temp_c"]
        if name == "7d":
            week_runs = runs
    return {
        "meta": {"now": now.isoformat(timespec="minutes"), "llm": f"{PROVIDER}:{MODEL}", "llm_days": len(llm),
                 "price_now": price(now), "window_days": WINDOW_DAYS},
        "user": USER,
        "now": {"hour": now.hour + now.minute / 60},
        "overview": overview(now),
        "peak": peak_hours(now),
        "home": {"temperature": {"value": f"{indoor:.1f}°C", "state": "Auto"}},
        "usage": usage,
        "shifts": shifts(now, week_runs),
    }


def check(now):
    if now.year != YEAR or now.minute:
        raise SystemExit(f"'now' must be on the hour in {YEAR} (the generated year), got {now:%Y-%m-%dT%H:%M}")


def main(now, out=OUT):
    check(now)
    data = build(now)
    data["meta"]["generated"] = datetime.now().isoformat(timespec="seconds")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}  (now {now:%a %d %b %H:%M}, LLM {PROVIDER}:{MODEL}, {data['meta']['llm_days']} days)")


def export_day(day):
    """All slots of one day -> data/app/forecast/<day>.json (compact)."""
    llm = load_llm_results()
    slots = {f"{h:02d}": build(datetime(day.year, day.month, day.day, h), llm) for h in SLOT_HOURS}
    (DAY_DIR / f"{day.isoformat()}.json").write_text(json.dumps({"slots": slots}, separators=(",", ":"), ensure_ascii=False))
    return day


def export_all(workers):
    """The whole year: 365 days x 4 slots (about 10 min single-core; runs in parallel)."""
    from multiprocessing import Pool
    DAY_DIR.mkdir(parents=True, exist_ok=True)
    for old in DAY_DIR.glob("*.json"):
        old.unlink()
    days = [date(YEAR, 1, 1) + timedelta(days=i) for i in range(365)]
    with Pool(workers) as pool:
        for i, day in enumerate(pool.imap_unordered(export_day, days), 1):
            if i % 30 == 0 or i == len(days):
                print(f"  {i}/{len(days)} days", flush=True)
    print(f"wrote {len(days)} day files to {DAY_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Export the forecast as JSON for the app.")
    ap.add_argument("now", nargs="?", default="2026-09-28T17:00", help="forecast start, local time on the hour")
    ap.add_argument("--out", type=Path, default=OUT, help=f"output file (default {OUT.relative_to(ROOT)})")
    ap.add_argument("--all", action="store_true", help=f"precompute every day of {YEAR} at {SLOT_HOURS} h -> {DAY_DIR.relative_to(ROOT)}/")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    args = ap.parse_args()
    if args.all:
        export_all(args.workers)
    else:
        main(datetime.fromisoformat(args.now), args.out.resolve())
