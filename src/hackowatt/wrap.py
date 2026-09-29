"""Year wrap-around and the 30-day window for everything the forecast reads.

The generated data covers one year (2026). A date in any year maps to the same month/day/time in 2026 (`canonical`);
December is glued in front of January (and January behind December), so 30 days before 10 Jan are 11 Dec – 10 Jan.
`set_window(now)` limits history, positions … to the 30 days before `now`: the forecast never sees older data.
"""
from datetime import datetime, timedelta

YEAR = 2026
WINDOW_DAYS = 30
LO = HI = None


def shift_year(ts, years):
    try:
        return ts.replace(year=ts.year + years)
    except ValueError:                       # 29 Feb
        return (ts - timedelta(days=1)).replace(year=ts.year + years)


def canonical(ts):
    return shift_year(ts, YEAR - ts.year)


def extend(items, back_days=0, forward_days=0):
    """Copy the last `back_days` of the year in front of it (as YEAR-1) and the first `forward_days` behind it (as YEAR+1)."""
    keys = sorted(items)
    first, last = keys[0], keys[-1]
    out = dict(items)
    for ts, v in items.items():
        if back_days and ts > last - timedelta(days=back_days):
            out[shift_year(ts, -1)] = v
        if forward_days and ts < first + timedelta(days=forward_days):
            out[shift_year(ts, 1)] = v
    return out


def set_window(now, days=WINDOW_DAYS):
    global LO, HI
    LO, HI = (now - timedelta(days=days), now) if now else (None, None)


_cache = {}


def windowed(items):
    """dict {ts: value} restricted to [LO, HI) (cached per window); the whole dict when no window is set."""
    if HI is None:
        return items
    key = (id(items), LO, HI)
    if key not in _cache:
        if len(_cache) > 8:
            _cache.clear()
        _cache[key] = {ts: v for ts, v in items.items() if LO <= ts < HI}
    return _cache[key]
