"""Master script: regenerates every data set Aleksandra's scenario needs, end to end and reproducibly.

    weather      real Open-Meteo data of the weather year (observed + issued forecasts), replayed as the simulated year
    calendar     procedural .ics calendar (one file per month + merged year)
    itinerary    where she is minute by minute, parsed from the calendar
    consumption  hourly kWh per appliance, ground truth, appliance event log
    geolocation  phone position every 15 minutes

Usage
    python src/generate_all.py                                   # Warsaw, seed 2026, year 2026 (weather of 2025)
    python src/generate_all.py --seed 7                          # another random year
    python src/generate_all.py --lat 50.0647 --lon 19.945 --city Kraków --iata KRK
    python src/generate_all.py --offline                         # reuse the cached weather files
    python src/generate_all.py --stages calendar itinerary consumption geolocation

The same seed always gives byte-identical files. Human variability (departure times, meal times, durations, ...) is normally
distributed around habits; the seed changes every draw, the default seed is fixed.
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hackowatt.datagen.config import Config                    # noqa: E402
from hackowatt.datagen.places import Places                    # noqa: E402

STAGES = ["weather", "calendar", "itinerary", "consumption", "geolocation"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=Config.seed, help="random seed (default %(default)s)")
    ap.add_argument("--lat", type=float, default=Config.lat, help="city latitude (weather, sun, local places)")
    ap.add_argument("--lon", type=float, default=Config.lon, help="city longitude")
    ap.add_argument("--city", default=Config.city, help="city name used in calendar entries")
    ap.add_argument("--iata", default=Config.iata, help="home airport code used in flight entries")
    ap.add_argument("--tz", default=Config.tz, help="IANA time zone")
    ap.add_argument("--year", type=int, default=Config.year, help="simulated year")
    ap.add_argument("--weather-year", type=int, default=Config.weather_year, help="real year whose weather is replayed")
    ap.add_argument("--today", default="2026-09-29", help="first 'future' day (rows before it are labelled history)")
    ap.add_argument("--target-away", type=float, default=Config.target_away, help="share of the year spent on trips")
    ap.add_argument("--no-report", action="store_true", help="skip figures and validation.md")
    ap.add_argument("--offline", action="store_true", help="do not download, use cached weather")
    ap.add_argument("--stages", nargs="+", choices=STAGES, default=STAGES, help="run only these stages (inputs of skipped stages are read from disk)")
    a = ap.parse_args()
    cfg = Config(seed=a.seed, lat=a.lat, lon=a.lon, city=a.city, iata=a.iata, tz=a.tz, year=a.year, weather_year=a.weather_year,
                 today=datetime.fromisoformat(a.today), offline=a.offline, target_away=a.target_away)
    places = Places(cfg)
    run = set(a.stages)
    t0 = time.time()

    def step(name):
        print(f"[{name}]", flush=True)
        return time.time()

    weather = events = itin = None
    if "weather" in run or "consumption" in run:
        t = step("weather")
        from hackowatt.datagen.weather import Weather
        weather = Weather(cfg)
        if "weather" in run:
            weather.write()
        print(f"  {len(weather.times)} hours, {min(weather.temp):.1f}..{max(weather.temp):.1f} °C (mean {sum(weather.temp) / len(weather.temp):.1f}), "
              f"forecast-vs-observed MAE {sum(abs(x - y) for x, y in zip(weather.temp, weather.temp_fc)) / len(weather.temp):.2f} °C")
    if "calendar" in run:
        step("calendar")
        from hackowatt.datagen.calendar_gen import generate, write_calendar
        events, stats = generate(cfg, places)
        out = write_calendar(cfg, events)
        print(f"  {len(events)} entries -> {out}  {stats}")
    if run & {"itinerary", "consumption", "geolocation"}:
        step("itinerary")
        from hackowatt.datagen.itinerary import Itinerary
        itin = Itinerary(cfg, places)
        itin.write()
        trips = [t for t in itin.trips if t.nights >= 1]
        print(f"  {len(itin.segs)} segments, away {itin.away.mean():.1%} of the year, {len(itin.trips)} trips ({len(trips)} with nights), "
              f"Paul home {itin.paul_in.mean():.1%}, guests present {(itin.guests > 0).mean():.1%}")
    if "consumption" in run:
        step("consumption")
        from hackowatt.datagen.consumption import Simulation
        from hackowatt.datagen.ics import read_ics
        sim = Simulation(cfg, weather, itin, read_ics(cfg.full_calendar)).run()
        out = sim.write()
        for w in sim.warnings[:5]:
            print("  WARN", w)
        if not a.no_report:
            from hackowatt.datagen import report
            report.validation(cfg, sim, itin)
            try:
                report.figures(cfg)
            except ImportError:
                print("  (matplotlib not installed: figures skipped)")
        print(f"  {len(sim.log)} appliance runs, {sim.total.sum():.0f} kWh in the year ({sim.total.mean() * 24:.1f} kWh/day) -> {out}")
    if "geolocation" in run:
        step("geolocation")
        from hackowatt.datagen.geolocation import write_positions
        print(f"  {write_positions(cfg, itin)} positions -> {cfg.data / 'geolocation' / 'positions.csv'}")
    print(f"done in {time.time() - t0:.1f} s (seed {cfg.seed})")


if __name__ == "__main__":
    main()
