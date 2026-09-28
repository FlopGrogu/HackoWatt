"""Block 1 – heat pump: space heating (physical 1-zone model) + hot-water tank. Default parameters from
docs/ASSUMPTIONS.md (no fitting). Two switches turn the real forecast into the ideal one:
  away_mode : 16 °C and no tank reheating while surely away (back to normal 2 h before the return)
  shifting  : tank reheated at night (03–06 h), pre-heat to 22 °C 15–17 h and allow 20 °C during 17–22 h
"""
from datetime import timedelta

from ..data import thermostat_reading, weather_forecast

UA, C = 60.0, 8.0e6              # W/K, J/K
SOLAR_AREA, TANK_GAIN_W = 1.4, 40.0
P_MAX = 3.0                      # kW electrical
DHW_P, DHW_COP, DHW_TRIGGER, DHW_LOSS = 1.6, 2.5, 2.0, 0.05
STEPS = 6                        # 10-minute sub-steps per hour
AWAY = 85


def cop(tout):
    return min(4.5, max(2.2, 2.6 + 0.09 * tout))


def _near_return(ts, absences):
    return any(timedelta(0) <= a["return"] - ts <= timedelta(hours=2) for a in absences)


def setpoint(ts, r, absences, away_mode, shifting):
    h = ts.hour
    sp = 21.0 if 6 <= h <= 21 else 19.5 if h == 22 else 18.0
    away = r["away_score"] >= AWAY
    if away_mode and away and not _near_return(ts, absences):
        return 16.0
    if shifting and not away:
        if h in (15, 16):
            sp = 22.0
        elif 17 <= h <= 21:
            sp = 20.0
    return sp


def shower_hours(ish):
    """Hour of her morning shower per day: 07 weekdays / 08 weekends, or the last home hour before an
    early departure."""
    by_day = {}
    for r in ish:
        by_day.setdefault(r["timestamp"].date(), {})[r["timestamp"].hour] = r
    out = set()
    for day, rows in by_day.items():
        usual = 8 if day.weekday() >= 5 else 7
        if usual in rows and rows[usual]["away_score"] < AWAY:
            out.add(rows[usual]["timestamp"])
            continue
        home_early = [h for h in range(4, usual) if h in rows and rows[h]["away_score"] < 50]
        if home_early:
            out.add(rows[max(home_early)]["timestamp"])
    return out


def heat_pump(start, ish, absences, gains_kwh, away_mode=False, shifting=False):
    """Hourly space-heating kWh, hot-water kWh and indoor temperature."""
    wx = weather_forecast()
    tin = thermostat_reading(start)
    deficit = 1.0                          # tank heat missing at start (kWh), unknown -> assumed half full
    showers = shower_hours(ish)
    out = []
    for i, r in enumerate(ish):
        ts = r["timestamp"]
        tout, rad = wx[ts]["temp"], wx[ts]["rad"]
        p_home = 1 - r["away_score"] / 100
        away = r["away_score"] >= AWAY
        sp = setpoint(ts, r, absences, away_mode, shifting)
        awake = 7 <= ts.hour <= 22
        gains = 900 * gains_kwh[i] + (80 if awake else 60) * r["people"] + SOLAR_AREA * rad + TANK_GAIN_W

        # --- hot-water tank ---
        draw = DHW_LOSS
        if ts in showers:
            draw += 1.6 * p_home + (1.8 if r["people"] >= 1.8 else 0.0)
        if awake:
            draw += 0.05 * p_home + (0.3 if r["people"] >= 3 else 0.0)
        paused = away_mode and away and not _near_return(ts, absences)
        if ts.weekday() == 6 and ts.hour == 2 and not paused:
            draw += 1.2                     # weekly anti-legionella cycle
        deficit += draw
        if paused:
            allowed = False
        elif shifting and not away:
            allowed = 3 <= ts.hour <= 5 or deficit >= 5.0
        else:
            allowed = deficit >= DHW_TRIGGER
        dhw_th = min(deficit, DHW_P * DHW_COP) if allowed else 0.0
        deficit -= dhw_th
        dhw_el = dhw_th / DHW_COP
        dhw_share = dhw_el / DHW_P          # part of the hour the heat pump is busy with water

        # --- space heating (10-minute steps) ---
        dt = 3600 / STEPS
        q_max = P_MAX * cop(tout) * 1000 * (1 - dhw_share)
        el = 0.0
        t_sum = 0.0
        for _ in range(STEPS):
            ua = UA + (120 if tin > 24 and p_home > 0.5 and tout < tin else 0)
            free = ua * (tout - tin) + gains
            need = (sp - tin) * C / dt - free
            q = min(max(need, 0.0), q_max)
            tin += (free + q) * dt / C
            el += q / cop(tout) * dt / 3.6e6
            t_sum += tin
        out.append(dict(space=el, dhw=dhw_el, t_in=t_sum / STEPS, setpoint=sp))
    return out
