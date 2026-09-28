"""Step 4 – backtest on the test period (29 Sep – 12 Oct): a 24 h forecast every day at 00:00, plus one
7-day forecast, compared with the metered (simulated) consumption and with the true presence.

Usage: python3 src/backtest.py
"""
import csv
from datetime import datetime, timedelta

from hackowatt.data import ACTIVITIES, BASELOAD, history
from hackowatt.forecast import forecast
from hackowatt.paths import ROOT

TEST_START, TEST_DAYS = datetime(2026, 9, 29), 14
BLOCKS = {"baseload": (BASELOAD, "baseload_kwh"), "activities": (ACTIVITIES, "activities_kwh"),
          "washer/dishwasher": (["washing_machine", "dishwasher"], "appliances_kwh"),
          "space heating": (["heat_pump_space_heating"], "space_heating_kwh"),
          "hot water": (["heat_pump_hot_water"], "hot_water_kwh")}


def true_presence():
    with open(ROOT / "data" / "consumption" / "simulation_ground_truth.csv") as f:
        return {datetime.fromisoformat(r["timestamp"][:16]): float(r["aleksandra_home_share"]) for r in csv.DictReader(f)}


def main():
    hist, truth = history(), true_presence()
    err = {b: [] for b in BLOCKS}
    err_total, daily, presence = [], [], []
    for d in range(TEST_DAYS):
        start = TEST_START + timedelta(days=d)
        rows, _, _ = forecast(start, 24)
        day_f = day_a = 0.0
        for r in rows:
            actual = hist[r["timestamp"]]
            for b, (apps, col) in BLOCKS.items():
                err[b].append(abs(r[col] - sum(actual[a] for a in apps)))
            a_total = sum(actual.values())
            err_total.append(abs(r["total_real_kwh"] - a_total))
            day_f += r["total_real_kwh"]
            day_a += a_total
            if r["away_score"] <= 15 or r["away_score"] >= 85:
                presence.append(((r["away_score"] <= 15) == (truth[r["timestamp"]] >= 0.5), r["source"]))
        daily.append((start, day_f, day_a))

    print("24 h forecasts, test period 29 Sep – 12 Oct (every day at 00:00)")
    print(f"  {'day':10s} {'forecast':>9s} {'actual':>8s}")
    for s, f, a in daily:
        print(f"  {s:%a %d %b} {f:8.2f}  {a:7.2f}  {'+' if f >= a else '-'}{abs(f - a) / a:5.0%}")
    print(f"  mean absolute error per hour: total {sum(err_total) / len(err_total):.3f} kWh")
    for b, e in err.items():
        print(f"    {b:18s} {sum(e) / len(e):.3f} kWh")
    print(f"  daily total: mean absolute error {sum(abs(f - a) for _, f, a in daily) / len(daily):.2f} kWh "
          f"(actual mean {sum(a for _, _, a in daily) / len(daily):.2f} kWh/day)")
    for src in ("geolocation", "llm", "habits"):
        hits = [ok for ok, s in presence if s == src]
        if hits:
            print(f"  away score (confident hours, source {src}): {sum(hits)}/{len(hits)} correct "
                  f"({sum(hits) / len(hits):.0%})")

    rows, _, _ = forecast(TEST_START, 24 * 7)
    f7 = sum(r["total_real_kwh"] for r in rows)
    a7 = sum(sum(hist[r["timestamp"]].values()) for r in rows)
    print(f"\n7-day forecast from {TEST_START:%d %b}: {f7:.1f} kWh vs actual {a7:.1f} kWh ({(f7 - a7) / a7:+.0%})")


if __name__ == "__main__":
    main()
