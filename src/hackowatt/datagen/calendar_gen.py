"""Calendar stage: a realistic, fully procedural year for Aleksandra (seeded, normally distributed times and durations).

Conventions the itinerary stage relies on (see itinerary.py):
  * all-day OFFICE / WFH entries mark the working mode of a day
  * an all-day TRAVEL-WORK / TRAVEL-PRIVATE entry is the trip banner (location = destination city);
    the timed transport entries start with "Flight", "Train", "Taxi" or "Drive"
  * an all-day PAUL entry with location HOME is a visit; timed PAUL entries at the airport / station are pick-ups
  * GUESTS-HOME entries list the guests in the description ("Guests: A, B, C.")
  * every other timed entry with a location outside the home is an outing; entries at home keep her at home

Year plan: seasonal anchors (holidays, ski week, summer holiday, conference, Paul's visits and Berlin weekends, family) are
placed first; the rest of the year is filled with work and private trips so that about `target_away` of the time is spent on
trips: single nights, 3-4 day work trips and a few day trips. Everyday life (office/WFH, sport, social, chores) fills the gaps.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .config import clipped_gauss
from .geo import distance_m
from .ics import Event
from .places import BY_NAME, CITIES, PAUL_CITY, PRIVATE, Places

IATA = {"Stockholm": "ARN", "Berlin": "BER", "Brussels": "BRU", "Vienna": "VIE", "Copenhagen": "CPH", "London": "LHR",
        "Munich": "MUC", "Amsterdam": "AMS", "Paris": "CDG", "Frankfurt": "FRA", "Zurich": "ZRH", "Milan": "MXP",
        "Prague": "PRG", "Budapest": "BUD", "Helsinki": "HEL", "Oslo": "OSL", "Dublin": "DUB", "Madrid": "MAD",
        "Hamburg": "HAM", "Essen": "DUS", "Split": "SPU", "Lisbon": "LIS", "Rome": "FCO", "Porto": "OPO", "Mayrhofen": "MUC"}
AIRLINE = {"Brussels": "SN", "Zurich": "LX", "Lisbon": "TP", "Porto": "TP", "Split": "LO", "Amsterdam": "KL", "Paris": "AF"}
TOPICS = ["pilot design sprint", "partnership review", "flexibility tender workshop", "kickoff", "steering committee",
          "quarterly review", "data-sharing workshop", "customer interviews", "contract negotiation", "product roadmap day",
          "pilot go/no-go", "demand-response deep-dive", "integration workshop", "commercial terms", "go-live preparation"]
OFFICE_MEETINGS = ["Q{q} partnership pipeline review", "Product roadmap sync", "Budget review", "Tender prep – municipal flexibility",
                   "Partner onboarding – new DSO", "Sales & partnerships weekly", "Hiring interview – partner manager",
                   "Legal review – data sharing agreement", "All-hands", "Customer success sync", "Pricing model workshop",
                   "Board deck review", "Strategy offsite prep", "1:1 with Anna (manager)", "Demo – flexibility dashboard"]
WFH_MEETINGS = ["Nordvolt pilot – weekly call", "VoltHaus – tariff model review", "KrakGrid – data quality call",
                "Focus: write partner proposal", "DonauNetz – tender Q&A", "Kraftly – integration check-in",
                "Isarwatt – API follow-up", "Polderstroom – offer review", "Expense report + travel booking",
                "Investor update call", "Webinar – EU network code on demand response", "Recruiting screen – analyst"]
FRIENDS = ["Kasia", "Marta", "Tomek", "Ola", "Bartek"]
BERLIN_LEISURE = [("Flohmarkt Mauerpark", "Mauerpark, Berlin", 3), ("Tempelhofer Feld – bikes w/ Paul", "Tempelhofer Feld, Berlin", 3),
                  ("Museum Island w/ Paul", "Museumsinsel, Berlin", 4), ("Brunch w/ Paul – Café Einstein", "Café Einstein, Berlin", 2.5),
                  ("Concert w/ Paul", "Berliner Philharmonie", 3), ("Dinner w/ Paul's friends", "Neukölln, Berlin", 3.5),
                  ("Lake Schlachtensee w/ Paul", "Schlachtensee, Berlin", 5), ("Christmas market w/ Paul", "Gendarmenmarkt, Berlin", 3)]


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    return date(y, month, (h + l - 7 * m + 33 * month + 19) % 32)


def holidays(y):
    e = easter(y)
    fixed = {date(y, 1, 1): "New Year's Day", date(y, 1, 6): "Epiphany", date(y, 5, 1): "Labour Day", date(y, 5, 3): "Constitution Day",
             date(y, 8, 15): "Assumption Day", date(y, 11, 1): "All Saints' Day", date(y, 11, 11): "Independence Day",
             date(y, 12, 24): "Christmas Eve", date(y, 12, 25): "Christmas Day", date(y, 12, 26): "Second Day of Christmas"}
    fixed.update({e: "Easter Sunday", e + timedelta(1): "Easter Monday", e + timedelta(49): "Pentecost",
                  e + timedelta(60): "Corpus Christi"})
    return fixed


def dt(day, hhmm):
    h, m = map(int, hhmm.split(":")) if isinstance(hhmm, str) else divmod(int(hhmm), 60)
    return datetime.combine(day, time(h, m))


def rnd5(x):
    """Round a datetime to the nearest 5 minutes."""
    m = round((x.hour * 60 + x.minute) / 5) * 5
    return datetime.combine(x.date(), time(0)) + timedelta(minutes=m)


@dataclass
class Trip:
    first: date
    last: date
    kind: str                      # work | paul | family | ski | holiday | getaway
    city: object                   # places.City
    title: str
    via: str = ""                  # flight | train | car (default: the city's mode)
    stay: str = ""
    desc: str = ""
    leisure: list = field(default_factory=list)   # (day offset, start, end, title, location)
    fixed_out: tuple = None        # (code, route, dep, arr) override of the outbound leg

    @property
    def nights(self):
        return (self.last - self.first).days


class Planner:
    def __init__(self, cfg, places):
        self.cfg, self.pl = cfg, places
        self.rng = cfg.rng("calendar")
        self.y = cfg.year
        self.first, self.last = date(self.y, 1, 1), date(self.y, 12, 31)
        self.events = []
        self.busy = defaultdict(list)
        self.away_nights = set()
        self.paul_days = set()
        self.leave_home, self.arrive_home = {}, {}
        self.holidays = holidays(self.y)
        self.trips = []
        self.wfh_forced = set()
        self.home = places.home_label

    # ------------------------------------------------------------------ helpers
    def add(self, start, end, summary, cat, location="", desc="", block=True, busy=True):
        if end <= start:
            end += timedelta(days=1)
        self.events.append(Event(start, end, summary, cat, location, desc, busy))
        if block:
            d = start.date()
            self.busy[d].append((start.time(), end.time() if end.date() == d else time(23, 59)))

    def allday(self, first, last, summary, cat, location="", desc="", busy=False):
        self.events.append(Event(first, last + timedelta(days=1), summary, cat, location, desc, busy))

    def block(self, day, s, e):
        self.busy[day].append((s, e))

    def free(self, day, start, end):
        s, e = dt(day, start).time(), dt(day, end).time()
        return all(e <= bs or s >= be for bs, be in self.busy[day])

    def is_away(self, day):
        return day in self.leave_home or day in self.arrive_home or day in self.away_nights or (day - timedelta(1)) in self.away_nights

    def fully_away(self, day):
        return day in self.away_nights and (day - timedelta(1)) in self.away_nights and day not in self.leave_home and day not in self.arrive_home

    def gauss_minutes(self, mu, sigma, lo, hi):
        return int(round(clipped_gauss(self.rng, mu, sigma, lo, hi)))

    # ------------------------------------------------------------------ transport
    def _flight_leg(self, city, day, outbound, earliest=None, latest_dep=None):
        rng = self.rng
        home = (self.cfg.lat, self.cfg.lon)
        km = distance_m(home, (city.lat, city.lon)) / 1000
        dur = rnd5(datetime(2000, 1, 1) + timedelta(minutes=km / 760 * 60 + 40)) - datetime(2000, 1, 1)
        code = f"{AIRLINE.get(city.name, 'LO')} {rng.randint(200, 690)}"
        iata = IATA[city.name]
        if outbound:
            dep = dt(day, rng.choice(["06:40", "06:40", "07:05", "07:20", "07:45", "10:40", "16:10"])) if earliest is None else earliest
            route = f"{self.cfg.iata} → {iata}"
        else:
            dep = latest_dep
            route = f"{iata} → {self.cfg.iata}"
        arr = dep + dur
        note = ""
        if city.tz_shift:
            note = f"Lands {arr + timedelta(hours=city.tz_shift):%H:%M} local time." if outbound else f"Departs {dep + timedelta(hours=city.tz_shift):%H:%M} local time."
        return code, route, dep, arr, note

    def _train_leg(self, city, day, outbound, dep_after=None):
        rng = self.rng
        km = distance_m((self.cfg.lat, self.cfg.lon), (city.lat, city.lon)) / 1000
        dur = timedelta(minutes=int(round((km * 1.25 / 105 * 60 + 12) / 5) * 5))
        code = f"{rng.choice(['EIP', 'IC', 'EIC'])} {rng.randint(1000, 9999)}"
        if outbound:
            dep = dt(day, rng.choice(["06:15", "07:05", "07:30", "09:20", "10:05", "13:05"]))
            route = f"{self.cfg.city} → {city.name}"
        else:
            dep = dep_after
            route = f"{city.name} → {self.cfg.city}"
        return code, route, dep, dep + dur

    def emit_trip(self, t):
        rng, pl, cfg = self.rng, self.pl, self.cfg
        city, first, last = t.city, t.first, t.last
        cat = "TRAVEL-WORK" if t.kind == "work" else "TRAVEL-PRIVATE"
        desc = " ".join(x for x in ((f"{t.stay} ({t.nights} nights)." if t.stay and t.nights else t.stay), t.desc) if x)
        place = f"{city.name}, {city.country}"
        self.allday(first, last, t.title, cat, place, desc)
        via = t.via or city.mode
        # outbound leg first: its arrival time decides whether there is a meeting on the first day
        if via == "flight":
            out = t.fixed_out or self._flight_leg(city, first, True)
            arrival = out[3]
        elif via == "train":
            out = self._train_leg(city, first, True)
            arrival = out[3]
        else:
            out, arrival = None, dt(first, "12:30")
        meetings = t.leisure or self._work_meetings(t, arrival)
        last_end = max([m[2] for m in meetings if m[0] == (last - first).days], default=None)
        if via == "flight":
            back_dep = rnd5(max(dt(last, "15:00"), (last_end + timedelta(minutes=150)) if last_end else dt(last, "17:30")))
            back_dep = min(back_dep, dt(last, "21:00"))
            if t.kind != "work":
                back_dep = dt(last, rng.choice(["14:15", "18:30", "19:45"]))
            back = self._flight_leg(city, last, False, latest_dep=back_dep)
            self._flight_events(first, out, cat, taxi=True, city=city)
            self._flight_events(last, back, cat, taxi=False, city=city)
            self.leave_home[first] = out[2] - timedelta(minutes=75)
            self.arrive_home[last] = back[3] + timedelta(minutes=45)
        elif via == "train":
            dep_back = rnd5(max(dt(last, "16:30"), (last_end + timedelta(minutes=75)) if last_end else dt(last, "17:10")))
            if t.kind != "work":
                dep_back = dt(last, rng.choice(["13:30", "16:05", "17:10", "19:55"]))
            back = self._train_leg(city, last, False, dep_after=min(dep_back, dt(last, "21:15")))
            for leg, origin in ((out, pl.label["station"]), (back, f"{city.name} main station")):
                self.add(leg[2], leg[3], f"Train {leg[0]} {leg[1]}", cat, origin, f"Car {rng.randint(2, 9)}, seat {rng.randint(11, 88)}.")
            self.leave_home[first] = out[2] - timedelta(minutes=20)
            self.arrive_home[last] = back[3] + timedelta(minutes=20)
        else:                                            # car with friends
            s, e = dt(first, "08:30"), dt(first, "12:30")
            self.add(s, e, f"Drive to {city.name} w/ {rng.choice(FRIENDS)}", cat, self.home, "Picks me up at 08:30.")
            b = dt(last, "14:00")
            self.add(b, b + timedelta(hours=4), f"Drive back from {city.name}", cat, place)
            self.leave_home[first], self.arrive_home[last] = s - timedelta(minutes=10), b + timedelta(hours=4, minutes=15)
        for off, s, e, title, loc in meetings:
            self.add(s, e, title, "WORK" if t.kind == "work" else "PAUL" if "Paul" in title else "SOCIAL-OUT", loc)
        day = first
        while day <= last:
            if day < last:
                self.away_nights.add(day)
            s = self.leave_home[first].time() if day == first else time(0, 0)
            e = self.arrive_home[last].time() if day == last else time(23, 59)
            self.block(day, s, e)
            day += timedelta(1)
        if last > first and rng.random() < 0.75:
            eve = first - timedelta(1)
            if self.free(eve, "20:00", "20:30") and not self.fully_away(eve):
                self.add(dt(eve, "20:00"), dt(eve, "20:30"), f"Laundry + pack for {city.name}", "CHORES", self.home, block=False)

    def _flight_events(self, day, leg, cat, taxi, city):
        code, route, dep, arr, note = leg
        home_side = route.startswith(self.cfg.iata)
        if taxi and home_side:
            self.add(dep - timedelta(minutes=75), dep - timedelta(minutes=45), "Taxi to airport", cat, self.home,
                     f"Bolt booked for {dep - timedelta(minutes=75):%H:%M}.")
        far = self.pl.label["airport"] if home_side else f"{city.name} Airport ({route.split(' → ')[0]})"
        seat = f"Seat {self.rng.choice('ACDF')}{self.rng.randint(2, 18)}."
        self.add(dep, arr, f"Flight {code} {route}", cat, far, f"{seat} {note}".strip())

    def _work_meetings(self, t, arrival):
        rng, city = self.rng, t.city
        out, n = [], (t.last - t.first).days
        topic = rng.choice(TOPICS)
        venue = self._venue(city)
        for k in range(n + 1):
            day = t.first + timedelta(k)
            if n == 0:
                s = dt(day, "10:00") + timedelta(minutes=self.gauss_minutes(0, 20, -30, 60))
                e = s + timedelta(minutes=self.gauss_minutes(330, 40, 240, 420))
            elif k == 0:
                s = max(dt(day, "13:00") + timedelta(minutes=self.gauss_minutes(30, 20, 0, 90)), arrival + timedelta(minutes=110))
                if s > dt(day, "16:00"):
                    continue                                   # arrives too late for a meeting
                e = s + timedelta(minutes=self.gauss_minutes(210, 30, 120, 270))
            elif k == n:
                s = dt(day, "09:00") + timedelta(minutes=self.gauss_minutes(0, 15, -15, 45))
                e = s + timedelta(minutes=self.gauss_minutes(215, 40, 120, 300))
            else:
                s = dt(day, "09:00") + timedelta(minutes=self.gauss_minutes(0, 20, -15, 60))
                e = s + timedelta(minutes=self.gauss_minutes(450, 50, 300, 540))
            out.append((k, rnd5(s), rnd5(e), f"{city.partner or city.name} – {topic if k in (0, n) and n else rng.choice(TOPICS)}", venue))
            if 0 < k < n and rng.random() < 0.3:
                ds = dt(day, "19:00") + timedelta(minutes=rng.choice([0, 30]))
                out.append((k, ds, ds + timedelta(minutes=self.gauss_minutes(120, 20, 75, 180)), f"Team dinner – {city.name}", f"Restaurant, {city.name}"))
        return out

    def _venue(self, city):
        return f"{city.partner or 'Partner office'}, {city.name}"

    # ------------------------------------------------------------------ planning
    def add_trip(self, trip):
        self.trips.append(trip)

    def blocked(self, first, last, buffer_before=1, buffer_after=1):
        taken = set()
        for t in self.trips:
            d = t.first - timedelta(buffer_before)
            while d <= t.last + timedelta(buffer_after):
                taken.add(d)
                d += timedelta(1)
        d = first
        while d <= last:
            if d in taken:
                return True
            d += timedelta(1)
        return False

    def plan_anchors(self):
        y, rng = self.y, self.rng
        # New Year with Paul (the one starting the year and the one ending it)
        for yr in (y - 1, y):
            self.add_trip(Trip(date(yr, 12, 30), date(yr + 1, 1, 2), "paul", PAUL_CITY, "New Year in Berlin with Paul", via="flight",
                               stay="Staying at Paul's", leisure=[(1, dt(date(yr, 12, 31), "20:00"), dt(date(yr, 12, 31), "20:00") + timedelta(hours=6), "New Year's Eve party – Paul's friends", "Friedrichshain, Berlin")],
                               fixed_out=None))
        # Christmas with the family
        self.add_trip(Trip(date(y, 12, 23), date(y, 12, 27), "family", PRIVATE["Łódź"], "Christmas – Mum & Dad in Łódź", via="train",
                           desc="Christmas Eve dinner at Mum & Dad's. Presents in the blue bag!",
                           leisure=[(1, dt(date(y, 12, 24), "17:00"), dt(date(y, 12, 24), "23:00"), "Wigilia – Christmas Eve dinner", "Mum & Dad's, Łódź"),
                                    (2, dt(date(y, 12, 25), "13:00"), dt(date(y, 12, 25), "18:00"), "Christmas lunch – Aunt Basia", "Łódź")]))
        e = easter(y)
        self.add_trip(Trip(e - timedelta(1), e + timedelta(1), "family", PRIVATE["Łódź"], "Easter – Mum & Dad in Łódź", via="train",
                           leisure=[(1, dt(e, "12:00"), dt(e, "17:00"), "Easter lunch at Mum & Dad's", "Mum & Dad's, Łódź")]))
        self.add_trip(Trip(date(y, 10, 31), date(y, 11, 2), "family", PRIVATE["Łódź"], "All Saints – Mum & Dad in Łódź", via="train",
                           desc="Cemetery visits on 1 Nov with Mum & Dad.",
                           leisure=[(1, dt(date(y, 11, 1), "10:00"), dt(date(y, 11, 1), "14:00"), "All Saints – cemetery (Grandma & Grandpa)", "Stary Cmentarz, Łódź")]))
        # ski week: Saturday to Saturday around 21 Feb
        sat = date(y, 2, 21)
        sat += timedelta((5 - sat.weekday()) % 7)
        self.add_trip(Trip(sat, sat + timedelta(7), "ski", PRIVATE["Mayrhofen"], "Ski week – Mayrhofen (Zillertal)", via="flight",
                           stay="Chalet with Kasia, Tomek & Ola", desc="Ski pass booked. Take ski helmet + goggles.",
                           leisure=[(k, dt(sat + timedelta(k), "09:30"), dt(sat + timedelta(k), "16:00"), "Skiing – Penken / Ahorn", "Mayrhofen") for k in range(1, 7)]))
        # summer holiday: 8-9 days from the Saturday nearest 22 Aug
        sat = date(y, 8, 22)
        sat += timedelta((5 - sat.weekday()) % 7)
        dest = PRIVATE[rng.choice(["Split", "Lisbon", "Porto"])]
        self.add_trip(Trip(sat, sat + timedelta(rng.choice([7, 8])), "holiday", dest, f"Summer holiday – {dest.name}", via="flight",
                           stay="Apartment near the old town",
                           leisure=[(k, dt(sat + timedelta(k), "10:30"), dt(sat + timedelta(k), "17:00"), rng.choice(["Beach day", "Snorkelling trip", "Old town walk + lunch", "Boat excursion", "Hike + swim"]), dest.name) for k in range(1, 7)]))
        # conferences
        self.add_trip(Trip(date(y, 2, 9), date(y, 2, 12), "work", BY_NAME["Essen"], "Essen – E-world energy & water", via="flight",
                           stay="Hotel: Mintrops Stadt Hotel Margarethenhöhe",
                           leisure=[(1, dt(date(y, 2, 10), "09:00"), dt(date(y, 2, 10), "18:00"), "E-world – booth duty + partner meetings", "Messe Essen"),
                                    (2, dt(date(y, 2, 11), "09:00"), dt(date(y, 2, 11), "18:00"), "E-world – panel 'Flexible households' 14:00", "Messe Essen, Hall 3"),
                                    (3, dt(date(y, 2, 12), "09:00"), dt(date(y, 2, 12), "14:00"), "E-world – last meetings", "Messe Essen")]))
        mon = date(y, 6, 22)
        mon += timedelta((0 - mon.weekday()) % 7)
        self.add_trip(Trip(mon, mon + timedelta(3), "work", BY_NAME["Munich"], "Munich – The smarter E Europe", via="flight",
                           stay="Hotel: Motel One München-Sendlinger Tor",
                           leisure=[(k, dt(mon + timedelta(k), "09:00"), dt(mon + timedelta(k), "17:30" if k < 3 else "13:00"), "Intersolar / ees – partner meetings", "Messe München") for k in range(1, 4)]))
        # Paul: he visits Warsaw, she visits Berlin (about every second weekend, alternating)
        fri = date(y, 1, 9)
        visit_paul = rng.random() < 0.5
        while fri < self.last - timedelta(3):
            fri += timedelta(int(round(clipped_gauss(rng, 14, 3, 9, 21))))
            fri += timedelta((4 - fri.weekday()) % 7)
            span_last = fri + timedelta(2 if rng.random() < 0.8 else 3)
            if fri > self.last - timedelta(3) or self.blocked(fri - timedelta(1), span_last, 0, 1):
                continue
            if visit_paul:
                self._paul_visit(fri, span_last)
            else:
                self._berlin_weekend(fri, span_last)
            visit_paul = not visit_paul if rng.random() < 0.85 else visit_paul

    def _berlin_weekend(self, fri, back):
        rng, y = self.rng, self.y
        start = fri - timedelta(1) if rng.random() < 0.25 else fri
        leisure = []
        sat = fri + timedelta(1)
        pool = [b for b in BERLIN_LEISURE if not (b[0].startswith("Lake") and not 5 <= sat.month <= 9) and not (b[0].startswith("Christmas") and sat.month != 12)]
        for k, (title, loc, hours) in enumerate(rng.sample(pool, 2)):
            day = sat + timedelta(k if k < (back - sat).days else 0)
            s = dt(day, rng.choice(["11:00", "14:00", "19:30"]))
            leisure.append(((day - start).days, s, s + timedelta(hours=hours), title, loc))
        if start != fri and rng.random() < 0.6:
            leisure.append((1, dt(fri, "09:00"), dt(fri, "14:00"), "Work from Paul's", "Prenzlauer Berg, Berlin"))
        via = rng.choice(["flight", "flight", "train"])
        trip = Trip(start, back, "paul", PAUL_CITY, rng.choice(["Berlin – long weekend with Paul", "Berlin – weekend with Paul"]), via=via,
                    stay="Staying at Paul's", leisure=leisure)
        if via == "flight":
            trip.fixed_out = ("LO 381", f"{self.cfg.iata} → BER", dt(start, "16:10" if start == fri else "19:15"), dt(start, "17:35" if start == fri else "20:40"), "")
        self.add_trip(trip)

    def _paul_visit(self, fri, sun):
        t = Trip(fri, sun, "paulhere", PAUL_CITY, "Paul in Warsaw", via="none")
        self.trips.append(t)                      # blocks the days; emitted by emit_paul()

    def emit_paul(self, t):
        rng, pl = self.rng, self.pl
        first, last = t.first, t.last
        self.allday(first, last, "Paul in Warsaw", "PAUL", self.home)
        d = first
        while d <= last:
            self.paul_days.add(d)
            d += timedelta(1)
        by_air = rng.random() < 0.6
        if by_air:
            arr = dt(first, "19:40") + timedelta(minutes=rng.choice([-30, 0, 0, 20]))
            self.add(arr - timedelta(minutes=40), arr + timedelta(minutes=50), f"Paul lands – LO 386 from BER", "PAUL", pl.label["airport"])
        else:
            arr = dt(first, "15:25")
            self.add(arr, arr + timedelta(minutes=30), "Pick up Paul – EC 45 from Berlin", "PAUL", pl.label["station"], f"Arrives {arr:%H:%M}.")
        dep = dt(last, rng.choice(["12:25", "14:30", "16:00"]))
        if rng.random() < 0.5:
            self.add(dep, dep + timedelta(minutes=30), "Bring Paul to the " + ("airport" if by_air else "station"), "PAUL", pl.label["airport" if by_air else "station"], block=True)
        else:
            self.add(dep, dep + timedelta(minutes=30), "Paul leaves for the " + ("airport" if by_air else "station"), "PAUL", self.home, block=False)
        sat = first + timedelta(1)
        options = [("Dinner at home w/ Paul", "PAUL", self.home, "19:30", 3), ("Cooking night w/ Paul", "PAUL", self.home, "19:30", 3),
                   ("Brunch w/ Paul", "SOCIAL-OUT", pl.label["charlotte"], "11:30", 2.5), ("Walk w/ Paul", "SPORT", pl.label["park"], "10:30", 2.5),
                   ("Cinema w/ Paul", "SOCIAL-OUT", pl.label["kino"], "20:00", 3), ("Dinner out w/ Paul", "SOCIAL-OUT", pl.label["nolita"], "19:30", 3)]
        if 5 <= sat.month <= 8:
            options.append(("Vistula beach w/ Paul", "SOCIAL-OUT", pl.label["poniatowka"], "12:00", 5))
        if sat.month in (11, 12):
            options.append(("Christmas market Old Town w/ Paul", "SOCIAL-OUT", pl.label["oldtown"], "15:00", 4))
        for title, cat, loc, s, h in rng.sample(options, 2):
            st = dt(sat, s) + timedelta(minutes=rng.choice([-30, 0, 0, 30]))
            self.add(st, st + timedelta(hours=h), title, cat, loc)

    def plan_random_trips(self):
        """Fill the year with trips. Every free day starts a trip with a weekday-dependent probability; the base rate is
        tuned (grid search, each candidate plan is deterministic) so that the total away share hits target_away."""
        anchors = list(self.trips)
        best = None
        for k in range(40):
            rate = 0.03 + 0.02 * k
            self.trips = list(anchors)
            self._fill(self.cfg.rng(f"trips:{rate:.2f}"), rate)
            frac = self.away_fraction()
            if best is None or abs(frac - self.cfg.target_away) < abs(best[0] - self.cfg.target_away):
                best = (frac, rate)
        self.trips = list(anchors)
        self._fill(self.cfg.rng(f"trips:{best[1]:.2f}"), best[1])
        self.trip_rate = best[1]

    def away_fraction(self):
        hours = 0.0
        for t in self.trips:
            if t.kind == "paulhere":
                continue
            lo, hi = max(t.first, self.first), min(t.last, self.last)
            if hi >= lo:
                hours += (hi - lo).days * 24 + 15
        return hours / (366 * 24 if self.y % 4 == 0 else 365 * 24)

    WEEKDAY_START = {0: 1.0, 1: 0.7, 2: 0.4, 3: 0.2, 4: 0.1, 5: 0.08, 6: 0.55}     # relative chance a trip starts on this weekday

    def _fill(self, rng, rate):
        d = self.first + timedelta(2)
        last_city = None
        while d < self.last - timedelta(1):
            wd = d.weekday()
            if rng.random() >= min(0.95, rate * self.WEEKDAY_START[wd]):
                d += timedelta(1)
                continue
            if wd in (4, 5) and rng.random() < 0.6:
                name, title, nights = rng.choice([("Zakopane", "Weekend in Zakopane – hiking", 2), ("Sopot", "Weekend by the sea – Sopot", 2),
                                                  ("Giżycko", "Mazury weekend w/ friends", 2), ("Kazimierz Dolny", "Kazimierz Dolny weekend", 1)]
                                                 if 4 <= d.month <= 10 else [("Zakopane", "Weekend in Zakopane – hiking", 2)])
                city = PRIVATE[name]
                trip = Trip(d, d + timedelta(nights), "getaway", city, title, stay="Guesthouse",
                            leisure=self._getaway_leisure(d, nights, city, rng))
            else:
                city = rng.choices(CITIES, [c.weight * (0.15 if c.name == last_city else 1) for c in CITIES])[0]
                nights = rng.choices([0, 1, 2, 3], [8, 27, 33, 32])[0] if city.mode == "train" else rng.choices([1, 2, 3], [30, 35, 35])[0]
                if wd == 6:                                   # Sunday-evening departure for a Monday meeting
                    nights = max(nights, 2)
                trip = Trip(d, d + timedelta(nights), "work", city, f"{city.name} – {city.partner} {rng.choice(TOPICS)}",
                            stay=f"Hotel: {city.hotel}" if city.hotel and nights else "")
            if trip.last > self.last or self.blocked(trip.first, trip.last, 1, 1):
                d += timedelta(1)
                continue
            last_city = city.name
            self.trips.append(trip)
            d = trip.last + timedelta(2)                       # at least one full day at home

    def _getaway_leisure(self, start, nights, city, rng):
        acts = {"Zakopane": ["Hike – Kasprowy Wierch", "Thermal baths", "Krupówki + oscypek lunch"],
                "Sopot": ["Beach walk", "Sopot pier + brunch", "Bike ride along the coast"],
                "Giżycko": ["Sailing", "Barbecue by the lake", "Kayaking"],
                "Kazimierz Dolny": ["Market square + river walk", "Castle hill hike"]}[city.name]
        out = []
        for k in range(1, nights + 1):
            s = dt(start + timedelta(k), "10:30") + timedelta(minutes=rng.choice([0, 30, 60]))
            out.append((k, s, s + timedelta(hours=rng.choice([3, 4, 5])), rng.choice(acts), city.name))
        return out

    # ------------------------------------------------------------------ home life & specials
    def specials(self):
        pl, rng, y = self.pl, self.rng, self.y

        def put(day, start, end, title, cat, loc, desc="", away_ok=True):
            if self.fully_away(day) or day in self.paul_days and cat == "GUESTS-HOME":
                return
            if not self.free(day, start, end):
                return
            self.add(dt(day, start), dt(day, end), title, cat, loc, desc)

        # birthdays and parties
        put(date(y, 1, 24), "20:00", "01:30", "Tomek's birthday party", "SOCIAL-OUT", pl.label["praga"])
        put(date(y, 3, 14), "19:00", "01:00", "My birthday party @ mine", "GUESTS-HOME", self.home, "Guests: Paul, Kasia, Marta, Tomek, Ola, Bartek. Order sushi 18:30, cake from Blikle.")
        put(date(y, 4, 18), "20:00", "00:30", "Bartek's birthday", "SOCIAL-OUT", pl.label["pardon"])
        put(date(y, 6, 13), "15:00", "22:00", "Ola's birthday BBQ", "SOCIAL-OUT", pl.label["poniatowka"])
        put(date(y, 11, 21), "19:30", "23:30", "Kasia's birthday dinner", "SOCIAL-OUT", pl.label["beirut"], "Gift: ceramics workshop voucher.")
        put(date(y, 8, 1), "16:45", "18:30", "Godzina W – Warsaw Uprising remembrance", "PERSONAL", pl.label["rondo"])
        put(date(y, 12, 6), "18:30", "23:59", "Christmas board game night @ mine", "GUESTS-HOME", self.home, "Guests: Kasia, Marta, Tomek, Ola, Bartek. Secret Santa. Mulled wine.")
        put(date(y, 12, 11), "18:30", "23:59", "Flexa Christmas party", "SOCIAL-OUT", pl.label["elektrownia"])
        put(date(y, 4, 27), "09:00", "09:30", "PIT tax return – deadline 30 Apr", "PERSONAL", self.home, "e-Urząd Skarbowy.")
        # health and services, on weekday mornings/evenings drawn from a normal distribution around the plan
        def weekday_near(month, dom):
            d = date(y, month, dom) + timedelta(int(round(rng.gauss(0, 6))))
            while d.weekday() >= 5 or self.fully_away(d) or d in self.paul_days:
                d += timedelta(1)
            return d
        for month, dom in ((3, 12), (9, 15)):
            put(weekday_near(month, dom), "08:00", "08:45", "Dentist – dr Nowak", "PERSONAL", pl.label["dentist"])
        put(weekday_near(2, 17), "08:00", "08:45", "GP check-up – blood tests", "PERSONAL", pl.label["gp"], "Fasting!")
        for month in (1, 6, 10):
            put(weekday_near(month, 20), "18:30", "19:15", "Physio", "PERSONAL", pl.label["physio"])
        for month in (1, 3, 5, 7, 9, 11):
            d = date(y, month, 10) + timedelta(int(round(rng.gauss(0, 5))))
            d += timedelta((5 - d.weekday()) % 7)
            put(d, "10:00", "11:15", "Hairdresser", "PERSONAL", pl.label["hair"])
        # annual heat-pump service before the heating season
        d = date(y, 10, 6) + timedelta(int(round(rng.gauss(0, 4))))
        while d.weekday() >= 5 or self.fully_away(d) or d in self.paul_days:
            d += timedelta(1)
        self.wfh_forced.add(d)
        self.add(dt(d, "14:00"), dt(d, "15:30"), "Heat pump service visit – TermoSerwis", "CHORES", self.home, "Annual service before winter.", block=True)
        # seasonal outings
        for day, title, loc, s, e in ((date(y, 6, 20), "Wianki midsummer festival", pl.label["vistula"], "20:00", "23:30"),
                                      (date(y, 9, 20), "Marathon Warszawski – cheering", pl.label["nowyswiat"], "10:00", "12:30"),
                                      (date(y, 10, 17), "Warsaw Film Festival", pl.label["kino"], "20:00", "23:00")):
            put(day, s, e, title, "SOCIAL-OUT", loc)

    # ------------------------------------------------------------------ everyday life
    def everyday(self):
        pl, rng, hol = self.pl, self.rng, self.holidays
        last_grocery = self.first - timedelta(7)
        grocery_due = {t.last + timedelta(1) for t in self.trips if t.kind != "paulhere" and t.nights >= 3}
        day = self.first
        while day <= self.last:
            wd = day.weekday()
            is_hol = day in hol
            if self.fully_away(day):
                day += timedelta(1)
                continue
            leaves, returns = self.leave_home.get(day), self.arrive_home.get(day)
            paul = day in self.paul_days
            if wd < 5 and not is_hol:
                if (leaves and leaves.time() < time(12, 0)) or (returns and returns.time() > time(13, 0) and not leaves):
                    pass
                elif leaves or returns:
                    self.allday(day, day, "WFH (morning)" if leaves else "WFH (afternoon)", "WFH", self.home)
                else:
                    p_office = {0: 0.35, 1: 0.85, 2: 0.4, 3: 0.85, 4: 0.2}[wd]
                    office = rng.random() < p_office and not paul and day not in self.wfh_forced
                    if office:
                        self.allday(day, day, "Office", "OFFICE", pl.label["office"])
                        self.block(day, time(8, 15), time(18, 0))
                        if wd in (0, 2):
                            self.add(dt(day, "09:30"), dt(day, "09:50"), "Team stand-up", "WORK", "Microsoft Teams", "Partnerships team stand-up.", block=False)
                        for hhmm in sorted(rng.sample(["10:00", "11:00", "13:00", "14:30", "15:30"], rng.choice([1, 1, 2]))):
                            title = rng.choice(OFFICE_MEETINGS).format(q=(day.month - 1) // 3 + 1)
                            s = dt(day, hhmm)
                            self.add(s, s + timedelta(minutes=rng.choice([45, 60, 60, 90])), title, "WORK", "Room 'Wisła', 18th floor", block=False)
                        if rng.random() < 0.25:
                            self.add(dt(day, "12:30"), dt(day, "13:30"), "Lunch w/ " + rng.choice(FRIENDS), "SOCIAL-OUT", pl.label["gwardii"], block=False)
                    else:
                        self.allday(day, day, "WFH", "WFH", self.home, "Paul working from mine too." if paul and rng.random() < 0.6 else "")
                        if wd in (0, 2):
                            self.add(dt(day, "09:30"), dt(day, "09:50"), "Team stand-up", "WORK", "Microsoft Teams", block=False)
                        for hhmm in sorted(rng.sample(["10:00", "11:00", "14:00", "15:30", "16:00"], rng.choice([1, 2, 2, 3]))):
                            s = dt(day, hhmm)
                            self.add(s, s + timedelta(minutes=rng.choice([30, 60, 60])), rng.choice(WFH_MEETINGS), "WORK", "Microsoft Teams", block=False)
            in_town_evening = not leaves and (not returns or returns.time() < time(18, 0))
            if in_town_evening:
                self._evening(day, wd, paul)
            morning_free = not leaves or leaves.time() > time(12, 0)
            self._weekend(day, wd, paul, morning_free, returns, leaves)
            weekly = wd == 6 and (day - last_grocery).days > 3 and rng.random() < 0.6
            if (day in grocery_due or weekly) and not leaves and self.free(day, "18:00", "19:00"):
                self.add(dt(day, "18:00"), dt(day, "19:00"), "Grocery delivery (Frisco)", "CHORES", self.home,
                         "Fridge is empty after the trip." if day in grocery_due else "", block=False)
                last_grocery = day
            day += timedelta(1)

    def _evening(self, day, wd, paul):
        pl, rng = self.pl, self.rng
        month = day.month
        outdoor = 5 <= month <= 9
        if wd == 2 and not paul and rng.random() < 0.65 and self.free(day, "19:00", "21:00"):
            self.add(dt(day, "19:00"), dt(day, "21:00"), "Bouldering w/ " + rng.choice(["Tomek & Ola", "Ola", "Tomek", "Bartek"]), "SPORT", pl.label["gym"])
        elif wd == 0 and rng.random() < 0.3 and self.free(day, "18:30", "19:30"):
            self.add(dt(day, "18:30"), dt(day, "19:30"), "Yoga – Joga Studio", "SPORT", pl.label["yoga"])
        elif wd == 1 and not paul and rng.random() < 0.15 and self.free(day, "19:30", "21:00"):
            self.add(dt(day, "19:30"), dt(day, "21:00"), "Padel w/ " + rng.choice(FRIENDS), "SPORT", pl.label["padel"])
        elif wd == 3 and not paul and rng.random() < 0.15 and self.free(day, "18:30", "19:30"):
            self.add(dt(day, "18:30"), dt(day, "19:30"), "Swimming", "SPORT", pl.label["pool"])
        elif wd in (1, 3) and not paul and rng.random() < 0.3 and self.free(day, "19:00", "22:00"):
            place = rng.choice([pl.label[k] for k in ("koszyki", "gwardii", "beirut", "browar", "relaks", "pardon", "nolita", "studio")])
            self.add(dt(day, "19:00"), dt(day, "22:00"), f"Dinner w/ {rng.choice(FRIENDS)}", "SOCIAL-OUT", place)
        elif wd == 4 and not paul and rng.random() < 0.35 and self.free(day, "19:30", "23:00"):
            title, key = rng.choice([("Cinema w/ Ola – Kino Muranów", "kino"), ("Drinks w/ Bartek & Tomek", "pardon"),
                                     ("Concert w/ Marta – Klub Hydrozagadka", "hydro"), ("Theatre w/ Marta", "teatr"),
                                     ("Concert – Filharmonia Narodowa", "filharmonia"), ("Exhibition opening – Muzeum Narodowe", "museum")])
            self.add(dt(day, "19:30"), dt(day, "23:00"), title, "SOCIAL-OUT", pl.label[key])
        elif wd in (1, 2, 3) and not paul and rng.random() < 0.06 and self.free(day, "19:00", "22:30"):
            names = rng.sample(FRIENDS, 2)
            self.add(dt(day, "19:00"), dt(day, "22:30"), f"Dinner @ mine w/ {names[0]} & {names[1]}", "GUESTS-HOME", self.home, f"Guests: {names[0]}, {names[1]}.")
        if outdoor and wd in (2, 3) and rng.random() < 0.12 and self.free(day, "18:30", "20:30"):
            self.add(dt(day, "18:30"), dt(day, "20:30"), "Cycling along the Vistula", "SPORT", pl.label["bike"])

    def _weekend(self, day, wd, paul, morning_free, returns, leaves):
        pl, rng = self.pl, self.rng
        summer = 5 <= day.month <= 9
        if wd == 5 and morning_free and not returns and rng.random() < 0.5 and self.free(day, "09:30", "10:30"):
            self.add(dt(day, "09:30"), dt(day, "10:30"), "Run – Pole Mokotowskie", "SPORT", pl.label["run"])
        if wd == 5 and not leaves and not returns and not paul and rng.random() < 0.18 and self.free(day, "19:00", "23:30"):
            kind = rng.choice(["Board game night @ mine", "Movie night @ mine", "Dinner @ mine w/ friends", "Cooking night @ mine"])
            names = rng.sample(FRIENDS, rng.choice([2, 3, 4, 5]))
            self.add(dt(day, "19:00"), dt(day, "23:30"), kind, "GUESTS-HOME", self.home, f"Guests: {', '.join(names)}.")
        if wd == 5 and not leaves and not paul and rng.random() < 0.2 and self.free(day, "11:00", "13:00"):
            self.add(dt(day, "11:00"), dt(day, "13:00"), "Farmers' market + shopping", "CHORES", pl.label["koszyki"])
        if wd == 5 and not leaves and not paul and self.free(day, "16:00", "17:30") and rng.random() < (0.35 if summer else 0.15):
            key, title = rng.choice([("poniatowka", "Picnic + frisbee"), ("szczesliwicki", "Walk with Ola"), ("lakeside", "Bike + lake walk")] if summer
                                    else [("museum", "Exhibition – Muzeum Narodowe"), ("polin", "POLIN Museum visit"), ("zoo", "Warsaw Zoo w/ Ola")])
            self.add(dt(day, "16:00"), dt(day, "17:30"), title, "SOCIAL-OUT", pl.label[key])
        if wd == 6 and morning_free and not returns and not paul and rng.random() < 0.25 and self.free(day, "11:30", "14:00"):
            self.add(dt(day, "11:30"), dt(day, "14:00"), "Sunday brunch w/ " + " & ".join(rng.sample(FRIENDS, 2)), "SOCIAL-OUT",
                     rng.choice([pl.label["charlotte"], pl.label["relaks"], pl.label["koszyki"]]))
        if wd == 6 and not leaves and rng.random() < 0.4 and self.free(day, "20:00", "20:45"):
            self.add(dt(day, "20:00"), dt(day, "20:45"), "Call Mum", "PERSONAL", self.home, block=False)
        if wd in (5, 6) and not leaves and not returns and rng.random() < 0.2 and self.free(day, "14:00", "16:00"):
            self.add(dt(day, "14:00"), dt(day, "16:00"), rng.choice(["Cleaning the flat", "Laundry + ironing", "Meal prep for the week", "Deep-clean fridge"]), "CHORES", self.home, block=False)


def generate(cfg, places=None):
    """All calendar events of the year (a trip that starts in the previous year is included)."""
    places = places or Places(cfg)
    p = Planner(cfg, places)
    p.plan_anchors()
    p.plan_random_trips()
    for t in sorted(p.trips, key=lambda t: t.first):
        if t.kind == "paulhere":
            p.emit_paul(t)
        else:
            p.emit_trip(t)
    p.specials()
    p.everyday()
    p.stats = dict(trip_rate=round(p.trip_rate, 2), trips=sum(1 for t in p.trips if t.kind not in ("paulhere",)),
                   paul_visits=sum(1 for t in p.trips if t.kind == "paulhere"), away_planned=round(p.away_fraction(), 3),
                   nights_away=sum(1 for d in p.away_nights if p.first <= d <= p.last))
    return p.events, p.stats


def write_calendar(cfg, events):
    """One .ics per month (events grouped by start month, a trip from the previous year goes into January) + the merged year."""
    from .ics import write_ics
    out = cfg.calendar_dir
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.ics"):
        old.unlink()
    by_month = defaultdict(list)
    for e in events:
        first = max(e.first_day, date(cfg.year, 1, 1))
        if first.year == cfg.year:
            by_month[first.month].append(e)
    for m in range(1, 13):
        write_ics(out / f"{cfg.year}-{m:02d}.ics", by_month[m], cfg.tz, cfg.year)
    write_ics(cfg.full_calendar, [e for m in sorted(by_month) for e in by_month[m]], cfg.tz, cfg.year)
    return out
