"""Weather stage: real Open-Meteo data of `weather_year`, replayed as `year`.

Two series are downloaded for the city coordinates:
  * Historical Weather API (reanalysis, "what really happened")   -> drives the simulated consumption
  * Historical Forecast API (the forecasts as they were issued)   -> what the forecasting model gets to see
Raw responses are cached in data/weather/; the request URLs are written to SOURCE_URLS.txt.
"""
import csv
import json
import urllib.request
from datetime import datetime

VARS = "temperature_2m,relative_humidity_2m,cloud_cover,shortwave_radiation,wind_speed_10m"
APIS = {
    "archive": ("https://archive-api.open-meteo.com/v1/archive", "Historical Weather API (observed / reanalysis)"),
    "forecast": ("https://historical-forecast-api.open-meteo.com/v1/forecast", "Historical Forecast API (issued forecasts)"),
}


def _url(kind, cfg):
    return (f"{APIS[kind][0]}?latitude={cfg.lat}&longitude={cfg.lon}&timezone={cfg.tz.replace('/', '%2F')}"
            f"&start_date={cfg.weather_year}-01-01&end_date={cfg.weather_year}-12-31&hourly={VARS}&daily=sunrise,sunset")


def _fetch(kind, cfg):
    d = cfg.data / "weather"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"openmeteo_{kind}_{cfg.weather_year}.json"
    url = _url(kind, cfg)
    meta = path.with_suffix(".url")
    if path.exists() and meta.exists() and meta.read_text().strip() == url:
        return json.loads(path.read_text())
    if cfg.offline:
        if path.exists():
            print(f"  [offline] using cached {path.name} (request parameters not verified)")
            return json.loads(path.read_text())
        raise SystemExit(f"--offline but {path} is missing")
    print(f"  downloading {kind}: {url}")
    with urllib.request.urlopen(url, timeout=120) as r:
        raw = r.read()
    data = json.loads(raw)
    if "hourly" not in data:
        raise SystemExit(f"Open-Meteo error: {data}")
    path.write_bytes(raw)
    meta.write_text(url + "\n")
    return data


def _relabel(dt, cfg):
    return dt.replace(year=cfg.year)


def _parse(data, cfg):
    h = data["hourly"]
    times = [_relabel(datetime.fromisoformat(t), cfg) for t in h["time"]]
    rows = {k: h[k] for k in ("temperature_2m", "relative_humidity_2m", "cloud_cover", "shortwave_radiation", "wind_speed_10m")}
    for k, v in rows.items():
        # short gaps (e.g. a missing model hour) are bridged linearly, so the simulation never sees a hole
        for i, x in enumerate(v):
            if x is None:
                j = next((j for j in range(i + 1, len(v)) if v[j] is not None), None)
                prev = v[i - 1] if i else None
                v[i] = prev if j is None else v[j] if prev is None else prev + (v[j] - prev) / (j - i + 1)
    sun = {}
    for i, day in enumerate(data["daily"]["time"]):
        d = _relabel(datetime.fromisoformat(day), cfg).date()
        sun[d] = (_relabel(datetime.fromisoformat(data["daily"]["sunrise"][i]), cfg),
                  _relabel(datetime.fromisoformat(data["daily"]["sunset"][i]), cfg))
    return times, rows, sun


class Weather:
    """Hourly series on the simulation grid. `*_fc` = issued forecast, the others = observed."""

    def __init__(self, cfg):
        obs = _parse(_fetch("archive", cfg), cfg)
        fc = _parse(_fetch("forecast", cfg), cfg)
        self.times = obs[0]
        expected = cfg.hours
        if len(self.times) != expected or fc[0] != self.times:
            raise SystemExit(f"weather grid mismatch: {len(self.times)} observed / {len(fc[0])} forecast hours, expected {expected}")
        o, f = obs[1], fc[1]
        self.temp, self.cloud, self.rad = o["temperature_2m"], o["cloud_cover"], o["shortwave_radiation"]
        self.rh, self.wind = o["relative_humidity_2m"], o["wind_speed_10m"]
        self.temp_fc, self.cloud_fc, self.rad_fc = f["temperature_2m"], f["cloud_cover"], f["shortwave_radiation"]
        self.rh_fc, self.wind_fc = f["relative_humidity_2m"], f["wind_speed_10m"]
        self.sun = obs[2]
        self.source = f"open-meteo archive {cfg.weather_year} (replayed as {cfg.year})"
        self.cfg = cfg

    def write(self):
        d = self.cfg.data / "weather"
        for name, cols in (("weather_hourly.csv", (self.temp, self.cloud, self.rad, self.rh, self.wind)),
                           ("weather_forecast_hourly.csv", (self.temp_fc, self.cloud_fc, self.rad_fc, self.rh_fc, self.wind_fc))):
            with open(d / name, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "temp_out_c", "cloud_cover_pct", "shortwave_radiation_wm2", "relative_humidity_pct", "wind_speed_kmh"])
                for i, t in enumerate(self.times):
                    w.writerow([t.strftime("%Y-%m-%dT%H:%M")] + [c[i] for c in cols])
        with open(d / "sun_times.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "sunrise", "sunset"])
            for day, (a, b) in sorted(self.sun.items()):
                w.writerow([day.isoformat(), a.strftime("%H:%M"), b.strftime("%H:%M")])
        lines = [f"Downloaded by src/generate_all.py for {self.cfg.city} {self.cfg.lat}N {self.cfg.lon}E ({self.cfg.tz}).",
                 f"The {self.cfg.weather_year} weather is replayed as {self.cfg.year} (same month/day/hour).", ""]
        for kind, (_, label) in APIS.items():
            lines += [f"openmeteo_{kind}_{self.cfg.weather_year}.json  – {label}", _url(kind, self.cfg), ""]
        (d / "SOURCE_URLS.txt").write_text("\n".join(lines))
        return d
