"""Consumption stage: minute-by-minute appliance simulation for the whole year, aggregated to hourly kWh.

Inputs : itinerary (where she is, from the calendar), the calendar entries themselves (laundry, groceries, service visits ...),
         observed weather (Open-Meteo) and the appliance parameters of HackoWatt Scenario 1 (page 3).
Outputs: data/consumption/hourly_consumption.csv        observable data (weather + kWh per appliance)
         data/consumption/simulation_ground_truth.csv   not observable (occupancy, indoor temperature ...)
         data/consumption/appliance_events.csv          every appliance run with the reason behind it
All human timing and durations are normally distributed around habits (see docs/ASSUMPTIONS.md).
"""
import csv
import math
from collections import Counter
from datetime import date, datetime, timedelta

import numpy as np

from .config import clipped_gauss

APPLIANCES = ["fridge", "heat_pump_space_heating", "heat_pump_hot_water", "kettle", "coffee_machine", "oven",
              "washing_machine", "dishwasher", "tv", "laptop", "wifi_router", "lighting",
              "phone_tablet_charging", "standby"]

# ---- building & heat pump (see docs/ASSUMPTIONS.md) ----
UA = 60.0             # W/K   envelope + ventilation losses, 65 m² well-insulated apartment
C = 8.0e6             # J/K   effective thermal capacity
SOLAR_AREA = 1.4      # m²    effective solar aperture (windows x g-value); halved when blinds are down
DHW_LOSS = 0.05 / 60  # kWh_th per minute tank standing loss
DHW_TRIGGER = 2.0     # kWh_th deficit that starts a reheat
DHW_P, DHW_COP = 1.6, 2.5
FRIDGE_P, CYCLE = 0.095, 36
FORGET_SWITCH_OFF = 0.7   # share of trips on which she does NOT set holiday mode / switch off the power strip (30 % remember)


def cop(tout):
    return min(4.5, max(2.2, 2.6 + 0.09 * tout))


class Simulation:
    def __init__(self, cfg, weather, itin, events):
        self.cfg, self.w, self.itin, self.events = cfg, weather, itin, events
        self.rng = cfg.rng("consumption")
        self.N = itin.N
        self.start = cfg.start
        self.loads = {a: np.zeros(self.N) for a in APPLIANCES}
        self.log, self.warnings = [], []
        self.dhw_draw = np.zeros(self.N)
        self.restocks = []

    # ------------------------------------------------------------------ small helpers
    def mi(self, t):
        return int((t - self.start).total_seconds() // 60)

    def at(self, d, hhmm):
        if isinstance(hhmm, str):
            h, m = map(int, hhmm.split(":"))
            hhmm = h * 60 + m
        return self.mi(datetime.combine(d, datetime.min.time())) + int(hhmm)

    def g(self, mu, sigma, lo, hi):
        return int(round(clipped_gauss(self.rng, mu, sigma, lo, hi)))

    def when(self, m):
        return self.start + timedelta(minutes=int(m))

    def add(self, app, start, profile, reason, need_awake=True, warn=True):
        s = int(start)
        if s < 0 or s >= self.N or not len(profile):
            return 0
        L = min(len(profile), self.N - s)
        if need_awake:
            ok = self.awake_any[s:s + L]
            if not ok[0]:
                if warn:
                    self.warnings.append(f"{app} '{reason}' at {self.when(s)}: nobody awake at home")
                return 0
            if not ok.all() and app in ("oven", "tv", "laptop"):
                L = int(np.argmin(ok))                     # these stop when nobody is left; short runs (kettle, coffee) finish
        prof = np.asarray(profile[:L], dtype=float)
        self.loads[app][s:s + L] += prof
        self.log.append(dict(appliance=app, start=self.when(s), end=self.when(s + L), peak_kw=round(float(prof.max()), 3),
                             kwh=round(float(prof.sum() / 60), 4), reason=reason))
        return L

    def first_awake(self, m, within):
        """First minute >= m in which someone is awake at home, within `within` minutes (else None)."""
        seg = self.awake_any[m:m + within]
        return m + int(np.argmax(seg)) if len(seg) and seg.any() else None

    def awake_run(self, m, span=720):
        """(start, end) of the contiguous stretch around minute m in which she is awake at home."""
        lo, hi = max(0, m - span), min(self.N, m + span)
        seg = self.a_awake[lo:hi]
        k = m - lo
        if not seg[k]:
            return None
        a = k
        while a > 0 and seg[a - 1]:
            a -= 1
        b = k
        while b < len(seg) - 1 and seg[b + 1]:
            b += 1
        return lo + a, lo + b + 1

    # ------------------------------------------------------------------ appliance profiles
    def kettle(self):
        return [2.0] * self.g(4, 0.7, 3, 5)

    def coffee(self):
        return [round(self.rng.uniform(1.0, 1.5), 2)] * self.g(7, 1.3, 5, 10)

    def oven(self, duration):
        p = round(self.rng.uniform(2.0, 2.5), 2)
        return [p if k < 12 or (k - 12) % 6 < 3 else 0.0 for k in range(duration)]

    def washer(self, kind):
        target = self.rng.uniform(0.9, 1.0) if kind == "hot" else self.rng.uniform(0.6, 0.85)
        heat = round((target - 0.247) * 60 / 2.0)
        return [0.03] * 3 + [2.0] * heat + [0.15] * 55 + [0.10] * 20 + [0.45] * 10

    def dishwasher(self):
        target = self.rng.uniform(0.84, 1.16)
        heat = round((target - 0.055) * 30)
        h1 = round(heat * 0.55)
        return [0.02] * 4 + [2.0] * h1 + [0.08] * 35 + [0.05] * 3 + [2.0] * (heat - h1) + [0.01] * 25

    def laptop(self, duration):
        p, prof = self.rng.uniform(0.045, 0.07), []
        for _ in range(max(0, duration)):
            p = min(0.08, max(0.04, p + self.rng.uniform(-0.004, 0.004)))
            prof.append(round(p, 4))
        return prof

    def tv(self, duration):
        p = clipped_gauss(self.rng, 0.115, 0.017, 0.08, 0.15)
        return [min(0.15, max(0.08, round(p + self.rng.uniform(-0.004, 0.004), 3)))] * max(1, duration)

    def charger(self, kwh, watts=10):
        return [watts / 1000] * max(1, round(kwh / (watts / 1000) * 60))

    def shower_kwh(self, d, who=1.0):
        """Thermal energy of one shower: colder mains water in winter needs more heat."""
        mains = 10 + 5 * math.sin(2 * math.pi * (d.timetuple().tm_yday - 110) / 365)
        return self.rng.uniform(1.4, 1.8) * who * (45 - mains) / 35

    # ------------------------------------------------------------------ weather on the minute grid
    def _weather(self):
        w, N = self.w, self.N
        x = np.arange(N) / 60.0
        xp = np.arange(len(w.times))
        self.T_OUT = np.interp(x, xp, w.temp)
        self.RAD = np.interp(x, xp, w.rad)
        self.CLOUD = np.asarray(w.cloud)[np.minimum(np.arange(N) // 60, len(w.cloud) - 1)]
        days = (np.arange(N) // 1440)
        n_days = int(days[-1]) + 1
        sr, ss = np.zeros(n_days), np.zeros(n_days)
        for i in range(n_days):
            a, b = w.sun[(self.start + timedelta(days=i)).date()]
            sr[i], ss[i] = a.hour * 60 + a.minute, b.hour * 60 + b.minute
        mod = np.arange(N) % 1440
        margin = np.where(self.CLOUD > 75, 15, 0)
        self.dark = (mod < sr[days] + 15 + margin) | (mod > ss[days] - 25 - margin)
        self.mod = mod
        # heating season: on when the 3-day mean outdoor temperature drops below 13 °C, off again above 16 °C
        daily = self.T_OUT[: n_days * 1440].reshape(n_days, 1440).mean(1)
        on, season = False, np.zeros(n_days, dtype=bool)
        for i in range(n_days):
            m3 = daily[max(0, i - 2): i + 1].mean()
            if not on and m3 < 13:
                on = True
            elif on and m3 > 16:
                on = False
            season[i] = on
        self.heat_season = np.repeat(season, 1440)[:N]

    # ------------------------------------------------------------------ presence
    def _presence(self):
        it, N, rng = self.itin, self.N, self.rng
        self.away = it.away.copy()
        self.a_home = ~self.away
        self.trip_list = it.trips
        # trips on which she remembers holiday mode / power strip
        holiday = np.zeros(N, dtype=bool)
        self.remembered = []
        for t in it.trips:
            if t.nights >= 1 and rng.random() > FORGET_SWITCH_OFF:
                holiday[t.t0:t.t1] = True
                self.remembered.append(t)
        self.holiday = holiday
        # sleep: (bed, wake) per night she sleeps at home
        asleep = np.zeros(N, dtype=bool)
        self.sleeps = []
        d = self.cfg.start.date()
        last = self.cfg.end.date()
        while d < last:
            wd_night = d.weekday()
            wd_morning = (d + timedelta(1)).weekday()
            base = self.at(d, 0)
            bed = base + self.g(1420 if wd_night in (4, 5) else 1375, 40 if wd_night in (4, 5) else 25, 1330, 1500)
            wake = base + 1440 + (self.g(480, 45, 405, 585) if wd_morning >= 5 else self.g(405, 18, 375, 450))
            if bed >= N:
                break
            if self.away[bed]:
                rest = np.flatnonzero(~self.away[bed:min(N, bed + 300)])
                if not len(rest):
                    d += timedelta(1)
                    continue
                bed = bed + int(rest[0]) + self.g(35, 10, 15, 60)
            out = np.flatnonzero(self.away[bed:min(N, wake + 60)])
            if len(out):
                leave = bed + int(out[0])
                if leave < wake + 40:
                    wake = leave - self.g(72, 12, 50, 100)
                    if wake < bed + 120:
                        d += timedelta(1)      # back at 01:00 and out again at 05:00: no proper night
                        continue
            wake = min(wake, N - 1)
            asleep[bed:wake] = True
            self.sleeps.append((bed, wake))
            d += timedelta(1)
        self.asleep = asleep
        self.a_awake = self.a_home & ~asleep
        self.paul_home = it.paul_in & ~it.paul_out
        minute_of_day = self.mod
        self.paul_awake = self.paul_home & (self.a_awake | (self.away & (minute_of_day >= 450) & (minute_of_day < 1410)))
        self.guests = it.guests.astype(int)
        self.awake_any = self.a_awake | self.paul_awake | (self.guests > 0)
        # she is out of the flat or asleep-with-guests inconsistencies are impossible by construction; keep the invariant
        assert not (asleep & self.away).any()

    # ------------------------------------------------------------------ behaviour
    def _behaviour(self):
        rng, w, N = self.rng, self.w, self.N
        events = self.events
        by_day = {}
        for e in events:
            by_day.setdefault(e.first_day, []).append(e)
        days = []
        d = self.cfg.start.date()
        while d < self.cfg.end.date():
            days.append(d)
            d += timedelta(1)
        wake_of = {}
        for bed, wake in self.sleeps:
            wake_of[self.when(wake).date()] = (bed, wake)
        bed_of = {self.when(bed - 300).date(): (bed, wake) for bed, wake in self.sleeps}   # night that starts on the evening of that date
        wfh_days = {e.first_day for e in events if e.cat == "WFH" and e.all_day}
        office_days = {e.first_day for e in events if e.cat == "OFFICE" and e.all_day}
        winter = lambda d: 0.5 + 0.5 * math.cos(2 * math.pi * (d.timetuple().tm_yday - 15) / 365)    # 1 mid-Jan .. 0 mid-Jul
        day_factor = {d: math.exp(rng.gauss(0, 0.18)) for d in days}
        last_wash, dish = -10, 0.0

        # morning routine: kettle, coffee, shower, phone check
        for bed, wake in self.sleeps:
            if wake >= N:
                continue
            dd = self.when(wake).date()
            leave = np.flatnonzero(self.away[wake:wake + 240])
            rush = len(leave) and leave[0] < 45
            if not rush or rng.random() < 0.6:
                self.add("kettle", wake + self.g(8, 3, 3, 15), self.kettle(), "Morning tea / hot water")
            self.add("coffee_machine", wake + self.g(15, 4, 8, 25), self.coffee(), "Morning coffee")
            if not rush or rng.random() < 0.5:
                self.dhw_draw[min(N - 1, wake + self.g(22, 5, 12, 35))] += self.shower_kwh(dd)
            if self.paul_home[min(N - 1, wake)]:
                self.add("coffee_machine", wake + self.g(32, 6, 20, 50), self.coffee(), "Coffee for Paul")
                self.dhw_draw[min(N - 1, wake + self.g(48, 6, 35, 65))] += self.shower_kwh(dd, 1.2)
            if wake % 1440 > 450 and not rush:
                self.add("coffee_machine", wake + self.g(95, 15, 60, 130), self.coffee(), "Second weekend coffee", warn=False)

        for d in days:
            evs = by_day.get(d, [])
            mid = self.at(d, 0)
            f = day_factor[d]
            # ---------------- work from home
            if d in wfh_days:
                run = self.awake_run(self.at(d, 750))
                if run:
                    s = max(run[0] + 30, self.at(d, self.g(520, 20, 470, 600)))
                    e = min(run[1] - 5, self.at(d, self.g(1035, 35, 960, 1110)))
                    lunch = self.at(d, self.g(750, 18, 705, 800))
                    back = lunch + self.g(38, 8, 25, 60)
                    if e - s > 180 and s + 60 < lunch < e - 90:
                        self.add("laptop", s, self.laptop(lunch - s), "Work from home")
                        self.add("laptop", back, self.laptop(e - back), "Work from home")
                        self.add("kettle", lunch + 5, self.kettle(), "Lunch break")
                        if rng.random() < 0.6:
                            self.add("coffee_machine", back - 8, self.coffee(), "Post-lunch coffee")
                        if rng.random() < 0.5:
                            self.add("coffee_machine", s + self.g(130, 20, 90, 180), self.coffee(), "Mid-morning coffee", warn=False)
                        if e - back > 150:
                            self.add("kettle", back + self.g(120, 25, 80, 170), self.kettle(), "Afternoon tea", warn=False)
                        if rng.random() < 0.15:
                            self.add("laptop", e + 20, self.laptop(self.g(50, 15, 20, 90)), "Catching up after hours", warn=False)
                    elif e - s > 60:
                        self.add("laptop", s, self.laptop(e - s), "Work from home", warn=False)
            # Paul working remotely while she is out
            if self.paul_home[min(N - 1, self.at(d, 600))] and self.away[min(N - 1, self.at(d, 600))] and d.weekday() < 5:
                s = self.at(d, self.g(540, 20, 480, 600))
                self.add("laptop", s, self.laptop(self.g(300, 60, 120, 420)), "Paul working remotely")
            # ---------------- calendar-driven home events
            for e in evs:
                if e.all_day:
                    continue
                s = self.mi(e.start)
                if e.summary.startswith("Laundry + pack"):
                    self.wash(s, "normal", "Laundry before the trip")
                    last_wash = s
                elif e.summary.startswith("Grocery delivery"):
                    self.restocks.append(s)
                elif e.summary.startswith("Heat pump service"):
                    pass                                  # handled in the thermal model
                elif e.cat == "GUESTS-HOME":
                    kind = e.summary.lower()
                    n_g = int(self.guests[min(N - 1, s + 30)]) or 2
                    oven_p = 0.85 if ("dinner" in kind or "cooking" in kind or "birthday" in kind) else 0.5
                    if rng.random() < oven_p:
                        self.add("oven", s - self.g(55, 10, 30, 90), self.oven(self.g(45 + 4 * n_g, 12, 30, 90)), f"Cooking for guests ({e.summary})", warn=False)
                    for k in range(min(4, n_g)):
                        self.add("kettle", s + self.g(200 + 25 * k, 30, 120, 300), self.kettle(), "Tea for guests", warn=False)
                    if "movie" in kind:
                        self.add("tv", s + self.g(90, 20, 45, 150), self.tv(self.g(130, 20, 90, 180)), "Movie night", warn=False)
                    dish += 2.5
                elif "Dinner at home" in e.summary or "Cooking night" in e.summary:
                    if rng.random() < 0.8:
                        self.add("oven", s - self.g(40, 8, 20, 70), self.oven(self.g(50, 10, 30, 80)), e.summary, warn=False)
                    dish += 1.5
                elif e.cat in ("SPORT",) and e.location != self.pl_home:
                    ret = self.mi(e.end) + self.g(20, 5, 10, 40)
                    if ret < N and self.a_home[min(N - 1, ret)]:
                        self.dhw_draw[min(N - 1, ret + 15)] += self.shower_kwh(d, 0.8)
            # ---------------- evenings at home
            bed_info = bed_of.get(d)
            if bed_info:
                bed, _ = bed_info
                lo = self.at(d, 17 * 60)
                run = np.flatnonzero(self.a_awake[lo:bed])
                if len(run) > 40:
                    ev_start, ev_end = lo + int(run[0]), lo + int(run[-1])
                    # first minute of the contiguous evening at home (she may return late)
                    seg_start = ev_start
                    ev_len = ev_end - ev_start
                    guests_now = self.guests[ev_start:ev_end].max() > 0
                    paul_now = self.paul_home[ev_start:ev_end].any()
                    dinner_p = min(0.95, (0.20 + 0.10 * winter(d)) + (0.5 if paul_now else 0) + (0.25 if guests_now else 0))
                    home_by_dinner = ev_start <= self.at(d, 19 * 60 + 30)
                    if home_by_dinner and not guests_now and rng.random() < dinner_p:
                        s = max(ev_start + 20, self.at(d, self.g(1125, 35, 1050, 1220)))
                        self.add("oven", s, self.oven(self.g(38, 12, 20, 80)), "Cooking dinner", warn=False)
                        dish += 1.0
                    elif home_by_dinner:
                        dish += 0.6                        # something quick: still dirty dishes
                    if not guests_now:
                        if rng.random() < 0.55 + 0.15 * winter(d):
                            self.add("kettle", self.first_awake(ev_start + self.g(110, 50, 20, 240), 300) or ev_start + 60, self.kettle(), "Evening tea", warn=False)
                        tv_p = 0.50 + 0.15 * winter(d) + (0.08 if self.CLOUD[ev_start] > 80 else 0)
                        if ev_len > 90 and rng.random() < tv_p * (0.8 if d in wfh_days else 1.0):
                            s = max(ev_start + 30, self.at(d, self.g(1235, 45, 1140, 1350)))
                            self.add("tv", s, self.tv(int(self.g(115, 35, 30, 230) * f)), "Evening TV / streaming", warn=False)
                        if rng.random() < 0.35:
                            self.add("laptop", max(ev_start + 20, self.at(d, self.g(1290, 25, 1230, 1350))), self.laptop(int(self.g(45, 15, 20, 80) * f)),
                                     "Personal laptop (e-mails, booking trips)", warn=False)
                    # dishwasher: when enough dishes piled up, or before a trip
                    leaving_soon = self.away[min(N - 1, bed + 400):min(N, bed + 1300)].all() if bed + 400 < N else False
                    if dish >= 2.2 or (leaving_soon and dish >= 0.9):
                        s = max(ev_start + 20, min(ev_end - 100, self.at(d, self.g(1300, 30, 1230, 1370))))
                        if s > ev_start and self.add("dishwasher", s, self.dishwasher(), "Dishwasher", need_awake=False):
                            dish = 0.0
                if self.a_home[min(N - 1, self.at(d, 14 * 60))] and d.weekday() in (5, 6) and rng.random() < 0.07:
                    s = self.at(d, self.g(760, 30, 700, 850))
                    self.add("oven", s, self.oven(self.g(60, 15, 40, 100)), "Weekend roast", warn=False)
                    dish += 1.0
            # weekly / routine laundry
            if d.weekday() in (5, 6) and (self.at(d, 600) - last_wash) > 6 * 1440 and self.a_awake[min(N - 1, self.at(d, 660))]:
                s = self.at(d, self.g(690, 60, 570, 900))
                if self.wash(s, "normal", "Weekly laundry"):
                    last_wash = s
        # laundry around trips (before: if not in calendar, after: almost always)
        for t in self.trip_list:
            if t.nights < 1:
                continue
            arrive = t.t1
            if arrive < N - 400:
                base_day = self.when(arrive).date()
                if rng.random() < 0.8:
                    late = self.when(arrive).hour * 60 + self.when(arrive).minute > 20 * 60 + 30
                    s = self.at(base_day + timedelta(1), self.g(475, 30, 420, 600)) if late else arrive + self.g(70, 20, 30, 130)
                    if self.wash(s, "normal", f"Laundry after the trip ({t.place})"):
                        if t.nights >= 3 and rng.random() < 0.3:
                            self.wash(s + self.g(120, 15, 100, 160), "normal", "Second load after the trip")
        # the day before a trip (packing, booking, clearing the fridge) and the day of return (catching up) are busy at home
        for t in self.trip_list:
            if t.nights < 1:
                continue
            eve = self.when(t.t0).date() - timedelta(1)
            back = self.when(t.t1).date()
            for day, why in ((eve, "Trip preparation"), (back, "Catching up after the trip")):
                base = self.at(day, 0)
                lo = self.first_awake(base + (18 * 60 if day == back else 17 * 60), 300)
                if lo is None:
                    continue
                self.add("laptop", lo + self.g(15, 10, 0, 40), self.laptop(self.g(55, 20, 25, 110)), f"{why}: e-mails, bookings, packing list", warn=False)
                self.add("kettle", lo + self.g(60, 20, 20, 120), self.kettle(), f"{why}: tea", warn=False)
                if rng.random() < 0.5:
                    self.add("oven", lo + self.g(30, 15, 5, 70), self.oven(self.g(35, 10, 20, 60)), f"{why}: cooking / using up food", warn=False)
                if day == eve and rng.random() < 0.4:
                    self.wash(lo + self.g(20, 10, 0, 60), "normal", "Extra load before the trip")
                if day == back:
                    self.add("tv", lo + self.g(90, 25, 40, 150), self.tv(self.g(90, 30, 30, 160)), "Winding down after the trip", warn=False)
        # bed sheets after Paul's visits
        self._paul_sheets()
        # power bank / spare devices before trips
        for t in self.trip_list:
            if t.nights >= 1 and t.t0 > 60:
                s = t.t0 - self.g(600, 240, 120, 900)
                self.add("phone_tablet_charging", s if self.a_home[s] else t.t0 - 40, self.charger(0.02, 15), "Power bank before trip", need_awake=False)
        # nightly charging
        for bed, _ in self.sleeps:
            b = bed - 10
            self.add("phone_tablet_charging", b, self.charger(rng.uniform(0.012, 0.018)), "Phone overnight", need_awake=False)
            if rng.random() < 0.5:
                self.add("phone_tablet_charging", b + 2, self.charger(rng.uniform(0.012, 0.02), 12), "Tablet overnight", need_awake=False)
            if self.paul_home[min(N - 1, b)]:
                self.add("phone_tablet_charging", b + 5, self.charger(rng.uniform(0.012, 0.018)), "Paul's phone", need_awake=False)
        # lights left on when leaving in a hurry
        for m in np.flatnonzero(self.a_home[:-1] & self.away[1:]):
            if rng.random() < 0.04 and self.away[m + 1: m + 60].all():
                dur = int(clipped_gauss(rng, 240, 150, 30, 720))
                seg = slice(m + 1, min(N, m + 1 + dur))
                self.loads["lighting"][seg] += np.where(self.away[seg], 0.06, 0.0)
                self.log.append(dict(appliance="lighting", start=self.when(m + 1), end=self.when(seg.stop), peak_kw=0.06,
                                     kwh=round(0.06 * (seg.stop - seg.start) / 60, 4), reason="Lights left on when leaving"))

    def wash(self, s, kind, reason):
        """Start the washing machine at s (or the next minute someone is awake within 4 h)."""
        if s < 0 or s >= self.N:
            return 0
        s2 = self.first_awake(s, 240)
        if s2 is None:
            return 0
        return self.add("washing_machine", s2, self.washer(kind), reason, need_awake=False)

    def _paul_sheets(self):
        it = self.itin
        pin = it.paul_in
        ends = np.flatnonzero(pin[:-1] & ~pin[1:])
        for e in ends:
            if self.rng.random() < 0.8:
                s = self.first_awake(int(e) + self.g(70, 20, 30, 150), 1500)
                if s is not None:
                    self.wash(s, "hot", "Bed sheets after Paul")

    # ------------------------------------------------------------------ continuous loads
    def _continuous(self):
        N, rng = self.N, self.rng
        self.loads["laptop"] = np.minimum(self.loads["laptop"], 0.08)      # one laptop (overlapping sessions do not add up)
        hour = np.arange(N) // 60
        self.loads["wifi_router"][:] = 0.011 + 0.0015 * np.sin(hour * 1.7) + 0.0005 * np.cos(hour * 0.37)
        days = np.arange(N) // 1440
        daily_offset = np.array([rng.gauss(0, 0.002) for _ in range(int(days[-1]) + 1)])
        self.loads["wifi_router"][:] = np.clip(self.loads["wifi_router"] + daily_offset[days] / 2, 0.008, 0.015)
        standby = np.where(self.a_home | self.paul_home, np.where(self.awake_any, 0.038, 0.030), np.where(self.holiday, 0.020, 0.034))
        self.loads["standby"][:] = np.clip(standby + daily_offset[days] * 3, 0.02, 0.06)
        mod = self.mod
        level = np.where(self.dark,
                         np.where(self.guests > 0, 0.14, np.where(mod >= 1350, 0.06, np.where(mod >= 1020, 0.10 + 0.02 * self.paul_home, 0.07))),
                         np.where(self.CLOUD > 85, 0.03, 0.0))
        wobble = 0.9 + 0.2 * (((hour * 104729) % 11) / 10)
        day_gain = np.array([math.exp(rng.gauss(0, 0.08)) for _ in range(int(days[-1]) + 1)])
        lit = level * wobble * day_gain[days]
        lit = np.where(level >= 0.05, np.clip(lit, 0.05, 0.15), lit)    # dark hours: 0.05-0.15 kW as in the scenario
        self.loads["lighting"] += np.where(self.awake_any, lit, 0.0)

    # ------------------------------------------------------------------ thermal model, heat pump, fridge
    def _thermal(self):
        N, rng = self.N, self.rng
        L = self.loads
        non_hp = sum(L[a] for a in APPLIANCES if not a.startswith("heat_pump") and a != "fridge")
        gains = (900 * non_hp + 80 * self.a_awake + 60 * (self.a_home & self.asleep) + 80 * self.paul_awake
                 + 60 * (self.paul_home & ~self.paul_awake) + 90 * self.guests + 40 + 0.0)
        gains_l = gains.tolist()
        t_out, rad = self.T_OUT.tolist(), self.RAD.tolist()
        a_home = self.a_home.tolist()
        awake_any = self.awake_any.tolist()
        any_home = (self.a_home | self.paul_home).tolist()
        a_awake = self.a_awake.tolist()
        guests = self.guests.tolist()
        holiday = self.holiday.tolist()
        heat_season = self.heat_season.tolist()
        mod = self.mod.tolist()
        dhw_draw = self.dhw_draw.tolist()
        svc_off = np.zeros(N, dtype=bool)
        svc_test = np.zeros(N, dtype=bool)
        for e in self.events:
            if e.summary.startswith("Heat pump service"):
                s = self.mi(e.start)
                svc_off[s:s + 70] = True
                svc_test[s + 70:s + 90] = True
        svc_off, svc_test = svc_off.tolist(), svc_test.tolist()
        # comfort boost: 1 K warmer for 2.5 h after coming home from a long absence
        boost = np.zeros(N, dtype=bool)
        for t in self.trip_list:
            boost[t.t1:t.t1 + 240] = True
        boost = boost.tolist()
        weekday_of_day = [(self.start + timedelta(days=i)).weekday() for i in range(N // 1440 + 1)]
        restock = self.restocks
        restock_end = [r + 240 for r in restock]
        fridge_l = [0.0] * N
        hp_space, hp_dhw = [0.0] * N, [0.0] * N
        T_IN, SP = [0.0] * N, [0.0] * N
        tin, hp_on, hp_since, dhw_on, deficit = 21.0, False, -999, False, 1.0
        fridge_left = 0
        r_ptr = 0
        u = rng.uniform
        for i in range(N):
            # fridge compressor
            if i % CYCLE == 0:
                duty = 0.40 + 0.015 * (tin - 20) + 0.05 * a_awake[i] + 0.08 * (guests[i] > 0)
                while r_ptr < len(restock) and restock_end[r_ptr] <= i:
                    r_ptr += 1
                if r_ptr < len(restock) and restock[r_ptr] <= i:
                    duty += 0.15
                duty = min(0.75, max(0.3, duty + u(-0.04, 0.04)))
                fridge_left = round(duty * CYCLE)
            if fridge_left > 0:
                fridge_l[i] = FRIDGE_P
                fridge_left -= 1
            hol = holiday[i]
            deficit += DHW_LOSS + dhw_draw[i] + (0.05 / 60 if awake_any[i] else 0) + (0.3 / 60 if guests[i] else 0)
            day = i // 1440
            if weekday_of_day[day] == 6 and mod[i] == 120 and not hol:
                deficit += 1.2                               # weekly anti-legionella cycle
            if not heat_season[i]:
                sp = 15.0                                    # summer: heating switched off, only frost protection
            elif hol:
                sp = 16.0
            else:
                sp = 21.0 if 360 <= mod[i] < 1350 else 18.0
                if boost[i] and tin < 20.5:
                    sp = 22.0
            tout = t_out[i]
            mode, p_el, q_space = None, 0.0, 0.0
            if svc_off[i]:
                dhw_on = hp_on = False
            elif svc_test[i]:
                mode, p_el = "space", 2.4
                q_space = p_el * cop(tout)
            elif not hol and (dhw_on or deficit > DHW_TRIGGER):
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
                hp_space[i] = p_el
            elif mode == "dhw":
                hp_dhw[i] = p_el
            g = gains_l[i] + 900 * fridge_l[i] + (SOLAR_AREA if tin < 24 else SOLAR_AREA / 2) * rad[i]
            ua = UA
            if tout < tin:                                   # airing: windows open when it is warm inside
                if awake_any[i] and tin > 24.0:
                    ua += 120
                elif any_home[i] and tin > 23.5:
                    ua += 50
            tin += (ua * (tout - tin) + q_space * 1000 + g) * 60 / C
            T_IN[i], SP[i] = tin, sp
        L["fridge"][:] = fridge_l
        L["heat_pump_space_heating"][:] = hp_space
        L["heat_pump_hot_water"][:] = hp_dhw
        self.T_IN, self.SP = np.array(T_IN), np.array(SP)
        self._log_heat_pump()

    def _log_heat_pump(self):
        for col, why in (("heat_pump_space_heating", "Space heating (thermostat)"), ("heat_pump_hot_water", "Hot-water tank reheat")):
            x = self.loads[col] > 0
            edges = np.flatnonzero(np.diff(np.concatenate(([0], x.astype(np.int8), [0]))))
            for s, e in zip(edges[::2], edges[1::2]):
                self.log.append(dict(appliance=col, start=self.when(s), end=self.when(e), peak_kw=round(float(self.loads[col][s:e].max()), 3),
                                     kwh=round(float(self.loads[col][s:e].sum() / 60), 4), reason=why))

    # ------------------------------------------------------------------ run + output
    def run(self):
        self.pl_home = self.itin.pl.home_label
        self._weather()
        self._presence()
        self._behaviour()
        self._continuous()
        self._thermal()
        return self

    def write(self):
        cfg, N = self.cfg, self.N
        out = cfg.data / "consumption"
        out.mkdir(parents=True, exist_ok=True)
        H = N // 60
        hourly = {a: self.loads[a].reshape(H, 60).sum(1) / 60 for a in APPLIANCES}
        total = sum(hourly.values())
        mean = lambda x: x.reshape(H, 60).mean(1)
        a_share, p_share = mean(self.a_home.astype(float)), mean(self.paul_home.astype(float))
        t_in, sp = mean(self.T_IN), mean(self.SP)
        guests_max = self.guests.reshape(H, 60).max(1)
        hol_any = self.holiday.reshape(H, 60).any(1)

        def occ(h):
            block = slice(h * 60, h * 60 + 60)
            c = Counter()
            for i in range(block.start, block.stop, 5):
                c["home+guests" if self.guests[i] else "home+Paul" if self.a_home[i] and self.paul_home[i] else "home" if self.a_home[i]
                  else "Paul only" if self.paul_home[i] else "away"] += 1
            return c.most_common(1)[0][0]

        w = self.w
        with open(out / "hourly_consumption.csv", "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["timestamp", "period", "weather_source", "temp_out_c", "cloud_cover_pct", "shortwave_radiation_wm2",
                         "indoor_temp_c", "heating_setpoint_c", "occupancy", "aleksandra_home_share", "paul_home_share",
                         "guests", "heat_pump_holiday_mode"] + [f"{a}_kwh" for a in APPLIANCES] + ["total_kwh"])
            for h in range(H):
                t = w.times[h]
                wr.writerow([cfg.stamp(t), "history" if t < cfg.today else "future", w.source, w.temp[h], w.cloud[h], w.rad[h],
                             round(t_in[h], 2), round(sp[h], 1), occ(h), round(a_share[h], 2), round(p_share[h], 2), int(guests_max[h]), int(hol_any[h])]
                            + [round(float(hourly[a][h]), 4) for a in APPLIANCES] + [round(float(total[h]), 4)])
        with open(out / "simulation_ground_truth.csv", "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["timestamp", "occupancy", "aleksandra_home_share", "paul_home_share", "guests", "indoor_temp_c", "heating_setpoint_c", "heat_pump_holiday_mode"])
            for h in range(H):
                wr.writerow([cfg.stamp(w.times[h]), occ(h), round(a_share[h], 2), round(p_share[h], 2), int(guests_max[h]), round(t_in[h], 2), round(sp[h], 1), int(hol_any[h])])
        with open(out / "appliance_events.csv", "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=["appliance", "start", "end", "duration_min", "peak_kw", "kwh", "reason"])
            wr.writeheader()
            for e in sorted(self.log, key=lambda e: (e["start"], e["appliance"])):
                wr.writerow(dict(e, start=e["start"].strftime("%Y-%m-%d %H:%M"), end=e["end"].strftime("%Y-%m-%d %H:%M"),
                                 duration_min=int((e["end"] - e["start"]).total_seconds() // 60)))
        self.hourly, self.total = hourly, total
        return out
