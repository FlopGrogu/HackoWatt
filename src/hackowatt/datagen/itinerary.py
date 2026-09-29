"""Itinerary stage: turn the calendar (.ics) into where Aleksandra, Paul and guests are, minute by minute.

The calendar is the only input (plus the seed for human noise: leaving a bit early, coming back a bit late). Output is a
gap-free timeline of `Seg`s (stay at a place / move between places) for the whole year, boolean minute masks for the
consumption model, and the trip list. The geolocation stage samples the same timeline, so both data sets always agree.
"""
import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .config import clipped_gauss
from .geo import distance_m
from .ics import read_ics

OUTING_CATS = {"SOCIAL-OUT", "SPORT", "PERSONAL", "CHORES", "PAUL", "WORK"}


@dataclass
class Seg:
    t0: int                      # minute of the year, inclusive
    t1: int                      # exclusive
    kind: str                    # "stay" | "move"
    a: tuple                     # start coordinates
    b: tuple                     # end coordinates (== a for a stay)
    label: str
    mode: str = ""               # move: walk/car/flight/train; stay: home/place


@dataclass
class Trip:
    t0: int
    t1: int
    nights: int
    place: str


class Itinerary:
    def __init__(self, cfg, places, events=None):
        self.cfg, self.pl = cfg, places
        self.rng = cfg.rng("itinerary")
        self.events = events if events is not None else read_ics(cfg.full_calendar)
        self.N = cfg.hours * 60
        self.home = cfg.home
        self.segs = []
        self.trips = []
        self._build()

    # ------------------------------------------------------------------ helpers
    def idx(self, t):
        return int((t - self.cfg.start).total_seconds() // 60)

    def travel_min(self, a, b, mode="city"):
        d = distance_m(a, b) / 1000
        if d < 0.35:
            return 3
        minutes = 8 + d / (22 if d < 8 else 45) * 60
        return int(round(min(90, max(8, minutes))))

    def _hub(self, e, city_label, outbound):
        return e.location if outbound else city_label

    # ------------------------------------------------------------------ commitments
    def _commitments(self):
        """List of (t0, t1, kind, a_label, b_label, mode, trip_index) sorted by t0. kind: stay/move."""
        pl, cfg, rng = self.pl, self.cfg, self.rng
        home_label = pl.home_label
        items, windows = [], []          # windows: (t0, t1, base_label) for trips
        banners = [e for e in self.events if e.all_day and e.cat.startswith("TRAVEL")]
        for b in banners:
            first, last = b.first_day, b.last_day
            w0, w1 = self.idx(datetime.combine(first, datetime.min.time())), self.idx(datetime.combine(last + timedelta(1), datetime.min.time()))
            city = b.location.split(",")[0]
            base = self._trip_base(b, city)
            transport = [e for e in self.events if not e.all_day and e.cat == b.cat and e.summary.startswith(("Flight", "Train", "Taxi", "Drive"))
                         and first <= e.first_day <= last]
            transport.sort(key=lambda e: e.start)
            hub_dest = {"Flight": f"{city} Airport", "Train": f"{city} main station"}
            legs = [e for e in transport if not e.summary.startswith("Taxi")]
            t_out = self.idx(min(e.start for e in transport)) if transport else w0
            t_home = None
            for e in transport:
                s, en = self.idx(e.start), self.idx(e.end)
                kind = e.summary.split()[0]
                outbound = (e.first_day == first and e is not legs[-1]) if legs else True
                if e.summary.startswith("Taxi"):
                    items.append((s, en, "move", e.location, self._airport_of(transport, e, city), "car", None))
                elif kind == "Flight":
                    out_leg = e.location == pl.label["airport"]
                    o_label = e.location
                    d_label = f"{city} Airport ({e.summary.split()[-1]})" if out_leg else pl.label["airport"]
                    if out_leg:
                        items.append((s - 60, s, "stay", o_label, o_label, "place", None))
                    else:
                        items.append((s - 75, s, "stay", o_label, o_label, "place", None))
                    items.append((s, en, "move", o_label, d_label, "flight", None))
                    if not out_leg:
                        t_home = (en, en + int(clipped_gauss(rng, 45, 8, 30, 70)), d_label)
                elif kind == "Train":
                    out_leg = e.location == pl.label["station"]
                    o_label = e.location
                    d_label = f"{city} main station" if out_leg else pl.label["station"]
                    items.append((s - 10, s, "stay", o_label, o_label, "place", None))
                    items.append((s, en, "move", o_label, d_label, "train", None))
                    if not out_leg:
                        t_home = (en, en + int(clipped_gauss(rng, 22, 5, 12, 40)), d_label)
                else:   # drive with friends
                    out_leg = e.summary.startswith("Drive to")
                    items.append((s, en, "move", home_label if out_leg else b.location, b.location if out_leg else home_label, "car", None))
                    if not out_leg:
                        t_home = (en, en, b.location)
            if t_home:                                   # last leg -> flat
                items.append((t_home[0], t_home[1], "move", t_home[2], home_label, "car" if "Airport" in t_home[2] else "walk", None))
            # first-day leave for trains: home -> station
            for e in transport:
                if e.summary.startswith("Train") and e.location == pl.label["station"]:
                    s = self.idx(e.start) - 10
                    dur = self.travel_min(self.home, pl.coord(pl.label["station"]))
                    items.append((s - dur, s, "move", home_label, pl.label["station"], "car", None))
            end_t = t_home[1] if t_home else w1
            self.trips.append(Trip(min(t_out, w0 + 6 * 60) if transport else w0, end_t, (last - first).days, b.location))
            windows.append((self.idx(datetime.combine(first, datetime.min.time())), end_t, base))
            for e in self.events:
                if not e.all_day and first <= e.first_day <= last and e.cat in ("WORK", "SOCIAL-OUT", "PAUL", "SPORT") and not e.summary.startswith(("Flight", "Train", "Taxi", "Drive")):
                    if e.location and e.location != home_label and e.location != "Microsoft Teams":
                        items.append((self.idx(e.start), self.idx(e.end), "stay", e.location, e.location, "place", None))
        # ---- local life
        in_trip = lambda d: any(b.first_day <= d <= b.last_day for b in banners)
        for e in self.events:
            if e.all_day:
                if e.cat == "OFFICE" and not in_trip(e.first_day):
                    day0 = datetime.combine(e.first_day, datetime.min.time())
                    leave = clipped_gauss(rng, 8 * 60 + 5, 12, 7 * 60 + 35, 8 * 60 + 50)
                    back = clipped_gauss(rng, 17 * 60 + 40, 25, 16 * 60 + 45, 19 * 60)
                    o = pl.label["office"]
                    tt = self.travel_min(self.home, pl.coord(o))
                    items.append((self.idx(day0) + int(leave) - tt, self.idx(day0) + int(leave), "move", home_label, o, "transit", None))
                    items.append((self.idx(day0) + int(leave), self.idx(day0) + int(back), "stay", o, o, "place", None))
                    items.append((self.idx(day0) + int(back), self.idx(day0) + int(back) + tt, "move", o, home_label, "transit", None))
                continue
            if in_trip(e.first_day) or e.cat not in OUTING_CATS:
                continue
            loc = e.location
            if not loc or loc == home_label or loc == "Microsoft Teams" or loc.startswith("Room '"):
                continue
            if e.cat == "WORK":
                continue
            s, en = self.idx(e.start), self.idx(e.end)
            tt = self.travel_min(self.home, pl.coord(loc))
            lead = tt + int(abs(rng.gauss(4, 3)))
            items.append((s - lead, s, "move", home_label, loc, "transit", None))
            items.append((s, en, "stay", loc, loc, "place", None))
            items.append((en, en + tt + int(abs(rng.gauss(3, 3))), "move", loc, home_label, "transit", None))
        return items, windows

    def _airport_of(self, transport, taxi, city):
        for e in transport:
            if e.summary.startswith("Flight") and e.location == self.pl.label["airport"] and e.start > taxi.start:
                return e.location
        return self.pl.label["airport"]

    def _trip_base(self, banner, city):
        d = banner.desc
        if d.startswith("Hotel:"):
            return f"{d[6:].split(' (')[0].strip()}, {city}"
        if "Paul" in d:
            return f"Paul's flat, Prenzlauer Berg, {city}"
        if d.startswith(("Chalet", "Apartment", "Guesthouse")):
            return f"{d.split(' (')[0].split(' with')[0].strip('.')}, {city}"
        if "Mum" in banner.summary:
            return f"Mum & Dad's, {city}"
        return f"Stay, {city}"

    # ------------------------------------------------------------------ timeline
    def _build(self):
        pl, N = self.pl, self.N
        items, windows = self._commitments()
        items = [it for it in items if it[1] > it[0] and it[1] > 0 and it[0] < N]
        items.sort(key=lambda it: (it[0], it[1]))
        wstarts = sorted(windows)
        home_label = pl.home_label
        segs = []
        cur_t, cur_label = 0, home_label

        def base_at(t):
            for w0, w1, base in wstarts:
                if w0 <= t < w1:
                    return base
            return home_label

        def stay(t1, label, mode="place"):
            nonlocal cur_t
            if t1 > cur_t:
                c = pl.coord(label)
                segs.append(Seg(cur_t, t1, "stay", c, c, label, "home" if label == home_label else mode))
                cur_t = t1

        def move(t0, t1, a_label, b_label, mode):
            """Stay at a_label until t0, then move (a -> b) during [t0, t1)."""
            nonlocal cur_t, cur_label
            stay(t0, a_label)
            if t1 <= cur_t:
                cur_label = b_label
                return
            segs.append(Seg(cur_t, t1, "move", pl.coord(a_label), pl.coord(b_label), f"{a_label} -> {b_label}", mode))
            cur_t, cur_label = t1, b_label

        def go_to(label, t_arrive, mode="transit"):
            """Get from cur_label to `label`, arriving at t_arrive. Long gaps are spent at the base (hotel / home)."""
            nonlocal cur_label
            base = base_at(cur_t)
            if t_arrive - cur_t > 150 and pl.distance(cur_label, base) > 250:
                tb = self.travel_min(pl.coord(cur_label), pl.coord(base))
                move(cur_t, cur_t + tb, cur_label, base, mode)
            if pl.distance(cur_label, label) < 250:
                stay(t_arrive, cur_label)
                return
            direct = self.travel_min(pl.coord(cur_label), pl.coord(label))
            depart = max(cur_t, t_arrive - direct)
            move(depart, max(depart + 1, t_arrive), cur_label, label, mode)

        for t0, t1, kind, a_label, b_label, mode, _ in items:
            if t0 < cur_t - 5 and kind == "stay":
                continue                                  # overlaps something she is already doing
            if t0 < cur_t and kind == "move" and mode in ("transit",) and cur_label != a_label:
                continue
            if kind == "stay":
                go_to(a_label, t0)
                stay(t1, a_label)
                cur_label = a_label
            else:
                if pl.distance(cur_label, a_label) >= 250 and t0 > cur_t:
                    go_to(a_label, t0)
                move(max(t0, cur_t), t1, cur_label if pl.distance(cur_label, a_label) < 250 else a_label, b_label, mode)
        # back home for the rest of the year (base is home outside trips)
        if pl.distance(cur_label, home_label) > 250:
            move(cur_t, cur_t + self.travel_min(pl.coord(cur_label), self.home), cur_label, home_label, "transit")
        stay(N, home_label)
        for s in segs:
            s.t1 = min(s.t1, N)
        self.segs = [s for s in segs if s.t1 > s.t0]
        self._starts = [s.t0 for s in self.segs]
        away = np.zeros(N, dtype=bool)
        for s in self.segs:
            if not (s.kind == "stay" and s.mode == "home"):
                away[s.t0:s.t1] = True
        self.away = away
        self._people()

    def _people(self):
        N, pl = self.N, self.pl
        home_label = pl.home_label
        self.paul_in = np.zeros(N, dtype=bool)
        self.guests = np.zeros(N, dtype=np.int16)
        self.paul_out = np.zeros(N, dtype=bool)
        banners = [e for e in self.events if e.all_day and e.cat == "PAUL" and e.location == home_label]
        for b in banners:
            first, last = b.first_day, b.last_day
            timed = [e for e in self.events if not e.all_day and e.cat == "PAUL" and first <= e.first_day <= last]
            arr = [e for e in timed if e.first_day == first and e.location != home_label and ("lands" in e.summary or "Pick up" in e.summary)]
            dep = [e for e in timed if e.first_day == last and ("Paul" in e.summary and ("leaves" in e.summary or "Bring" in e.summary))]
            t0 = self.idx(arr[0].end) + 35 if arr else self.idx(datetime.combine(first, datetime.min.time())) + 18 * 60
            t1 = self.idx(dep[0].start) if dep else self.idx(datetime.combine(last, datetime.min.time())) + 12 * 60
            self.paul_in[max(0, t0):min(N, t1)] = True
        for e in self.events:
            if e.all_day:
                continue
            s, en = self.idx(e.start), self.idx(e.end)
            if e.cat == "GUESTS-HOME":
                names = [n.strip() for n in e.desc.replace("Guests:", "").rstrip(".").split(",") if n.strip() and n.strip() != "Paul"]
                self.guests[max(0, s - 10):min(N, en)] = max(1, len(names))
            elif "Paul" in e.summary and e.location != home_label and e.cat in ("SOCIAL-OUT", "SPORT"):
                self.paul_out[max(0, s - 20):min(N, en + 20)] = True

    # ------------------------------------------------------------------ queries
    def segment_at(self, minute):
        return self.segs[bisect.bisect_right(self._starts, minute) - 1]

    def position(self, minute):
        """(lat, lon, mode) of her phone at a minute of the year, before GPS noise."""
        from .geo import interpolate
        s = self.segment_at(minute)
        if s.kind == "stay":
            return s.a[0], s.a[1], s.mode
        f = (minute - s.t0) / max(1, s.t1 - s.t0)
        f = f * f * (3 - 2 * f) if s.mode in ("car", "transit", "walk") else f       # accelerate / brake in town
        lat, lon = interpolate(s.a, s.b, f)
        return lat, lon, s.mode

    def write(self):
        import csv
        out = self.cfg.data / "geolocation"
        out.mkdir(parents=True, exist_ok=True)
        base = self.cfg.start
        with open(out / "itinerary_truth.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["start", "end", "kind", "mode", "place", "lat_from", "lon_from", "lat_to", "lon_to"])
            for s in self.segs:
                w.writerow([(base + timedelta(minutes=s.t0)).strftime("%Y-%m-%d %H:%M"), (base + timedelta(minutes=s.t1)).strftime("%Y-%m-%d %H:%M"),
                            s.kind, s.mode, s.label, f"{s.a[0]:.5f}", f"{s.a[1]:.5f}", f"{s.b[0]:.5f}", f"{s.b[1]:.5f}"])
