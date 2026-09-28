"""Forecast for the next 24 h / 3 d / 7 d: real vs ideal consumption per hour, band, explanation,
reminders and tips. Run it with src/run_forecast.py.
"""
import csv
from datetime import datetime, timedelta

from .blocks.appliances import appliances
from .blocks.averages import activities, baseload
from .blocks.heat_pump import heat_pump
from .data import ACTIVITIES, BASELOAD, history, price, weather_forecast
from .ishome import absences, ishome, load_llm_results
from .paths import ROOT

REMINDER_MIN_EUR, TIP_MIN_EUR, TIP_MIN_P = 1.0, 0.10, 0.6
HP_BAND = 0.2                     # ±20 % around the heat-pump forecast
TRIP_LOOKAHEAD = timedelta(days=14)  # trips can end long after the window (whole absence for reminders)


def forecast(start, hours, llm=None):
    llm = load_llm_results() if llm is None else llm
    ish = ishome(start, hours, llm=llm)
    trips = absences(start - timedelta(days=1), start + timedelta(hours=hours) + TRIP_LOOKAHEAD, llm=llm)
    base = baseload(start, ish)
    act = activities(start, ish)
    app, runs = appliances(start, ish, trips)
    gains = [base[i]["real"] + act[i]["real"] + app[i]["real"] for i in range(hours)]
    hp_real = heat_pump(start, ish, trips, gains)
    hp_away = heat_pump(start, ish, trips, gains, away_mode=True)
    hp_ideal = heat_pump(start, ish, trips, gains, away_mode=True, shifting=True)
    wx = weather_forecast()

    rows = []
    for i, r in enumerate(ish):
        ts = r["timestamp"]
        hp_r = hp_real[i]["space"] + hp_real[i]["dhw"]
        real = base[i]["real"] + act[i]["real"] + app[i]["real"] + hp_r
        ideal = base[i]["ideal"] + act[i]["ideal"] + app[i]["ideal"] + hp_ideal[i]["space"] + hp_ideal[i]["dhw"]
        rows.append(dict(
            timestamp=ts, away_score=r["away_score"], people=r["people"], source=r["source"], reason=r["reason"],
            temp_out_c=wx[ts]["temp"], indoor_temp_c=round(hp_real[i]["t_in"], 2),
            baseload_kwh=base[i]["real"], activities_kwh=act[i]["real"], appliances_kwh=app[i]["real"],
            space_heating_kwh=hp_real[i]["space"], hot_water_kwh=hp_real[i]["dhw"],
            total_real_kwh=real, total_ideal_kwh=ideal,
            low_kwh=base[i]["low"] + act[i]["low"] + app[i]["low"] + hp_r * (1 - HP_BAND),
            high_kwh=base[i]["high"] + act[i]["high"] + app[i]["high"] + hp_r * (1 + HP_BAND),
            price_eur_kwh=price(ts), cost_real_eur=real * price(ts), cost_ideal_eur=ideal * price(ts),
            _hp_away=hp_away[i]["space"] + hp_away[i]["dhw"], _hp_real=hp_r,
            _hp_ideal=hp_ideal[i]["space"] + hp_ideal[i]["dhw"],
            _standby_saving=base[i]["real"] - base[i]["ideal"]))
    return rows, runs, trips


def reminders_and_tips(start, hours, rows, runs, trips, llm=None):
    out = []
    end = start + timedelta(hours=hours)
    by_ts = {r["timestamp"]: r for r in rows}
    # 1) away-mode reminder: 12 h before departure, saving >= €1, surely away
    for a in trips:
        if not (start <= a["departure"] < end) or a["min_score"] < 85:
            continue
        until = a["return"] + timedelta(hours=6)          # include the warm-up after the return
        full = by_ts
        if until > end:                                   # absence longer than the window: extend it
            ext_hours = min(int((until - start).total_seconds() // 3600) + 1, 24 * 14)
            full = {r["timestamp"]: r for r in forecast(start, ext_hours, llm=llm)[0]}
        span = [r for ts, r in full.items() if a["departure"] <= ts < until]
        saving = sum(((r["_hp_real"] - r["_hp_away"]) + r["_standby_saving"]) * r["price_eur_kwh"] for r in span)
        if saving >= REMINDER_MIN_EUR:
            out.append(dict(kind="away-mode reminder", send_at=max(start, a["departure"] - timedelta(hours=12)),
                            saving_eur=saving, text=f"You leave {a['departure']:%a %d %b %H:%M} for {a['nights']} "
                            f"night(s): switch the heat pump to holiday mode and turn off the power strip "
                            f"(saves ≈ €{saving:.2f})."))
    # 2) washer / dishwasher tips: likely run + cheaper allowed slot
    for run in runs:
        if run["p"] >= TIP_MIN_P and run["saving_eur"] >= TIP_MIN_EUR and run["ideal_start"] != run["usual_start"]:
            name = "Washing machine" if run["appliance"] == "washing_machine" else "Dishwasher"
            out.append(dict(kind=f"{name.lower()} tip", send_at=max(start, run["usual_start"] - timedelta(hours=1)),
                            saving_eur=run["saving_eur"],
                            text=f"{name} likely around {run['usual_start']:%a %H:%M} ({run['reason']}): use delay-start "
                                 f"at {run['ideal_start']:%a %H:%M} → saves ≈ €{run['saving_eur']:.2f}."))
    # 3) heat pump setting tip (once): hot water at night + pre-heating, scaled to a month
    shift = sum((r["_hp_away"] - r["_hp_ideal"]) * r["price_eur_kwh"] for r in rows)
    if shift > 0:
        out.append(dict(kind="heat pump setting tip", send_at=start, saving_eur=shift * 720 / hours,
                        text=f"Set the hot-water schedule to 03:00–06:00 and pre-heat to 22 °C from 15:00–17:00 "
                             f"→ saves ≈ €{shift * 720 / hours:.2f} per month."))
    return sorted(out, key=lambda t: t["send_at"])


def explain(start, hours, rows):
    """Change per block vs the same number of hours just before the forecast start."""
    hist = history()
    past = [hist[start - timedelta(hours=k + 1)] for k in range(hours) if start - timedelta(hours=k + 1) in hist]
    if len(past) < hours:
        return []
    groups = {"baseload": BASELOAD, "activities": ACTIVITIES, "washer/dishwasher": ["washing_machine", "dishwasher"],
              "space heating": ["heat_pump_space_heating"], "hot water": ["heat_pump_hot_water"]}
    cols = {"baseload": "baseload_kwh", "activities": "activities_kwh", "washer/dishwasher": "appliances_kwh",
            "space heating": "space_heating_kwh", "hot water": "hot_water_kwh"}
    lines = []
    for g, apps in groups.items():
        before = sum(sum(p[a] for a in apps) for p in past)
        after = sum(r[cols[g]] for r in rows)
        lines.append((after - before, g, before, after))
    return sorted(lines, key=lambda x: -abs(x[0]))


def write_csv(start, hours, rows):
    out = ROOT / "data" / "forecast"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"forecast_{start:%Y-%m-%dT%H%M}_{hours}h.csv"
    fields = [k for k in rows[0] if not k.startswith("_")]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else f"{v:%Y-%m-%dT%H:%M}" if isinstance(v, datetime) else v)
                        for k, v in r.items() if k in fields})
    return path
