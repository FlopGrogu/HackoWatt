"""Step 5 – export the forecast as JSON for the app: data/app/forecast.json.

Same keys as the app's demo data (app/js/data/demo.js): meta, user, now, overview, peak, home, usage
(24h / 3d / 7d). Not included (not computed by the forecast): humidity and the device list.

HOW TO GENERATE A NEW FORECAST
1. Environment (once): Python >= 3.10, e.g.
       conda create -n hackowatt python=3.10 && conda activate hackowatt
       pip install -r requirements.txt
2. Pick the moment "now" the app should show. Everything before "now" counts as the past (metered data),
   everything after it is forecast. It must be on the hour and between 2026-09-20T00:00 and 2026-10-05T23:00:
   the weather forecast in data/weather/ covers 20 Sep – 12 Oct and the 7-day view needs 7 days after "now".
3. Run
       python src/export_app_data.py 2026-10-04T09:00
   -> overwrites data/app/forecast.json (use --out other/file.json to write somewhere else).
   Without an argument "now" is 2026-09-28T17:00 (the version currently in the repository).
4. Only needed if the calendar (aleksandra_calendar.ics) changed: first let the LLM read the changed days,
       python src/interpret_calendar.py
   (Gemini key as API_KEY=... in the git-ignored .secret file). Unchanged days come from data/llm_cache/
   and cost nothing. If a day has no LLM result, the forecast falls back to her habits for that day.

Usage:  python src/export_app_data.py [now] [--out file.json]
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from hackowatt.data import history, price
from hackowatt.forecast import forecast, reminders_and_tips
from hackowatt.ishome import load_llm_results
from hackowatt.llm_ishome import MODEL, PROVIDER
from hackowatt.paths import ROOT

OUT = ROOT / "data" / "app" / "forecast.json"
USER = {"name": "Aleksandra", "initials": "A", "status": "All systems running normally"}
BLOCK_TITLES = {"space_heating_kwh": "Space heating", "hot_water_kwh": "Hot-water reheat",
                "appliances_kwh": "Washer / dishwasher", "activities_kwh": "Cooking & activities",
                "baseload_kwh": "Baseload"}
RANGES = {"24h": (24, 1, "Hour-level granularity (next 24 h)"),
          "3d": (72, 4, "4-hour totals (next 3 days)"),
          "7d": (168, 24, "Daily totals (next 7 days)")}


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
    return {"hours": [r1(v, 3) for v in hours], "from": start, "to": start + 3,
            "text": f"Your highest energy demand is typically between {start}–{start + 4} h on weekdays."}


def highlights(rows, size, count):
    """The `count` highest points of the (grouped) series, titled by the block that dominates them."""
    points = []
    for i in range(0, len(rows), size):
        chunk = rows[i:i + size]
        total = sum(r["total_real_kwh"] for r in chunk)
        block = max(BLOCK_TITLES, key=lambda b: sum(r[b] for r in chunk))
        when = (f"{chunk[0]['timestamp']:%a %-d %b}" if size == 24 else
                f"{chunk[0]['timestamp']:%a %-d %b %H:%M}" if len(rows) > 24 else f"{chunk[0]['timestamp']:%H:%M}")
        points.append(dict(index=i // size, title=BLOCK_TITLES[block], detail=f"{when} • {total:.2f} kWh", total=total))
    gap = 3 if size == 1 else 1 if size < 24 else 0     # don't pick neighbouring points of the same peak
    top = []
    for p in sorted(points, key=lambda p: -p["total"]):
        if len(top) < count and all(abs(p["index"] - q["index"]) > gap for q in top):
            top.append(p)
    return [{k: v for k, v in p.items() if k != "total"} for p in sorted(top, key=lambda p: p["index"])]


def incidents(now, hours, rows, runs, trips, llm):
    """Reminders/tips first (as savings), then the biggest hours (as peaks) – three tiles."""
    out = []
    short = {"away-mode reminder": "Away mode", "dishwasher tip": "Dishwasher", "washing machine tip": "Washer",
             "heat pump setting tip": "HP schedule"}
    for t in reminders_and_tips(now, hours, rows, runs, trips, llm=llm)[:2]:
        out.append({"title": short.get(t["kind"], t["kind"]), "value": f"−€{t['saving_eur']:.2f}",
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
        {"label": "Total cost", "value": f"€{cost:.2f}", "delta": f"€{saved:.2f} to save", "good": True,
         "accent": True},
    ]


def labels_for(rows, name):
    if name == "24h":
        return [f"{rows[i]['timestamp']:%H:%M}" for i in (0, 6, 12, 18, 23)]
    return [f"{rows[i]['timestamp']:%a}" for i in range(0, len(rows), 24)]


FIRST_NOW, LAST_NOW = datetime(2026, 9, 20, 0, 0), datetime(2026, 10, 5, 23, 0)


def main(now, out=OUT):
    if not FIRST_NOW <= now <= LAST_NOW or now.minute:
        raise SystemExit(f"'now' must be on the hour between {FIRST_NOW:%Y-%m-%dT%H:%M} and {LAST_NOW:%Y-%m-%dT%H:%M} "
                         f"(weather forecast data covers 20 Sep – 12 Oct), got {now:%Y-%m-%dT%H:%M}")
    llm = load_llm_results()
    usage = {}
    for name, (hours, size, subtitle) in RANGES.items():
        rows, runs, trips = forecast(now, hours, llm=llm)
        usage[name] = {
            "title": "Forecast Profile", "subtitle": subtitle, "stepHours": size, "labels": labels_for(rows, name),
            "values": [r1(v, 3) for v in accumulate([r["total_real_kwh"] for r in rows], size)],
            "highlights": highlights(rows, size, 2 if name != "7d" else 3),
            "incidents": incidents(now, hours, rows, runs, trips, llm),
            "summaryTitle": {"24h": "Daily Summary", "3d": "3-Day Summary", "7d": "Weekly Summary"}[name],
            "summary": summary(now, hours, rows),
        }
        if name == "24h":
            indoor = rows[0]["indoor_temp_c"]
    data = {
        "meta": {"generated": datetime.now().isoformat(timespec="seconds"), "now": now.isoformat(timespec="minutes"),
                 "llm": f"{PROVIDER}:{MODEL}", "llm_days": len(llm), "price_now": price(now)},
        "user": USER,
        "now": {"hour": now.hour + now.minute / 60},
        "overview": overview(now),
        "peak": peak_hours(now),
        "home": {"temperature": {"value": f"{indoor:.1f}°C", "state": "Auto"}},
        "usage": usage,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}  (now {now:%a %d %b %H:%M}, LLM {PROVIDER}:{MODEL}, {len(llm)} days)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Export the forecast as JSON for the app.")
    ap.add_argument("now", nargs="?", default="2026-09-28T17:00", help="forecast start, local time on the hour")
    ap.add_argument("--out", type=Path, default=OUT, help=f"output file (default {OUT.relative_to(ROOT)})")
    args = ap.parse_args()
    main(datetime.fromisoformat(args.now), args.out.resolve())
