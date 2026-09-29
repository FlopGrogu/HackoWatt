"""Shared inputs for the forecast: consumption history, weather forecast, tariff, thermostat reading."""
import csv
from datetime import datetime
from functools import lru_cache

from .ishome import distance_m, load_positions
from .paths import ROOT

APPLIANCES = ["fridge", "heat_pump_space_heating", "heat_pump_hot_water", "kettle", "coffee_machine", "oven",
              "washing_machine", "dishwasher", "tv", "laptop", "wifi_router", "lighting",
              "phone_tablet_charging", "standby"]
BASELOAD = ["fridge", "wifi_router", "standby"]
ACTIVITIES = ["kettle", "coffee_machine", "oven", "tv", "laptop", "lighting", "phone_tablet_charging"]


def _ts(s):
    return datetime.fromisoformat(s[:16])


@lru_cache(maxsize=None)
def history():
    """All metered hours: {timestamp: {appliance: kWh}} (callers only use hours before the forecast start)."""
    out = {}
    with open(ROOT / "data" / "consumption" / "hourly_consumption.csv") as f:
        for r in csv.DictReader(f):
            out[_ts(r["timestamp"])] = {a: float(r[f"{a}_kwh"]) for a in APPLIANCES}
    return out


@lru_cache(maxsize=None)
def weather_forecast():
    """Weather forecast as it was issued (Open-Meteo Historical Forecast API, whole year): {timestamp: {temp, rad}}."""
    with open(ROOT / "data" / "weather" / "weather_forecast_hourly.csv") as f:
        return {_ts(r["timestamp"]): dict(temp=float(r["temp_out_c"]), rad=float(r["shortwave_radiation_wm2"])) for r in csv.DictReader(f)}


def price(ts):
    """Official HackoWatt tariff, €/kWh."""
    return 0.18 if ts.hour < 6 else 0.28 if ts.hour < 17 else 0.40 if ts.hour < 22 else 0.28


@lru_cache(maxsize=None)
def _thermostat():
    with open(ROOT / "data" / "consumption" / "simulation_ground_truth.csv") as f:
        return {_ts(r["timestamp"]): float(r["indoor_temp_c"]) for r in csv.DictReader(f)}


def thermostat_reading(ts):
    """Indoor temperature at the forecast start. In reality read from the thermostat; here taken from the
    simulation (the only ground-truth value used, and only as the starting state)."""
    return _thermostat()[ts]


@lru_cache(maxsize=None)
def home_hours_observed():
    """{hour timestamp: True/False} – was she home, according to past phone positions (observable)."""
    acc = {}
    for ts, lat, lon in load_positions():
        acc.setdefault(ts.replace(minute=0), []).append(distance_m(lat, lon) < 150)
    return {k: sum(v) / len(v) >= 0.5 for k, v in acc.items()}
