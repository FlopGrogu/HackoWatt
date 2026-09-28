"""Step 3 – forecast for the next 24 h / 3 d / 7 d: real vs ideal consumption, band, peak hours,
explanation, reminders and tips. Uses cached LLM results if present (falls back to habits otherwise).

Usage:  python3 src/run_forecast.py 2026-09-28T17:00 24     # start (local time, on the hour), hours
Writes data/forecast/forecast_<start>_<hours>h.csv and prints a summary.
"""
import sys
from datetime import datetime

from hackowatt.forecast import explain, forecast, reminders_and_tips, write_csv
from hackowatt.ishome import load_llm_results
from hackowatt.paths import ROOT


def main(start, hours):
    llm = load_llm_results()
    rows, runs, trips = forecast(start, hours, llm=llm)
    path = write_csv(start, hours, rows)
    real = sum(r["total_real_kwh"] for r in rows)
    ideal = sum(r["total_ideal_kwh"] for r in rows)
    print(f"Forecast {start:%a %d %b %H:%M} + {hours} h  ->  {path.relative_to(ROOT)}")
    print(f"  real  {real:6.2f} kWh  €{sum(r['cost_real_eur'] for r in rows):6.2f}   "
          f"(band {sum(r['low_kwh'] for r in rows):.1f}–{sum(r['high_kwh'] for r in rows):.1f} kWh)")
    print(f"  ideal {ideal:6.2f} kWh  €{sum(r['cost_ideal_eur'] for r in rows):6.2f}")
    sources = {s: sum(1 for r in rows if r["source"] == s) for s in ("geolocation", "llm", "habits")}
    print(f"  isHome sources (hours): {sources}")
    print("  peak hours: " + ", ".join(f"{r['timestamp']:%a %H:%M} {r['total_real_kwh']:.2f} kWh"
                                       for r in sorted(rows, key=lambda r: -r["total_real_kwh"])[:3]))
    print("  explanation (vs previous period):")
    for diff, g, before, after in explain(start, hours, rows):
        print(f"    {g:18s} {before:6.2f} -> {after:6.2f} kWh ({diff:+.2f})")
    print("  reminders & tips:")
    for t in reminders_and_tips(start, hours, rows, runs, trips, llm=llm):
        print(f"    [{t['send_at']:%a %d %H:%M}] {t['kind']}: {t['text']}")


if __name__ == "__main__":
    s = datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime(2026, 9, 29, 0, 0)
    main(s, int(sys.argv[2]) if len(sys.argv) > 2 else 24)
