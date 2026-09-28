"""Blocks 4a/4b – washing machine and dishwasher.

Per day: chance of a run from triggers (read from the isHome output + the appliance's own last run),
then spread over her usual start hours while she is home. Each predicted run also gets the cheapest
allowed start in the next 24 h (ideal version / tips).
"""
from collections import Counter, defaultdict
from datetime import timedelta

from ..data import history, home_hours_observed, price

HOME_MAX_SCORE = 50           # away score below this = counted as home
SHAPE = {"washing_machine": [0.7, 0.3], "dishwasher": [0.6, 0.4]}   # share of a run's kWh per hour
ENERGY = {"washing_machine": 0.8, "dishwasher": 1.0}
HOT_WASH = 1.0


def _runs_in_history(app, start):
    """Start times of past runs (consecutive metered hours with > 0.05 kWh)."""
    runs, prev = [], None
    for ts in sorted(t for t in history() if t < start):
        on = history()[ts][app] > 0.05
        if on and not prev:
            runs.append(ts)
        prev = on
    return runs


def _home(r):
    return r["away_score"] < HOME_MAX_SCORE


def _combine(ps):
    q = 1.0
    for p in ps:
        q *= 1 - p
    return 1 - q


def predict_runs(start, ish, absences):
    """List of predicted runs: appliance, day, p, hours (candidate start hours with weights), kwh, reason."""
    by_day = defaultdict(list)
    for r in ish:
        by_day[r["timestamp"].date()].append(r)
    days = sorted(by_day)
    runs = []

    for app in ("washing_machine", "dishwasher"):
        past = _runs_in_history(app, start)
        usual = Counter(ts.hour for ts in past)
        last_day = past[-1].date() if past else start.date() - timedelta(days=7)
        # dinners at home since the last dishwasher run (history: phone at home at 19:00)
        home_obs = home_hours_observed()
        dinners = sum(1 for d in range((start.date() - last_day).days)
                      if home_obs.get((start - timedelta(days=d + 1)).replace(hour=19)))

        for day in days:
            rows = {r["timestamp"].hour: r for r in by_day[day]}
            triggers = []   # (p, allowed start hours, reason, kwh)

            def window(h0, h1):
                return [h for h in range(h0, h1) if h in rows and _home(rows[h])]

            if app == "washing_machine":
                for a in absences:
                    if a["nights"] < 1:
                        continue
                    if a["departure"].date() == day and a["departure"].hour >= 12:
                        triggers.append((0.7, window(7, a["departure"].hour - 1), "morning before a trip", ENERGY[app]))
                    if a["departure"].date() - timedelta(days=1) == day:
                        triggers.append((0.7, window(18, 23), "evening before a trip", ENERGY[app]))
                    back = a["return"]
                    after_day = back.date() if back.hour < 17 else back.date() + timedelta(days=1)
                    if after_day == day:
                        h0 = back.hour + 1 if back.date() == day else 7
                        kwh = ENERGY[app] * (2 if a["nights"] >= 4 else 1)
                        triggers.append((0.8, window(h0, 22), f"after a {a['nights']}-night trip", kwh))
                hours = sorted(rows)
                for h0, h1 in zip(hours, hours[1:]):
                    if rows[h0]["people"] >= 1.5 and rows[h1]["people"] <= 1.2 and _home(rows[h1]):
                        triggers.append((0.7, window(max(h1, 18), 22), "bed sheets after Paul's visit", HOT_WASH))
                        break
                gap = (day - last_day).days
                if gap >= 5:
                    triggers.append((min(0.6, 0.15 + 0.1 * (gap - 5)), window(7, 22), f"{gap} days since last wash",
                                     ENERGY[app]))
            else:
                if any(rows[h]["people"] >= 3 for h in range(18, 24) if h in rows):
                    triggers.append((0.95, window(23, 24) or window(21, 24), "after guests", ENERGY[app]))
                for a in absences:
                    if a["nights"] >= 1 and a["departure"].date() - timedelta(days=1) == day:
                        triggers.append((0.6, window(21, 23), "emptying before a trip", ENERGY[app]))
                if 19 in rows and _home(rows[19]):
                    dinners += 2 if rows[19]["people"] >= 1.8 else 1
                if dinners >= 3:
                    triggers.append((0.7, window(21, 23), f"{dinners} dinners at home since last run", ENERGY[app]))

            triggers = [t for t in triggers if t[1]]
            if not triggers:
                continue
            p = _combine(t[0] for t in triggers)
            main = max(triggers, key=lambda t: t[0])
            weights = {h: usual.get(h, 0) + 1 for h in main[1]}
            total = sum(weights.values())
            kwh = max(t[3] for t in triggers)
            runs.append(dict(appliance=app, day=day, p=p, kwh=kwh, reason=" + ".join(t[2] for t in triggers),
                             hours={h: w / total for h, w in weights.items()}))
            if p >= 0.5:
                last_day, dinners = day, 0
    return runs


def ideal_start(run, usual_start, ish_by_ts, absences):
    """Cheapest allowed start within 24 h after the usual start (delay-start). Washer must finish while
    she is home (and still home the hour after, to hang it up), and not within 12 h before a trip (>= 1 night).
    Keeps the usual start when nothing is cheaper."""
    best, best_cost = usual_start, None
    shape = SHAPE[run["appliance"]]
    for k in range(24):
        s = usual_start + timedelta(hours=k)
        end = s + timedelta(hours=len(shape))
        if run["appliance"] == "washing_machine":
            after = [ish_by_ts.get(end + timedelta(hours=j)) for j in range(2)]
            if any(r is None or not _home(r) for r in after):
                continue
            if any(a["nights"] >= 1 and timedelta(0) <= a["departure"] - end <= timedelta(hours=12) for a in absences):
                continue
        elif s not in ish_by_ts:
            continue
        cost = sum(share * price(s + timedelta(hours=j)) for j, share in enumerate(shape))
        # washer: among equally cheap slots take the latest (finishes just before she needs the clothes)
        later_tie = run["appliance"] == "washing_machine" and best_cost is not None and abs(cost - best_cost) < 1e-9
        if best_cost is None or cost < best_cost - 1e-9 or later_tie:
            best, best_cost = s, cost
    usual_cost = sum(share * price(usual_start + timedelta(hours=j)) for j, share in enumerate(shape))
    return best if best_cost is not None and best_cost < usual_cost - 1e-9 else usual_start


def run_cost_per_kwh(appliance, s):
    return sum(share * price(s + timedelta(hours=j)) for j, share in enumerate(SHAPE[appliance]))


def appliances(start, ish, absences):
    """Hourly real/ideal/low/high kWh for washer + dishwasher, and the predicted runs (for tips)."""
    idx = {r["timestamp"]: i for i, r in enumerate(ish)}
    ish_by_ts = {r["timestamp"]: r for r in ish}
    real = [0.0] * len(ish)
    ideal = [0.0] * len(ish)
    low = [0.0] * len(ish)
    high = [0.0] * len(ish)
    runs = predict_runs(start, ish, absences)

    def put(arr, s, kwh, factor):
        for j, share in enumerate(SHAPE[run["appliance"]]):
            i = idx.get(s + timedelta(hours=j))
            if i is not None:
                arr[i] += kwh * share * factor

    for run in runs:
        usual_h = max(run["hours"], key=run["hours"].get)
        base = next(r["timestamp"] for r in ish if r["timestamp"].date() == run["day"]).replace(hour=0)
        run["usual_start"] = base + timedelta(hours=usual_h)
        run["ideal_start"] = ideal_start(run, run["usual_start"], ish_by_ts, absences)
        run["saving_eur"] = run["kwh"] * (run_cost_per_kwh(run["appliance"], run["usual_start"])
                                          - run_cost_per_kwh(run["appliance"], run["ideal_start"]))
        for h, w in run["hours"].items():
            put(real, base + timedelta(hours=h), run["kwh"], run["p"] * w)
            put(high, base + timedelta(hours=h), run["kwh"], w if run["p"] >= 0.1 else run["p"] * w)
            if run["p"] >= 0.9:
                put(low, base + timedelta(hours=h), run["kwh"], run["p"] * w)
        put(ideal, run["ideal_start"], run["kwh"], run["p"])
    out = [dict(real=real[i], ideal=ideal[i], low=low[i], high=high[i]) for i in range(len(ish))]
    return out, runs
