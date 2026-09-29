"""PV simulator: what a shared/community PV share of k kWp would do for Aleksandra's household over the simulated year.

Solar production: PVGIS 5.3 hourly series (JRC, EU) for 1 kWp at the household location – south, 35° tilt,
14 % system losses (PVGIS defaults), radiation year 2023 (latest available), mapped onto 2026 by date and local hour.
Her PV share counts hour by hour as if it were on her own meter: used directly up to her demand, the rest exported.

Scenarios (challenge section 05):
  A  PV, no change of habits                → her metered consumption as it is
  B  PV + shifting selected activities       → washing machine, dishwasher and hot-water reheating moved to the
                                               cheapest allowed hours, where "cheap" includes her own PV surplus
Economics (common challenge assumptions): €1,300/kWp, export €0.08/kWh, operating cost 1 %/year of the investment,
time-of-use tariff for grid purchases. Simple payback = investment / (annual saving − operating cost).
"""
import csv
import json
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .paths import ROOT

LAT, LON = 52.2297, 21.0122
PVGIS_URL = ("https://re.jrc.ec.europa.eu/api/v5_3/seriescalc?lat={lat}&lon={lon}&peakpower=1&loss=14&angle=35&aspect=0"
             "&pvcalculation=1&outputformat=json&startyear=2023&endyear=2023")
PVGIS_FILE = ROOT / "data" / "weather" / "pvgis_warsaw_2023.json"
CONSUMPTION = ROOT / "data" / "consumption" / "hourly_consumption.csv"
GROUND_TRUTH = ROOT / "data" / "consumption" / "simulation_ground_truth.csv"
TZ = ZoneInfo("Europe/Warsaw")

COST_PER_KWP = 1300.0          # € (common challenge assumptions)
EXPORT_PRICE = 0.08            # €/kWh
OPERATING_COST = 0.01          # share of the investment per year
SIZES = range(0, 7)            # kWp; 0 = no PV (shows the effect of shifting alone)
DHW_MAX_KW = 1.6               # heat pump electrical power while heating water
DHW_BUFFER_KWH = 2.8           # electricity the 150 L tank can store (≈ 7 kWh heat at COP 2.5): one day of hot water
STEP = 0.1                     # kWh, granularity when re-placing hot-water heating


def price(hour):
    """Official HackoWatt time-of-use tariff, €/kWh."""
    return 0.18 if hour < 6 else 0.28 if hour < 17 else 0.40 if hour < 22 else 0.28


# ---------------------------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------------------------
def pvgis_series(offline=False):
    """PVGIS hourly output for 1 kWp; downloaded once and cached (with the request URL) next to the weather data."""
    url = PVGIS_URL.format(lat=LAT, lon=LON)
    if not PVGIS_FILE.exists():
        if offline:
            raise SystemExit(f"{PVGIS_FILE.name} missing – run once without --offline")
        with urllib.request.urlopen(url, timeout=120) as resp:
            PVGIS_FILE.write_bytes(resp.read())
        PVGIS_FILE.with_suffix(".url").write_text(url + "\n")
    return json.loads(PVGIS_FILE.read_text())


def load_year():
    """The simulated year: timestamps, total demand and the shiftable parts per hour, plus presence."""
    rows = list(csv.DictReader(open(CONSUMPTION)))
    home = {r["timestamp"]: float(r["aleksandra_home_share"]) for r in csv.DictReader(open(GROUND_TRUTH))}
    col = lambda name: [float(r[name]) for r in rows]
    return dict(
        ts=[datetime.fromisoformat(r["timestamp"]) for r in rows],
        total=col("total_kwh"), washer=col("washing_machine_kwh"), dishwasher=col("dishwasher_kwh"),
        hot_water=col("heat_pump_hot_water_kwh"), home=[home.get(r["timestamp"], 0.0) for r in rows],
    )


def pv_per_kwp(ts, series):
    """kWh per hour for 1 kWp, aligned with the consumption hours (PVGIS 2023 UTC → Warsaw local → same date in 2026)."""
    by_key = {}
    for h in series["outputs"]["hourly"]:
        t = datetime.strptime(h["time"], "%Y%m%d:%H%M").replace(tzinfo=timezone.utc).astimezone(TZ)
        by_key[(t.month, t.day, t.hour)] = h["P"] / 1000.0          # mean W over the hour = Wh
    out = []
    for t in ts:
        key = (t.month, t.day, t.hour)
        # the DST switch days differ between 2023 and 2026: fall back to the neighbouring hour
        out.append(by_key.get(key, by_key.get((t.month, t.day, (t.hour + 1) % 24), 0.0)))
    return out


# ---------------------------------------------------------------------------------------------------------------
# Energy balance
# ---------------------------------------------------------------------------------------------------------------
def hour_cost(demand, pv, p):
    """€ for one hour: grid purchases at the tariff minus export revenue."""
    return max(demand - pv, 0.0) * p - max(pv - demand, 0.0) * EXPORT_PRICE


def balance(demand, pv, prices):
    used = [min(d, s) for d, s in zip(demand, pv)]
    grid = [d - u for d, u in zip(demand, used)]
    export = [s - u for s, u in zip(pv, used)]
    return dict(demand=sum(demand), production=sum(pv), used=sum(used), grid=sum(grid), export=sum(export),
                cost=sum(g * p for g, p in zip(grid, prices)) - sum(export) * EXPORT_PRICE,
                monthly=None)


def monthly(ts, demand, pv):
    m = {k: dict(demand=0.0, production=0.0, used=0.0, grid=0.0, export=0.0) for k in range(1, 13)}
    for t, d, s in zip(ts, demand, pv):
        u = min(d, s)
        x = m[t.month]
        x["demand"] += d; x["production"] += s; x["used"] += u; x["grid"] += d - u; x["export"] += s - u
    return [{k: round(v, 1) for k, v in m[i].items()} for i in range(1, 13)]


# ---------------------------------------------------------------------------------------------------------------
# Scenario B: shifting
# ---------------------------------------------------------------------------------------------------------------
def runs(series):
    """Runs = consecutive hours with consumption: (start index, [kWh per hour])."""
    out, cur = [], None
    for i, v in enumerate(series):
        if v > 1e-9:
            if cur is None:
                cur = (i, [])
                out.append(cur)
            cur[1].append(v)
        else:
            cur = None
    return out


def shifted_demand(year, pv, prices):
    """Demand after moving hot-water heating (within its day) and washer/dishwasher runs (up to 24 h later) to the
    hours where they cost least, given the PV surplus. Energy is conserved; returns (demand, moved kWh)."""
    n = len(year["total"])
    cur = [t - w - d - h for t, w, d, h in zip(year["total"], year["washer"], year["dishwasher"], year["hot_water"])]
    extra = lambda i, x: hour_cost(cur[i] + x, pv[i], prices[i]) - hour_cost(cur[i], pv[i], prices[i])
    moved = 0.0

    # hot water: re-place each day's heating (up to one tank of it) in 0.1 kWh steps, ≤ 1.6 kWh per hour
    days = {}
    for i, t in enumerate(year["ts"]):
        days.setdefault(t.date(), []).append(i)
    for hours in days.values():
        total = sum(year["hot_water"][i] for i in hours)
        movable = min(total, DHW_BUFFER_KWH)
        keep = 1 - movable / total if total else 1.0
        placed = {i: year["hot_water"][i] * keep for i in hours}
        for i in hours:
            cur[i] += placed[i]
        left = movable
        while left > 1e-9:
            x = min(STEP, left)
            options = [i for i in hours if placed[i] + x <= DHW_MAX_KW + 1e-9]
            best = min(options, key=lambda i: (extra(i, x), i))
            cur[best] += x
            placed[best] += x
            left -= x
        moved += sum(abs(placed[i] - year["hot_water"][i]) for i in hours) / 2

    # washer / dishwasher: same run, delay-start 0–23 h
    jobs = [("washer", r) for r in runs(year["washer"])] + [("dishwasher", r) for r in runs(year["dishwasher"])]
    for kind, (start, kwh) in sorted(jobs, key=lambda j: j[1][0]):
        best, best_cost = start, None
        for c in range(start, min(start + 24, n - len(kwh))):
            end = c + len(kwh) - 1
            if kind == "washer" and not (year["home"][end] >= 0.5 and year["home"][min(end + 1, n - 1)] >= 0.5):
                continue                                   # she must be home when it finishes (and to hang it up)
            cost = sum(extra(c + k, v) for k, v in enumerate(kwh))
            if best_cost is None or cost < best_cost - 1e-9:
                best, best_cost = c, cost
        for k, v in enumerate(kwh):
            cur[best + k] += v
        if best != start:
            moved += sum(kwh)
    return cur, moved


# ---------------------------------------------------------------------------------------------------------------
# Simulation over all sizes
# ---------------------------------------------------------------------------------------------------------------
def simulate(offline=False, sizes=SIZES):
    year = load_year()
    series = pvgis_series(offline)
    per_kwp = pv_per_kwp(year["ts"], series)
    prices = [price(t.hour) for t in year["ts"]]
    zero = [0.0] * len(prices)
    reference = balance(year["total"], zero, prices)            # today: no PV, no shifting

    results = []
    for kwp in sizes:
        pv = [kwp * x for x in per_kwp]
        invest = kwp * COST_PER_KWP
        opex = invest * OPERATING_COST
        row = dict(kwp=kwp, investment=invest, operating_cost=opex, production=sum(pv))
        for name, demand, moved in (("A", year["total"], 0.0), ("B", *shifted_demand(year, pv, prices))):
            b = balance(demand, pv, prices)
            saving = reference["cost"] - b["cost"] - opex
            row[name] = dict(
                cost=round(b["cost"], 2), saving=round(saving, 2),
                grid=round(b["grid"], 1), grid_reduction=round(reference["grid"] - b["grid"], 1),
                used=round(b["used"], 1), export=round(b["export"], 1), moved=round(moved, 1),
                self_sufficiency=round(b["used"] / b["demand"], 3) if b["demand"] else 0.0,
                self_consumption=round(b["used"] / b["production"], 3) if b["production"] else 0.0,
                payback_years=round(invest / saving, 1) if invest and saving > 0 else None,
                monthly=monthly(year["ts"], demand, pv),
            )
        results.append(row)
    meta = dict(
        source="PVGIS 5.3 (JRC, European Commission), radiation database PVGIS-SARAH3, year 2023",
        url=PVGIS_URL.format(lat=LAT, lon=LON), location=dict(lat=LAT, lon=LON),
        system=dict(tilt_deg=35, azimuth="south", losses_pct=14), yield_kwh_per_kwp=round(sum(per_kwp)),
        cost_per_kwp=COST_PER_KWP, export_price=EXPORT_PRICE, operating_cost_share=OPERATING_COST,
        tariff="00–06 €0.18 · 06–17 €0.28 · 17–22 €0.40 · 22–24 €0.28",
        consumption_kwh=round(reference["demand"]), cost_without_pv=round(reference["cost"], 2),
        year=f"{year['ts'][0]:%Y-%m-%d} – {year['ts'][-1]:%Y-%m-%d}",
    )
    return meta, results
