"""Simulate Aleksandra's appliance usage minute by minute (1 Sep - 12 Oct 2026) and aggregate to hourly kWh.

Inputs : the day plan below (transcribed from aleksandra_calendar.ics) and Open-Meteo weather in data/weather/.
Outputs: data/consumption/hourly_consumption.csv  (one row per hour, kWh per appliance)
         data/consumption/appliance_events.csv    (one row per appliance run)
See docs/ASSUMPTIONS.md for every parameter and behavioural rule.
"""
import csv
import json
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 2026
rng = random.Random(SEED)

START = datetime(2026, 9, 1)
END = datetime(2026, 10, 13)            # exclusive
HISTORY_END = datetime(2026, 9, 29)     # "today" is 28 Sep: everything from 29 Sep on is future
N = int((END - START).total_seconds() // 60)

APPLIANCES = ["fridge", "heat_pump_space_heating", "heat_pump_hot_water", "kettle", "coffee_machine", "oven",
              "washing_machine", "dishwasher", "tv", "laptop", "wifi_router", "lighting",
              "phone_tablet_charging", "standby"]


def t(s):
    """'MM-DD HH:MM' -> datetime in 2026."""
    return datetime.strptime(f"2026-{s}", "%Y-%m-%d %H:%M")


def mi(x):
    """datetime or 'MM-DD HH:MM' -> minute index from START."""
    if isinstance(x, str):
        x = t(x)
    return int((x - START).total_seconds() // 60)


def mask(intervals):
    arr = [False] * N
    for a, b, *_ in intervals:
        for i in range(max(0, mi(a)), min(N, mi(b))):
            arr[i] = True
    return arr


# =====================================================================================
# Day plan (from the calendar)
# =====================================================================================
# Periods when Aleksandra is NOT in the apartment (incl. travel time to/from stations & airports).
AWAY = [
    ("09-01 00:00", "09-01 13:20", "Holiday in Split, lands WAW 12:40"),
    ("09-02 08:15", "09-02 21:20", "Office + bouldering"),
    ("09-03 15:20", "09-04 22:20", "Stockholm trip"),
    ("09-05 09:30", "09-05 10:30", "Run Pole Mokotowskie"),
    ("09-05 14:55", "09-05 16:30", "Picking up Paul at Centralna"),
    ("09-06 11:05", "09-06 14:30", "Brunch pl. Zbawiciela"),
    ("09-07 11:45", "09-07 12:45", "Bringing Paul to the train"),
    ("09-08 08:10", "09-08 17:50", "Office"),
    ("09-08 19:10", "09-08 22:35", "Dinner with Kasia"),
    ("09-09 05:50", "09-09 22:50", "Kraków day trip"),
    ("09-10 07:40", "09-10 09:05", "Dentist"),
    ("09-11 14:30", "09-13 22:20", "Berlin weekend with Paul"),
    ("09-14 08:15", "09-14 18:10", "Office"),
    ("09-15 06:20", "09-17 20:25", "Brussels forum"),
    ("09-19 09:30", "09-20 17:40", "Mazury - Marta's 40th"),
    ("09-21 12:35", "09-22 16:35", "Gdańsk trip"),
    ("09-22 19:00", "09-22 20:50", "Picking up Paul at WAW"),
    ("09-24 08:20", "09-24 18:15", "Office"),
    ("09-25 08:15", "09-25 23:20", "Office + drinks + cinema"),
    ("09-26 08:50", "09-27 19:05", "Łódź - parents"),
    ("09-28 08:15", "09-28 18:00", "Office"),
    ("09-28 18:15", "09-28 19:35", "Physio"),
    ("09-29 05:30", "10-04 22:55", "Berlin client week + weekend with Paul"),
    ("10-05 18:40", "10-05 21:20", "Bouldering"),
    ("10-06 08:10", "10-06 17:45", "Office"),
    ("10-07 05:30", "10-09 22:20", "Stockholm trip"),
    ("10-10 09:15", "10-10 11:10", "Hala Mirowska market"),
    ("10-10 12:00", "10-10 13:45", "Picking up Paul at WAW"),
    ("10-11 10:15", "10-11 11:45", "Run in Łazienki with Paul"),
    ("10-11 14:40", "10-11 16:40", "Coffee with Ola"),
]
# Trips where she remembered to switch the heat pump to holiday mode (16 °C, hot water off) and
# switch off the power strip. 3 of 10 trips = 30 %.
HOLIDAY_MODE = [
    ("09-15 06:20", "09-17 20:25"),   # Brussels
    ("09-26 08:50", "09-27 19:05"),   # Łódź
    ("10-07 05:30", "10-09 22:20"),   # Stockholm
]
PAUL_STAY = [("09-05 16:30", "09-07 11:45"), ("09-22 20:50", "09-24 05:45"), ("10-10 13:45", "10-12 14:30")]
PAUL_OUT = [("09-06 11:05", "09-06 14:30"), ("09-07 11:45", "09-07 12:45"), ("10-11 10:15", "10-11 11:45")]
GUESTS = [("09-18 19:00", "09-18 23:40", 5), ("09-23 19:00", "09-23 23:00", 2), ("10-10 18:30", "10-11 00:20", 5)]
# (bedtime, wake-up) for every night she sleeps at home.
SLEEP = [
    ("09-01 22:45", "09-02 06:40"), ("09-02 23:15", "09-03 06:35"), ("09-04 23:15", "09-05 07:45"),
    ("09-05 23:45", "09-06 08:30"), ("09-06 23:30", "09-07 07:00"), ("09-07 23:00", "09-08 06:30"),
    ("09-08 23:10", "09-09 05:15"), ("09-09 23:20", "09-10 06:50"), ("09-10 23:00", "09-11 06:45"),
    ("09-13 23:15", "09-14 06:40"), ("09-14 22:45", "09-15 05:30"), ("09-17 23:00", "09-18 07:00"),
    ("09-19 00:15", "09-19 08:00"), ("09-20 22:45", "09-21 06:45"), ("09-22 23:30", "09-23 07:00"),
    ("09-23 23:45", "09-24 05:30"), ("09-24 22:45", "09-25 06:40"), ("09-25 23:50", "09-26 07:30"),
    ("09-27 23:00", "09-28 06:35"), ("09-28 23:00", "09-29 04:50"), ("10-04 23:30", "10-05 07:00"),
    ("10-05 23:15", "10-06 06:30"), ("10-06 22:45", "10-07 04:50"), ("10-09 23:10", "10-10 08:00"),
    ("10-11 00:45", "10-11 09:00"), ("10-11 23:30", "10-12 07:00"), ("10-12 22:45", "10-13 06:40"),
]
# Laptop work blocks (WFH days); lunch breaks are cut out automatically.
WFH = [
    ("09-03 08:15", "09-03 15:10"), ("09-07 08:30", "09-07 11:40"), ("09-07 12:50", "09-07 17:30"),
    ("09-10 09:10", "09-10 18:00"), ("09-11 08:30", "09-11 14:20"), ("09-18 08:45", "09-18 16:45"),
    ("09-21 08:15", "09-21 12:20"), ("09-23 08:30", "09-23 17:30"), ("10-05 08:30", "10-05 13:55"),
    ("10-05 15:30", "10-05 18:20"), ("10-12 08:30", "10-12 17:30"),
]
PAUL_LAPTOP = [("09-07 08:30", "09-07 11:30"), ("09-23 09:00", "09-23 17:30"), ("10-12 09:00", "10-12 14:00")]
TV = [("09-05 21:30", 105, "Evening with Paul"), ("09-06 20:00", 150, "Movie night with Paul"),
      ("09-20 20:00", 120, "Tired after Mazury"), ("10-11 20:30", 120, "Evening with Paul")]
OVEN = [
    ("09-01 19:15", 25, "Frozen pizza after holiday"), ("09-05 18:45", 55, "Duck breast + roasted veg with Paul"),
    ("09-10 19:00", 30, "Baked salmon"), ("09-18 17:50", 65, "Lasagne for board game night"),
    ("09-22 21:00", 25, "Late pizza after Paul lands"), ("09-23 19:30", 40, "Käsespätzle gratin (Paul)"),
    ("09-23 20:15", 35, "Apple crumble"), ("09-24 19:15", 25, "Reheating leftovers"),
    ("09-28 19:45", 35, "Chicken traybake"), ("10-06 19:00", 35, "Roasted vegetables"),
    ("10-10 19:00", 40, "Baked pierogi"), ("10-12 18:45", 45, "Roasted veg + halloumi"),
]
WASHER = [
    ("09-01 14:00", "hot", "Holiday laundry #1"), ("09-01 16:30", "normal", "Holiday laundry #2"),
    ("09-03 07:30", "normal", "Before Stockholm"), ("09-05 11:00", "normal", "After Stockholm"),
    ("09-11 07:15", "normal", "Before Berlin"), ("09-14 20:00", "normal", "Before Brussels"),
    ("09-18 08:30", "normal", "After Brussels"), ("09-20 18:30", "normal", "Smoky bonfire clothes"),
    ("09-22 17:00", "normal", "After Gdańsk"), ("09-24 19:00", "hot", "Bed sheets after Paul"),
    ("09-28 20:30", "normal", "Before Berlin week"), ("10-05 08:00", "normal", "After Berlin #1"),
    ("10-05 10:30", "normal", "After Berlin #2"), ("10-06 21:00", "normal", "Before Stockholm"),
    ("10-10 08:15", "normal", "After Stockholm"), ("10-12 15:00", "hot", "Bed sheets after Paul"),
]
DISHWASHER = [
    ("09-05 22:45", "Dinner with Paul"), ("09-07 21:30", "Weekend dishes"), ("09-10 21:30", "Salmon dinner"),
    ("09-14 22:00", "Emptying before trip"), ("09-18 23:45", "Board game night"), ("09-23 23:15", "Dinner guests"),
    ("09-27 21:30", "Week's dishes"), ("09-28 22:30", "Before Berlin week"), ("10-06 21:30", "Before Stockholm"),
    ("10-11 00:25", "Pierogi night #1"), ("10-11 12:00", "Pierogi night #2"), ("10-12 21:00", "Weekend with Paul"),
]
EXTRA_KETTLE = [("09-18 22:30", "Tea for guests"), ("09-18 22:40", "Tea for guests"), ("09-23 22:00", "Tea for guests"),
                ("10-10 18:40", "Boiling water for pierogi"), ("10-10 19:20", "Boiling water for pierogi"),
                ("10-10 20:00", "Boiling water for pierogi"), ("10-10 20:40", "Boiling water for pierogi")]
RESTOCK = ["09-01 18:00", "09-05 17:00", "09-18 16:00", "09-22 16:40", "10-05 17:00", "10-10 11:10"]  # fridge refills
SPORT_SHOWERS = ["09-02 21:25", "09-05 10:35", "10-05 21:25", "10-11 11:50"]
TRIP_EVE_CHARGING = ["09-03 07:40", "09-08 22:30", "09-11 08:00", "09-14 21:00", "09-18 23:00", "09-21 09:00",
                     "09-25 23:30", "09-28 21:00", "10-06 21:30"]  # power bank + spare devices before trips
HP_SERVICE_OFF = ("10-05 14:00", "10-05 15:10")
HP_SERVICE_TEST = ("10-05 15:10", "10-05 15:30")

# =====================================================================================
# Weather (Open-Meteo): Historical Weather API for history, forecast for the future
# =====================================================================================
weather, sun = {}, {}
for fname, src in (("openmeteo_historical.json", "open-meteo historical API"),
                   ("openmeteo_forecast.json", "open-meteo forecast")):
    d = json.load(open(ROOT / "data" / "weather" / fname))
    h = d["hourly"]
    for i, ts in enumerate(h["time"]):
        dt = datetime.fromisoformat(ts)
        if (src.startswith("open-meteo historical")) != (dt < HISTORY_END):
            continue
        weather[dt] = dict(src=src, temp=h["temperature_2m"][i], cloud=h["cloud_cover"][i],
                           rad=h["shortwave_radiation"][i], rh=h["relative_humidity_2m"][i],
                           wind=h["wind_speed_10m"][i])
    for i, day in enumerate(d["daily"]["time"]):
        dd = datetime.fromisoformat(day).date()
        if (src.startswith("open-meteo historical")) == (dd < HISTORY_END.date()):
            sun[dd] = (datetime.fromisoformat(d["daily"]["sunrise"][i]), datetime.fromisoformat(d["daily"]["sunset"][i]))

hours = sorted(weather)
assert hours[0] == START and hours[-1] == END - timedelta(hours=1) and len(hours) == N // 60, "weather gap"


def interp(key, i):
    h, frac = divmod(i, 60)
    a = weather[hours[h]][key]
    b = weather[hours[min(h + 1, len(hours) - 1)]][key]
    return a + (b - a) * frac / 60


T_OUT = [interp("temp", i) for i in range(N)]
RAD = [interp("rad", i) for i in range(N)]
CLOUD = [weather[hours[i // 60]]["cloud"] for i in range(N)]

# =====================================================================================
# Presence
# =====================================================================================
away = mask(AWAY)
a_home = [not x for x in away]
a_asleep = mask(SLEEP)
holiday = mask(HOLIDAY_MODE)
paul_in = mask(PAUL_STAY)
paul_out = mask(PAUL_OUT)
paul_home = [paul_in[i] and not paul_out[i] for i in range(N)]
guests = [0] * N
for a, b, n in GUESTS:
    for i in range(mi(a), min(N, mi(b))):
        guests[i] = n

for a, b in SLEEP:  # sanity: she can't sleep at home while away
    assert not any(away[i] for i in range(mi(a), min(N, mi(b)))), f"sleep/away overlap {a}"


def minute_of_day(i):
    return (START + timedelta(minutes=i)).hour * 60 + (START + timedelta(minutes=i)).minute


a_awake = [a_home[i] and not a_asleep[i] for i in range(N)]
# Paul sleeps when she sleeps; if he is alone he is awake 07:30-23:30.
paul_awake = [paul_home[i] and (a_awake[i] or (not a_home[i] and 450 <= minute_of_day(i) < 1410)) for i in range(N)]
awake_any = [a_awake[i] or paul_awake[i] or guests[i] > 0 for i in range(N)]
people = [int(a_home[i]) + int(paul_home[i]) + guests[i] for i in range(N)]

# =====================================================================================
# Appliance loads
# =====================================================================================
loads = {a: [0.0] * N for a in APPLIANCES}
events, warnings = [], []


def add(app, start, profile, reason, need_awake=True, warn=True):
    s = mi(start) if not isinstance(start, int) else start
    kwh, used = 0.0, 0
    for k, p in enumerate(profile):
        i = s + k
        if i >= N:
            break
        if need_awake and not awake_any[i]:
            if warn:
                warnings.append(f"{app} '{reason}' at {START + timedelta(minutes=i)} while nobody awake at home")
            break
        loads[app][i] += p
        kwh += p / 60
        used += 1
    if used:
        events.append(dict(appliance=app, start=START + timedelta(minutes=s), end=START + timedelta(minutes=s + used),
                           peak_kw=round(max(profile[:used]), 3), kwh=round(kwh, 4), reason=reason))


def kettle():
    return [2.0] * rng.randint(3, 5)


def coffee():
    return [round(rng.uniform(1.0, 1.5), 2)] * rng.randint(5, 10)


def oven(duration):
    p = round(rng.uniform(2.0, 2.5), 2)
    return [p if k < 12 or (k - 12) % 6 < 3 else 0.0 for k in range(duration)]  # preheat, then thermostat cycling


def washer(kind):
    target = rng.uniform(0.9, 1.0) if kind == "hot" else rng.uniform(0.6, 0.85)
    heat = round((target - 0.247) * 60 / 2.0)
    return [0.03] * 3 + [2.0] * heat + [0.15] * 55 + [0.10] * 20 + [0.45] * 10


def dishwasher():
    target = rng.uniform(0.8, 1.2)
    heat = round((target - 0.055) * 30)
    h1 = round(heat * 0.55)
    return [0.02] * 4 + [2.0] * h1 + [0.08] * 35 + [0.05] * 3 + [2.0] * (heat - h1) + [0.01] * 25


def laptop(duration):
    p, prof = rng.uniform(0.045, 0.07), []
    for _ in range(duration):
        p = min(0.08, max(0.04, p + rng.uniform(-0.004, 0.004)))
        prof.append(round(p, 4))
    return prof


def charger(kwh, watts=10):
    return [watts / 1000] * max(1, round(kwh / (watts / 1000) * 60))


dhw_draw = [0.0] * N          # kWh (thermal) of hot water drawn per minute
fridge_boost_until = []       # minute indices of fridge restocks


def jitter(dt, lo, hi):
    return dt + timedelta(minutes=rng.randint(lo, hi))


# --- morning routine ---
for _, wake in SLEEP:
    w = t(wake)
    if w >= END:
        continue
    add("kettle", jitter(w, 5, 12), kettle(), "Morning tea / hot water")
    add("coffee_machine", jitter(w, 10, 20), coffee(), "Morning coffee")
    dhw_draw[mi(jitter(w, 15, 30))] += rng.uniform(1.4, 1.8)
    if paul_home[mi(w)]:
        add("coffee_machine", jitter(w, 25, 40), coffee(), "Coffee for Paul")
        dhw_draw[mi(jitter(w, 40, 55))] += rng.uniform(1.6, 2.0)
    if w.hour >= 7 and w.minute >= 30 or w.hour >= 8:
        add("coffee_machine", jitter(w, 80, 110), coffee(), "Second weekend coffee", warn=False)

for s in SPORT_SHOWERS:
    dhw_draw[mi(s)] += rng.uniform(1.2, 1.6)

# --- work from home ---
for a, b in WFH:
    s, e = mi(a), mi(b)
    lunch = mi(t(a).strftime("%m-%d") + " 12:30") + rng.randint(-15, 20)
    if s < lunch < e - 60:
        add("laptop", s, laptop(lunch - s), "Work from home")
        back = lunch + rng.randint(30, 45)
        add("laptop", back, laptop(e - back), "Work from home")
        add("kettle", lunch + 5, kettle(), "Lunch break")
        add("coffee_machine", back - 8, coffee(), "Post-lunch coffee")
        if e - back > 150:
            add("kettle", back + rng.randint(90, 150), kettle(), "Afternoon tea")
    else:
        add("laptop", s, laptop(e - s), "Work from home")
for a, b in PAUL_LAPTOP:
    add("laptop", a, laptop(mi(b) - mi(a)), "Paul working remotely")

# --- scheduled cooking / washing ---
for s, dur, why in OVEN:
    add("oven", s, oven(dur), why)
for s, kind, why in WASHER:
    assert awake_any[mi(s)], f"washer start while nobody home: {s}"
    add("washing_machine", s, washer(kind), why, need_awake=False)
for s, why in DISHWASHER:
    assert awake_any[mi(s)], f"dishwasher start while nobody home: {s}"
    add("dishwasher", s, dishwasher(), why, need_awake=False)
for s, why in EXTRA_KETTLE:
    add("kettle", s, kettle(), why)
for s, dur, why in TV:
    add("tv", s, [round(rng.uniform(0.08, 0.15), 3)] * dur, why)
fridge_boost_until = [mi(s) for s in RESTOCK]

# --- random evening habits ---
tv_days = {s[:5] for s, _, _ in TV}
day = START
while day < END:
    md = day.strftime("%m-%d")
    probe = mi(f"{md} 20:30")
    if a_awake[probe] and guests[probe] == 0:
        if rng.random() < 0.6:
            add("kettle", probe + rng.randint(-30, 75), kettle(), "Evening tea", warn=False)
        if md not in tv_days and rng.random() < 0.55:
            add("tv", probe + rng.randint(-30, 45), [round(rng.uniform(0.08, 0.15), 3)] * rng.randint(45, 150),
                "Evening TV / streaming", warn=False)
        if rng.random() < 0.35:
            add("laptop", mi(f"{md} 21:00") + rng.randint(0, 60), laptop(rng.randint(20, 70)),
                "Personal laptop (e-mails, booking trips)", warn=False)
    day += timedelta(days=1)

# --- charging (overnight) ---
for bed, _ in SLEEP:
    b = mi(bed) - 10
    if b >= N:
        continue
    add("phone_tablet_charging", b, charger(rng.uniform(0.012, 0.018)), "Phone overnight", need_awake=False)
    if rng.random() < 0.5:
        add("phone_tablet_charging", b + 2, charger(rng.uniform(0.012, 0.02), 12), "Tablet overnight", need_awake=False)
    if paul_home[b]:
        add("phone_tablet_charging", b + 5, charger(rng.uniform(0.012, 0.018)), "Paul's phone", need_awake=False)
for s in TRIP_EVE_CHARGING:
    add("phone_tablet_charging", s, charger(0.035, 15), "Power bank before trip", need_awake=False)

# --- continuous loads: router, standby, lighting ---
for i in range(N):
    h = i // 60
    loads["wifi_router"][i] = 0.011 + 0.002 * ((h * 7919) % 5 - 2) / 2
    if a_home[i] or paul_home[i]:
        loads["standby"][i] = 0.03 if not awake_any[i] else 0.038
    else:
        loads["standby"][i] = 0.02 if holiday[i] else 0.034   # forgot the power strip -> standby keeps running

    now = START + timedelta(minutes=i)
    sunrise, sunset = sun[now.date()]
    margin = 15 if CLOUD[i] > 75 else 0
    dark = now < sunrise + timedelta(minutes=15 + margin) or now > sunset - timedelta(minutes=25 + margin)
    if awake_any[i]:
        mod = minute_of_day(i)
        if dark:
            if guests[i]:
                level = 0.14
            elif mod >= 22 * 60 + 30:
                level = 0.06
            elif mod >= 17 * 60:
                level = 0.10 + 0.02 * paul_home[i]
            else:
                level = 0.07
        else:
            level = 0.03 if CLOUD[i] > 85 else 0.0
        loads["lighting"][i] = level * (0.9 + 0.2 * ((h * 104729) % 11) / 10)

# =====================================================================================
# Thermal model: fridge + heat pump (space heating & hot-water tank)
# =====================================================================================
UA = 60.0            # W/K  envelope + ventilation losses, 65 m² well-insulated apartment
C = 8.0e6            # J/K  effective thermal capacity
SOLAR_AREA = 1.4     # m²   effective solar aperture (windows x g-value)
DHW_LOSS = 0.05 / 60  # kWh_th per minute tank standing loss
DHW_TRIGGER = 2.0    # kWh_th deficit that starts a reheat
DHW_P = 1.6          # kW electrical while heating water
DHW_COP = 2.5
FRIDGE_P = 0.095     # kW compressor
CYCLE = 36           # min fridge cycle


def setpoint(i):
    if holiday[i]:
        return 16.0
    mod = minute_of_day(i)
    return 21.0 if 6 * 60 <= mod < 22 * 60 + 30 else 18.0


def cop(tout):
    return min(4.5, max(2.2, 2.6 + 0.09 * tout))


svc_off = mask([HP_SERVICE_OFF])
svc_test = mask([HP_SERVICE_TEST])
T_IN, SP = [0.0] * N, [0.0] * N
tin, hp_on, hp_since, dhw_on, deficit = 24.0, False, -999, False, 1.0
fridge_on_left = 0
hp_run = None  # (mode, start)

for i in range(N):
    now = START + timedelta(minutes=i)
    # fridge compressor
    if i % CYCLE == 0:
        duty = 0.40 + 0.015 * (tin - 20) + 0.05 * a_awake[i] + 0.08 * (guests[i] > 0)
        duty += 0.15 if any(0 <= i - r < 240 for r in fridge_boost_until) else 0.0
        duty = min(0.75, max(0.3, duty + rng.uniform(-0.04, 0.04)))
        fridge_on_left = round(duty * CYCLE)
    if fridge_on_left > 0:
        loads["fridge"][i] = FRIDGE_P
        fridge_on_left -= 1

    # hot-water tank
    deficit += DHW_LOSS + dhw_draw[i] + (0.05 / 60 if awake_any[i] else 0) + (0.3 / 60 if guests[i] else 0)
    if now.weekday() == 6 and now.hour == 2 and now.minute == 0 and not holiday[i]:
        deficit += 1.2   # weekly anti-legionella cycle (tank to 60 °C)
    sp = setpoint(i)
    tout = T_OUT[i]
    mode, p_el, q_space = None, 0.0, 0.0
    if svc_off[i]:
        dhw_on = hp_on = False
    elif svc_test[i]:
        mode, p_el = "space", 2.4
        q_space = p_el * cop(tout)
    elif not holiday[i] and (dhw_on or deficit > DHW_TRIGGER):
        dhw_on = True
        mode, p_el = "dhw", DHW_P
        deficit -= DHW_P * DHW_COP / 60
        if deficit <= 0:
            deficit, dhw_on = 0.0, False
    else:
        if hp_on and tin >= sp + 0.3 and i - hp_since >= 15:
            hp_on, hp_since = False, i
        elif not hp_on and tin < sp - 0.3 and i - hp_since >= 10:
            hp_on, hp_since = True, i
        if hp_on:
            mode = "space"
            p_el = min(3.0, max(1.0, 1.0 + 0.8 * (sp - tin + 0.3)))
            q_space = p_el * cop(tout)

    if mode == "space":
        loads["heat_pump_space_heating"][i] = p_el
    elif mode == "dhw":
        loads["heat_pump_hot_water"][i] = p_el

    # log heat pump runs as events
    if hp_run and hp_run[0] != mode:
        s0 = hp_run[1]
        col = "heat_pump_space_heating" if hp_run[0] == "space" else "heat_pump_hot_water"
        kwh = sum(loads[col][s0:i]) / 60
        why = {"space": "Space heating (thermostat)", "dhw": "Hot-water tank reheat"}[hp_run[0]]
        if svc_test[s0]:
            why = "Test run after annual service"
        events.append(dict(appliance=col, start=START + timedelta(minutes=s0), end=now,
                           peak_kw=round(max(loads[col][s0:i]), 3), kwh=round(kwh, 4), reason=why))
        hp_run = None
    if mode and not hp_run:
        hp_run = (mode, i)

    gains_w = 900 * sum(loads[a][i] for a in APPLIANCES if not a.startswith("heat_pump"))
    gains_w += 80 * sum([a_awake[i], paul_awake[i]]) + 60 * sum([a_home[i] and a_asleep[i], paul_home[i] and not paul_awake[i]])
    gains_w += 90 * guests[i] + 40   # 40 W: tank losses inside the apartment
    gains_w += SOLAR_AREA * RAD[i]
    # window airing: she opens windows when it is warm inside (tilted bedroom window at night)
    ua = UA
    if tout < tin:
        if awake_any[i] and tin > 24.0:
            ua += 120
        elif (a_home[i] or paul_home[i]) and tin > 23.5:
            ua += 50
    tin += (ua * (tout - tin) + q_space * 1000 + gains_w) * 60 / C
    T_IN[i], SP[i] = tin, sp

# =====================================================================================
# Output
# =====================================================================================
out = ROOT / "data" / "consumption"
out.mkdir(parents=True, exist_ok=True)


def occ_state(i):
    if guests[i]:
        return "home+guests"
    if a_home[i] and paul_home[i]:
        return "home+Paul"
    if a_home[i]:
        return "home"
    if paul_home[i]:
        return "Paul only"
    return "away"


with open(out / "hourly_consumption.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "period", "weather_source", "temp_out_c", "cloud_cover_pct", "shortwave_radiation_wm2",
                "indoor_temp_c", "heating_setpoint_c", "occupancy", "aleksandra_home_share", "paul_home_share",
                "guests", "heat_pump_holiday_mode"] + [f"{a}_kwh" for a in APPLIANCES] + ["total_kwh"])
    for h, dt in enumerate(hours):
        r = range(h * 60, h * 60 + 60)
        wx = weather[dt]
        per_app = [sum(loads[a][i] for i in r) / 60 for a in APPLIANCES]
        w.writerow([dt.strftime("%Y-%m-%dT%H:%M:00+02:00"), "history" if dt < HISTORY_END else "future", wx["src"],
                    wx["temp"], wx["cloud"], wx["rad"], round(sum(T_IN[i] for i in r) / 60, 2),
                    round(sum(SP[i] for i in r) / 60, 1), Counter(occ_state(i) for i in r).most_common(1)[0][0],
                    round(sum(a_home[i] for i in r) / 60, 2), round(sum(paul_home[i] for i in r) / 60, 2),
                    max(guests[i] for i in r), int(any(holiday[i] for i in r))]
                   + [round(x, 4) for x in per_app] + [round(sum(per_app), 4)])

with open(out / "appliance_events.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["appliance", "start", "end", "duration_min", "peak_kw", "kwh", "reason"])
    w.writeheader()
    for e in sorted(events, key=lambda e: (e["start"], e["appliance"])):
        w.writerow(dict(e, start=e["start"].strftime("%Y-%m-%d %H:%M"), end=e["end"].strftime("%Y-%m-%d %H:%M"),
                        duration_min=int((e["end"] - e["start"]).total_seconds() // 60)))

for x in warnings:
    print("WARN", x)
print(f"{len(events)} events, {N // 60} hours written to {out}")
