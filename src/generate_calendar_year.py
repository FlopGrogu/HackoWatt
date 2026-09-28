"""Step 0 – generate Aleksandra's calendar for the 12 months before the existing one (1 Sep 2025 – 31 Aug 2026).

Writes
  aleksandra_calendar_2025-09_2026-08.ics  – only the new months
  aleksandra_calendar_full.ics             – new months + all events of aleksandra_calendar.ics (Sep–Oct 2026)
The existing aleksandra_calendar.ics is not modified.

Trips, Paul's visits, holidays and special evenings are planned by hand below (the "story" of the year);
everyday entries (office/WFH, meetings, sport, dinners, groceries, packing) are filled in by rules with a
fixed random seed, only into time that is still free. Same style as the existing calendar.

Usage: python src/generate_calendar_year.py
"""
import hashlib
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXISTING = ROOT / "aleksandra_calendar.ics"
OUT_NEW = ROOT / "aleksandra_calendar_2025-09_2026-08.ics"
OUT_FULL = ROOT / "aleksandra_calendar_full.ics"
FIRST, LAST = date(2025, 9, 1), date(2026, 8, 31)
rng = random.Random(2025)

HOME = "Home – ul. Chmielna 71, Warsaw"
OFFICE = "Warsaw Spire, pl. Europejski 1, Warsaw"
WAW = "Warsaw Chopin Airport (WAW)"
CENTRALNA = "Warszawa Centralna"
GYM = "Bouldering gym, ul. Puławska (Mokotów)"


def d(s):
    """'2025-09-08' -> date"""
    return date.fromisoformat(s)


def hm(s):
    return datetime.strptime(s, "%H:%M").time()


# =====================================================================================
# Events + busy windows
# =====================================================================================
events = []                      # dicts: start, end (datetime or date), summary, cat, location, desc, busy, rrule
busy = defaultdict(list)         # date -> [(start time, end time)] when she is NOT free for other plans
away_nights = set()              # nights (date of the evening) spent away from home
paul_days = set()                # days Paul is in Warsaw


def add(day, start, end, summary, cat, location="", desc="", block=True, end_day=None):
    """Timed event. `end` before `start` means it ends the next day."""
    s = datetime.combine(day, hm(start))
    e = datetime.combine(end_day or day, hm(end))
    if e <= s:
        e += timedelta(days=1)
    events.append(dict(start=s, end=e, summary=summary, cat=cat, location=location, desc=desc, busy=True))
    if block:
        busy[day].append((s.time(), e.time() if e.date() == day else time(23, 59)))


def allday(first, last, summary, cat, location="", desc="", busy_flag=False):
    events.append(dict(start=first, end=last + timedelta(days=1), summary=summary, cat=cat,
                       location=location, desc=desc, busy=busy_flag))


def block(day, start, end):
    busy[day].append((hm(start) if isinstance(start, str) else start, hm(end) if isinstance(end, str) else end))


def free(day, start, end):
    s, e = hm(start), hm(end)
    return all(e <= bs or s >= be for bs, be in busy[day])


def minus(t, minutes):
    return (datetime.combine(date.today(), hm(t)) - timedelta(minutes=minutes)).strftime("%H:%M")


def plus(t, minutes):
    return (datetime.combine(date.today(), hm(t)) + timedelta(minutes=minutes)).strftime("%H:%M")


# =====================================================================================
# Transport (times in Warsaw time; local arrival noted where the time zone differs)
# =====================================================================================
FLIGHTS = {  # destination: (outbound, return)  each = (code, from→to, dep, arr, note)
    "stockholm": (("LO 453", "WAW → ARN", "06:40", "08:25", ""), ("LO 454", "ARN → WAW", "19:45", "21:30", "")),
    "berlin": (("LO 381", "WAW → BER", "16:10", "17:35", ""), ("LO 388", "BER → WAW", "20:10", "21:35", "")),
    "berlin_am": (("LO 379", "WAW → BER", "06:40", "08:00", ""), ("LO 388", "BER → WAW", "20:10", "21:35", "")),
    "brussels": (("SN 2562", "WAW → BRU", "07:40", "09:55", ""), ("SN 2563", "BRU → WAW", "17:25", "19:35", "")),
    "vienna": (("LO 231", "WAW → VIE", "07:20", "08:40", ""), ("LO 232", "VIE → WAW", "18:30", "19:50", "")),
    "copenhagen": (("LO 461", "WAW → CPH", "07:05", "08:40", ""), ("LO 462", "CPH → WAW", "18:20", "19:55", "")),
    "london": (("LO 281", "WAW → LHR", "07:45", "10:25", "Lands 09:25 London time."),
               ("LO 282", "LHR → WAW", "17:10", "21:50", "Departs 16:10 London time.")),
    "essen": (("LO 403", "WAW → DUS", "07:10", "09:05", "Then train to Essen Hbf (~40 min)."),
              ("LO 404", "DUS → WAW", "18:05", "19:50", "")),
    "munich": (("LO 355", "WAW → MUC", "07:00", "08:35", ""), ("LO 356", "MUC → WAW", "18:10", "19:40", "")),
    "amsterdam": (("LO 267", "WAW → AMS", "07:15", "09:25", ""), ("LO 268", "AMS → WAW", "17:55", "19:55", "")),
    "lisbon": (("TP 1255", "WAW → LIS", "10:40", "15:20", "Lands 14:20 Lisbon time."),
               ("TP 1254", "LIS → WAW", "14:15", "20:55", "Departs 13:15 Lisbon time.")),
    "ski": (("LO 351", "WAW → MUC", "07:00", "08:35", "Shuttle to Mayrhofen booked (Four Seasons Travel, 09:30)."),
            ("LO 356", "MUC → WAW", "19:10", "20:40", "Shuttle from Mayrhofen 14:00.")),
}
TRAINS = {  # destination: (outbound, return) each = (train, from→to, dep, arr)
    "krakow": (("EIP 1301", "Warszawa → Kraków", "06:15", "08:40"), ("EIP 1306", "Kraków → Warszawa", "19:55", "22:20")),
    "gdansk": (("EIP 5101", "Warszawa → Gdańsk", "07:05", "09:45"), ("EIP 5106", "Gdańsk → Warszawa", "17:15", "19:55")),
    "lodz": (("IC 18102", "Warszawa → Łódź Fabryczna", "09:20", "10:45"), ("IC 18107", "Łódź Fabryczna → Warszawa", "17:10", "18:35")),
    "sopot": (("EIP 5103", "Warszawa → Sopot", "09:05", "11:55"), ("EIP 5110", "Sopot → Warszawa", "16:05", "19:00")),
    "zakopane": (("IC 31100 'Tatry'", "Warszawa → Zakopane", "07:00", "13:05"), ("IC 13101 'Tatry'", "Zakopane → Warszawa", "13:30", "19:50")),
    "berlin": (("EC 47", "Warszawa → Berlin Hbf", "14:50", "20:35"), ("EC 46", "Berlin Hbf → Warszawa", "13:37", "19:25")),
}

# =====================================================================================
# The year's plan: trips (hand-written)
# =====================================================================================
# kind: work/private · via: flights/trains key or "car" · meetings: (day offset, start, end, title, location)
TRIPS = [
    # --- 2025 ---
    dict(first="2025-09-08", last="2025-09-10", title="Stockholm – Nordvolt kickoff", kind="work", via=("flight", "stockholm"),
         place="Stockholm, Sweden", stay="Hotel: Scandic Continental, Vasagatan 22",
         meetings=[(0, "10:30", "17:00", "Nordvolt × Flexa – partnership kickoff", "Nordvolt HQ, Kungsbron 1, Stockholm"),
                   (1, "09:00", "16:00", "Nordvolt – data sharing workshop", "Nordvolt HQ, Stockholm"),
                   (2, "09:00", "13:00", "Nordvolt – next steps", "Nordvolt HQ, Stockholm")]),
    dict(first="2025-09-18", last="2025-09-18", title="Kraków day trip – KrakGrid", kind="work", via=("train", "krakow"),
         place="Kraków", meetings=[(0, "10:00", "15:30", "KrakGrid – smart-meter data kickoff", "KrakGrid office, ul. Lubicz 23, Kraków")]),
    dict(first="2025-09-22", last="2025-09-24", title="Gdańsk – Port of Gdańsk scoping", kind="work", via=("train", "gdansk"),
         place="Gdańsk", stay="Hotel: PURO Gdańsk Stare Miasto",
         meetings=[(0, "11:00", "17:00", "Port of Gdańsk – energy team intro", "Port of Gdańsk, ul. Zamknięta 18"),
                   (1, "09:00", "16:00", "Site visits – quays & substation", "Port of Gdańsk"),
                   (2, "09:00", "12:30", "Workshop – electrification roadmap", "Port of Gdańsk")]),
    dict(first="2025-09-25", last="2025-09-28", title="Berlin – long weekend with Paul", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "13:00", "Work from Paul's (half day)", "Prenzlauer Berg, Berlin"),
                   (2, "15:00", "18:00", "Tempelhofer Feld – bikes w/ Paul", "Tempelhofer Feld, Berlin")]),
    dict(first="2025-10-06", last="2025-10-09", title="Brussels – DSO flexibility meetings", kind="work", via=("flight", "brussels"),
         place="Brussels, Belgium", stay="Hotel: Thon Hotel EU, Rue de la Loi 75",
         meetings=[(0, "13:00", "18:00", "Meeting – DG ENER flexibility unit", "Berlaymont area, Brussels"),
                   (1, "09:00", "17:00", "Workshop – DSO flexibility markets", "The Square, Brussels"),
                   (2, "09:30", "16:30", "Partner meetings", "Rue de la Loi, Brussels"),
                   (3, "09:00", "13:00", "Wrap-up with Brussels team", "Flexa Brussels office")]),
    dict(first="2025-10-15", last="2025-10-15", title="Kraków day trip – KrakGrid", kind="work", via=("train", "krakow"),
         place="Kraków", meetings=[(0, "10:00", "16:00", "KrakGrid – pilot data review", "KrakGrid office, Kraków")]),
    dict(first="2025-10-20", last="2025-10-22", title="Vienna – DonauNetz workshop", kind="work", via=("flight", "vienna"),
         place="Vienna, Austria", stay="Hotel: Motel One Wien-Staatsoper",
         meetings=[(0, "10:30", "17:30", "DonauNetz – flexibility tender workshop", "DonauNetz, Erdberg, Vienna"),
                   (1, "09:00", "16:00", "DonauNetz – pilot design", "DonauNetz, Vienna"),
                   (2, "09:00", "15:00", "DonauNetz – contract draft review", "DonauNetz, Vienna")]),
    dict(first="2025-10-24", last="2025-10-26", title="Berlin – weekend with Paul", kind="private", via=("train", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "11:00", "14:00", "Flohmarkt Mauerpark w/ Paul", "Mauerpark, Berlin"),
                   (1, "20:00", "23:30", "Dinner w/ Paul's friends", "Neukölln, Berlin")]),
    dict(first="2025-10-31", last="2025-11-02", title="All Saints – Mum & Dad in Łódź", kind="private", via=("train", "lodz"),
         place="Łódź", desc="Cemetery visits on 1 Nov with Mum & Dad.",
         meetings=[(1, "10:00", "14:00", "All Saints – cemetery (Grandma & Grandpa)", "Stary Cmentarz, Łódź")]),
    dict(first="2025-11-04", last="2025-11-06", title="Gdańsk – Port electrification study", kind="work", via=("train", "gdansk"),
         place="Gdańsk", stay="Hotel: PURO Gdańsk Stare Miasto",
         meetings=[(0, "11:00", "17:00", "Port of Gdańsk – feasibility study kickoff", "Port of Gdańsk, ul. Zamknięta 18"),
                   (1, "09:00", "16:30", "Port of Gdańsk – load measurements", "Port of Gdańsk"),
                   (2, "09:00", "12:00", "Port of Gdańsk – steering group", "Port of Gdańsk")]),
    dict(first="2025-11-16", last="2025-11-20", title="Copenhagen – Kraftly partner week", kind="work", via=("flight", "copenhagen"),
         place="Copenhagen, Denmark", stay="Hotel: Absalon Hotel, Helgolandsgade 15",
         meetings=[(1, "09:00", "17:00", "Kraftly – demand response platform deep-dive", "Kraftly, Nordhavn, Copenhagen"),
                   (2, "09:00", "17:00", "Kraftly – integration workshop", "Kraftly, Copenhagen"),
                   (3, "09:00", "16:00", "Kraftly – commercial terms", "Kraftly, Copenhagen"),
                   (4, "09:00", "13:00", "Kraftly – wrap-up", "Kraftly, Copenhagen")], out_day_offset=0,
         desc="Flying out Sunday evening.", out_override=("LO 463", "WAW → CPH", "18:30", "20:05", "")),
    dict(first="2025-11-27", last="2025-11-30", title="Berlin – Christmas markets with Paul", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "14:00", "Work from Paul's", "Prenzlauer Berg, Berlin"),
                   (2, "17:00", "21:00", "Christmas market Gendarmenmarkt w/ Paul", "Gendarmenmarkt, Berlin")]),
    dict(first="2025-12-02", last="2025-12-04", title="London – GridMint partnership", kind="work", via=("flight", "london"),
         place="London, UK", stay="Hotel: The Hoxton, Shoreditch",
         meetings=[(0, "12:30", "18:00", "GridMint – partnership review", "GridMint, Old Street, London"),
                   (1, "09:30", "17:00", "GridMint – product roadmap day", "GridMint, London"),
                   (2, "09:30", "13:00", "GridMint – investor call prep", "GridMint, London")]),
    dict(first="2025-12-23", last="2025-12-27", title="Christmas – Mum & Dad in Łódź", kind="private", via=("train", "lodz"),
         place="Łódź", desc="Christmas Eve dinner at Mum & Dad's. Presents in the blue bag!",
         meetings=[(1, "17:00", "23:00", "Wigilia – Christmas Eve dinner", "Mum & Dad's, Łódź"),
                   (2, "13:00", "18:00", "Christmas lunch – Aunt Basia", "Łódź")]),
    dict(first="2025-12-30", last="2026-01-02", title="New Year in Berlin with Paul", kind="private", via=("flight", "berlin_am"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "20:00", "02:00", "New Year's Eve party – Paul's friends", "Friedrichshain, Berlin")]),
    # --- 2026 ---
    dict(first="2026-01-12", last="2026-01-15", title="Stockholm – Nordvolt pilot design", kind="work", via=("flight", "stockholm"),
         place="Stockholm, Sweden", stay="Hotel: Scandic Continental, Vasagatan 22",
         meetings=[(0, "10:30", "17:00", "Nordvolt – pilot design sprint", "Nordvolt HQ, Stockholm"),
                   (1, "09:00", "17:00", "Nordvolt – pilot design sprint", "Nordvolt HQ, Stockholm"),
                   (2, "09:00", "16:00", "Nordvolt – customer interviews", "Nordvolt HQ, Stockholm"),
                   (3, "09:00", "13:00", "Nordvolt – sprint review", "Nordvolt HQ, Stockholm")]),
    dict(first="2026-01-21", last="2026-01-22", title="Kraków – KrakGrid tariff workshop", kind="work", via=("train", "krakow"),
         place="Kraków", stay="Hotel: Puro Kraków Kazimierz",
         meetings=[(0, "10:00", "17:00", "KrakGrid – dynamic tariff workshop", "KrakGrid office, Kraków"),
                   (1, "09:00", "15:00", "KrakGrid – pilot households selection", "KrakGrid office, Kraków")]),
    dict(first="2026-01-29", last="2026-02-01", title="Berlin – long weekend with Paul", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "14:00", "Work from Paul's", "Prenzlauer Berg, Berlin"),
                   (2, "19:30", "22:30", "Philharmonie concert w/ Paul", "Berliner Philharmonie")]),
    dict(first="2026-02-04", last="2026-02-04", title="Kraków day trip – KrakGrid", kind="work", via=("train", "krakow"),
         place="Kraków", meetings=[(0, "10:00", "15:30", "KrakGrid – pilot go/no-go", "KrakGrid office, Kraków")]),
    dict(first="2026-02-09", last="2026-02-12", title="Essen – E-world energy & water", kind="work", via=("flight", "essen"),
         place="Essen, Germany", stay="Hotel: Mintrops Stadt Hotel Margarethenhöhe",
         meetings=[(1, "09:00", "18:00", "E-world – booth duty + partner meetings", "Messe Essen"),
                   (2, "09:00", "18:00", "E-world – panel 'Flexible households' 14:00", "Messe Essen, Hall 3"),
                   (3, "09:00", "14:00", "E-world – last meetings", "Messe Essen")],
         out_day_offset=0),
    dict(first="2026-02-21", last="2026-02-28", title="Ski week – Mayrhofen (Zillertal)", kind="private", via=("flight", "ski"),
         place="Mayrhofen, Austria", stay="Chalet with Kasia, Tomek & Ola",
         desc="Ski pass booked. Take ski helmet + goggles.",
         meetings=[(k, "09:30", "16:00", "Skiing – Penken / Ahorn", "Mayrhofen") for k in range(1, 7)]),
    dict(first="2026-03-03", last="2026-03-05", title="Brussels – Flexibility regulation roundtable", kind="work", via=("flight", "brussels"),
         place="Brussels, Belgium", stay="Hotel: Thon Hotel EU, Rue de la Loi 75",
         meetings=[(0, "13:00", "18:00", "Roundtable – network code on demand response", "The Square, Brussels"),
                   (1, "09:00", "17:00", "Partner meetings", "Rue de la Loi, Brussels"),
                   (2, "09:00", "13:00", "Brussels team – Q2 planning", "Flexa Brussels office")]),
    dict(first="2026-03-10", last="2026-03-11", title="Kraków – KrakGrid pilot launch", kind="work", via=("train", "krakow"),
         place="Kraków", stay="Hotel: Puro Kraków Kazimierz",
         meetings=[(0, "10:00", "17:00", "KrakGrid – installer training", "KrakGrid office, Kraków"),
                   (1, "09:00", "16:00", "KrakGrid – pilot launch", "KrakGrid office, Kraków")]),
    dict(first="2026-03-18", last="2026-03-20", title="Munich – Isarwatt workshop", kind="work", via=("flight", "munich"),
         place="Munich, Germany", stay="Hotel: Motel One München-Sendlinger Tor",
         meetings=[(0, "10:30", "17:30", "Isarwatt – heat pump fleet integration", "Isarwatt, Werksviertel, Munich"),
                   (1, "09:00", "17:00", "Isarwatt – API workshop", "Isarwatt, Munich"),
                   (2, "09:00", "14:00", "Isarwatt – commercial alignment", "Isarwatt, Munich")]),
    dict(first="2026-03-26", last="2026-03-29", title="Berlin – long weekend with Paul", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "14:00", "Work from Paul's", "Prenzlauer Berg, Berlin"),
                   (2, "12:00", "16:00", "Potsdam day w/ Paul", "Potsdam")]),
    dict(first="2026-04-03", last="2026-04-06", title="Easter – Mum & Dad in Łódź", kind="private", via=("train", "lodz"),
         place="Łódź", desc="Paul joins on Saturday. Bring the mazurek from Blikle.",
         meetings=[(1, "10:00", "12:00", "Święconka – blessing of the Easter basket", "Łódź"),
                   (2, "10:00", "15:00", "Easter breakfast at Mum & Dad's", "Mum & Dad's, Łódź")]),
    dict(first="2026-04-13", last="2026-04-16", title="Amsterdam – Polderstroom partnership", kind="work", via=("flight", "amsterdam"),
         place="Amsterdam, Netherlands", stay="Hotel: Hotel V Nesplein",
         meetings=[(0, "13:00", "18:00", "Polderstroom – intro & site tour", "Polderstroom, NDSM, Amsterdam"),
                   (1, "09:00", "17:00", "Polderstroom – aggregation platform workshop", "Polderstroom, Amsterdam"),
                   (2, "09:00", "17:00", "Polderstroom – joint offer draft", "Polderstroom, Amsterdam"),
                   (3, "09:00", "13:00", "Polderstroom – wrap-up", "Polderstroom, Amsterdam")]),
    dict(first="2026-04-29", last="2026-04-29", title="Kraków day trip – KrakGrid", kind="work", via=("train", "krakow"),
         place="Kraków", meetings=[(0, "10:00", "15:30", "KrakGrid – first pilot results", "KrakGrid office, Kraków")]),
    dict(first="2026-04-30", last="2026-05-03", title="Majówka – Tatra hiking with Paul", kind="private", via=("train", "zakopane"),
         place="Zakopane", stay="Pensjonat Pod Giewontem, ul. Kasprusie",
         meetings=[(1, "08:00", "17:00", "Hike – Dolina Kościeliska & Ornak", "Tatra National Park"),
                   (2, "07:30", "17:30", "Hike – Kasprowy Wierch → Hala Gąsienicowa", "Tatra National Park")]),
    dict(first="2026-05-11", last="2026-05-14", title="Stockholm – Nordvolt pilot review", kind="work", via=("flight", "stockholm"),
         place="Stockholm, Sweden", stay="Hotel: Scandic Continental, Vasagatan 22",
         meetings=[(0, "10:30", "17:00", "Nordvolt – winter pilot results", "Nordvolt HQ, Stockholm"),
                   (1, "09:00", "17:00", "Nordvolt – scale-up planning", "Nordvolt HQ, Stockholm"),
                   (2, "09:00", "16:00", "Nordvolt – board presentation prep", "Nordvolt HQ, Stockholm"),
                   (3, "09:00", "13:00", "Nordvolt – steering committee", "Nordvolt HQ, Stockholm")]),
    dict(first="2026-05-15", last="2026-05-17", title="Berlin – weekend with Paul", kind="private", via=("train", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "14:00", "18:00", "Kayaking on the Spree w/ Paul", "Treptower Park, Berlin")]),
    dict(first="2026-05-21", last="2026-05-22", title="Kraków – KrakGrid pilot review", kind="work", via=("train", "krakow"),
         place="Kraków", stay="Hotel: Puro Kraków Kazimierz",
         meetings=[(0, "10:00", "17:00", "KrakGrid – pilot review", "KrakGrid office, Kraków"),
                   (1, "09:00", "14:00", "KrakGrid – rollout plan", "KrakGrid office, Kraków")]),
    dict(first="2026-06-04", last="2026-06-07", title="Boże Ciało long weekend – Sopot with friends", kind="private", via=("train", "sopot"),
         place="Sopot", stay="Apartment by the pier with Kasia, Marta & Ola",
         meetings=[(1, "11:00", "17:00", "Beach + Molo w/ the girls", "Sopot beach"),
                   (2, "10:00", "15:00", "Bike ride Sopot → Gdynia", "Sopot")]),
    dict(first="2026-06-08", last="2026-06-11", title="Brussels – EU Energy Week", kind="work", via=("flight", "brussels"),
         place="Brussels, Belgium", stay="Hotel: Thon Hotel EU, Rue de la Loi 75",
         meetings=[(0, "13:00", "18:00", "EU Energy Week – opening + policy sessions", "The Square, Brussels"),
                   (1, "09:00", "17:30", "EU Energy Week – my panel 11:00", "The Square, Brussels"),
                   (2, "09:00", "17:00", "Partner meetings", "Rue de la Loi, Brussels"),
                   (3, "09:00", "13:00", "Brussels team – H2 planning", "Flexa Brussels office")]),
    dict(first="2026-06-16", last="2026-06-17", title="Kraków – KrakGrid contract extension", kind="work", via=("train", "krakow"),
         place="Kraków", stay="Hotel: Puro Kraków Kazimierz",
         meetings=[(0, "10:00", "17:00", "KrakGrid – year-one review", "KrakGrid office, Kraków"),
                   (1, "09:00", "15:00", "KrakGrid – contract extension", "KrakGrid office, Kraków")]),
    dict(first="2026-06-25", last="2026-06-28", title="Berlin – Paul's birthday", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "14:00", "Work from Paul's", "Prenzlauer Berg, Berlin"),
                   (2, "19:00", "01:00", "Paul's birthday party", "Prenzlauer Berg, Berlin")]),
    dict(first="2026-07-07", last="2026-07-08", title="Gdańsk – Port pilot go-live", kind="work", via=("train", "gdansk"),
         place="Gdańsk", stay="Hotel: PURO Gdańsk Stare Miasto",
         meetings=[(0, "11:00", "17:00", "Port of Gdańsk – pilot go-live", "Port of Gdańsk"),
                   (1, "09:00", "15:00", "Port of Gdańsk – operations handover", "Port of Gdańsk")]),
    dict(first="2026-07-17", last="2026-07-26", title="Holiday – Lisbon & Algarve with Paul", kind="private", via=("flight", "lisbon"),
         place="Portugal", desc="OOO 17–26 Jul. Lisbon 17–21 Jul (Alfama apartment), then Lagos 21–26 Jul (car rental).",
         meetings=[(4, "10:00", "14:00", "Drive Lisbon → Lagos (rental car)", "A2 motorway")]),
    dict(first="2026-07-29", last="2026-07-29", title="Kraków day trip – KrakGrid", kind="work", via=("train", "krakow"),
         place="Kraków", meetings=[(0, "10:00", "15:30", "KrakGrid – summer peak review", "KrakGrid office, Kraków")]),
    dict(first="2026-08-05", last="2026-08-07", title="Vienna – DonauNetz pilot kickoff", kind="work", via=("flight", "vienna"),
         place="Vienna, Austria", stay="Hotel: Motel One Wien-Staatsoper",
         meetings=[(0, "10:30", "17:30", "DonauNetz – pilot kickoff", "DonauNetz, Vienna"),
                   (1, "09:00", "16:30", "DonauNetz – field visit Burgenland", "Burgenland"),
                   (2, "09:00", "15:00", "DonauNetz – next steps", "DonauNetz, Vienna")]),
    dict(first="2026-08-14", last="2026-08-16", title="15 Aug weekend – Mazury sailing", kind="private", via=("car", "Bartek"),
         place="Giżycko, Mazury", stay="Sailing boat from Giżycko marina with Bartek, Tomek & Kasia",
         meetings=[(1, "09:00", "18:00", "Sailing – Niegocin → Mikołajki", "Mazury lakes")]),
    dict(first="2026-08-20", last="2026-08-23", title="Berlin – long weekend with Paul", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "14:00", "Work from Paul's", "Prenzlauer Berg, Berlin"),
                   (2, "15:00", "20:00", "Wannsee beach w/ Paul", "Strandbad Wannsee, Berlin")]),
    # --- additional trips (so that roughly a third of all nights are away, like Sep–Oct 2026) ---
    dict(first="2025-09-30", last="2025-10-02", title="Amsterdam – Polderstroom first meeting", kind="work", via=("flight", "amsterdam"),
         place="Amsterdam, Netherlands", stay="Hotel: Hotel V Nesplein",
         meetings=[(0, "13:00", "18:00", "Polderstroom – first meeting", "Polderstroom, NDSM, Amsterdam"),
                   (1, "09:00", "17:00", "Polderstroom – platform demo", "Polderstroom, Amsterdam"),
                   (2, "09:00", "13:00", "Polderstroom – next steps", "Polderstroom, Amsterdam")]),
    dict(first="2025-10-10", last="2025-10-12", title="Weekend at Mum & Dad's – Łódź", kind="private", via=("train", "lodz"),
         place="Łódź", desc="Dad's name day on Saturday.",
         meetings=[(1, "13:00", "17:00", "Dad's name day lunch", "Mum & Dad's, Łódź")]),
    dict(first="2025-12-08", last="2025-12-10", title="Stockholm – Nordvolt year-end review", kind="work", via=("flight", "stockholm"),
         place="Stockholm, Sweden", stay="Hotel: Scandic Continental, Vasagatan 22",
         meetings=[(0, "10:30", "17:00", "Nordvolt – year-end review", "Nordvolt HQ, Stockholm"),
                   (1, "09:00", "16:00", "Nordvolt – 2026 roadmap", "Nordvolt HQ, Stockholm"),
                   (1, "18:00", "22:00", "Nordvolt julbord (Christmas dinner)", "Östermalm, Stockholm"),
                   (2, "09:00", "13:00", "Nordvolt – contract renewal", "Nordvolt HQ, Stockholm")]),
    dict(first="2026-01-08", last="2026-01-11", title="Berlin – long weekend with Paul", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "14:00", "Work from Paul's", "Prenzlauer Berg, Berlin"),
                   (2, "11:00", "15:00", "Museum Island w/ Paul", "Museumsinsel, Berlin")]),
    dict(first="2026-02-18", last="2026-02-19", title="Gdańsk – Port winter load review", kind="work", via=("train", "gdansk"),
         place="Gdańsk", stay="Hotel: PURO Gdańsk Stare Miasto",
         meetings=[(0, "11:00", "17:00", "Port of Gdańsk – winter load review", "Port of Gdańsk"),
                   (1, "09:00", "15:00", "Port of Gdańsk – pilot scope", "Port of Gdańsk")]),
    dict(first="2026-03-23", last="2026-03-25", title="Copenhagen – Kraftly integration", kind="work", via=("flight", "copenhagen"),
         place="Copenhagen, Denmark", stay="Hotel: Absalon Hotel, Helgolandsgade 15",
         meetings=[(0, "10:30", "17:00", "Kraftly – integration testing", "Kraftly, Nordhavn, Copenhagen"),
                   (1, "09:00", "17:00", "Kraftly – joint customer workshop", "Kraftly, Copenhagen"),
                   (2, "09:00", "14:00", "Kraftly – go-live plan", "Kraftly, Copenhagen")]),
    dict(first="2026-04-20", last="2026-04-22", title="London – GridMint quarterly", kind="work", via=("flight", "london"),
         place="London, UK", stay="Hotel: The Hoxton, Shoreditch",
         meetings=[(0, "12:30", "18:00", "GridMint – quarterly business review", "GridMint, Old Street, London"),
                   (1, "09:30", "17:00", "GridMint – UK market workshop", "GridMint, London"),
                   (2, "09:30", "13:00", "GridMint – wrap-up", "GridMint, London")]),
    dict(first="2026-05-05", last="2026-05-07", title="Vienna – DonauNetz tender award", kind="work", via=("flight", "vienna"),
         place="Vienna, Austria", stay="Hotel: Motel One Wien-Staatsoper",
         meetings=[(0, "10:30", "17:30", "DonauNetz – tender award meeting", "DonauNetz, Vienna"),
                   (1, "09:00", "16:30", "DonauNetz – pilot planning", "DonauNetz, Vienna"),
                   (2, "09:00", "15:00", "DonauNetz – legal", "DonauNetz, Vienna")]),
    dict(first="2026-05-25", last="2026-05-27", title="Munich – Isarwatt go-live", kind="work", via=("flight", "munich"),
         place="Munich, Germany", stay="Hotel: Motel One München-Sendlinger Tor",
         meetings=[(0, "10:30", "17:30", "Isarwatt – go-live preparation", "Isarwatt, Werksviertel, Munich"),
                   (1, "09:00", "17:00", "Isarwatt – go-live", "Isarwatt, Munich"),
                   (2, "09:00", "14:00", "Isarwatt – hypercare", "Isarwatt, Munich")]),
    dict(first="2026-07-01", last="2026-07-02", title="Brussels – Flexa board meeting", kind="work", via=("flight", "brussels"),
         place="Brussels, Belgium", stay="Hotel: Thon Hotel EU, Rue de la Loi 75",
         meetings=[(0, "13:00", "18:00", "Board meeting – H1 results", "Flexa Brussels office"),
                   (1, "09:00", "13:00", "Brussels team – partnerships sync", "Flexa Brussels office")]),
    dict(first="2026-07-09", last="2026-07-12", title="Berlin – long weekend with Paul", kind="private", via=("flight", "berlin"),
         place="Paul's flat, Prenzlauer Berg, Berlin", stay="Staying at Paul's",
         meetings=[(1, "09:00", "14:00", "Work from Paul's", "Prenzlauer Berg, Berlin"),
                   (2, "14:00", "19:00", "Lake Schlachtensee w/ Paul", "Schlachtensee, Berlin")]),
    dict(first="2026-08-10", last="2026-08-12", title="Stockholm – Nordvolt summer check-in", kind="work", via=("flight", "stockholm"),
         place="Stockholm, Sweden", stay="Hotel: Scandic Continental, Vasagatan 22",
         meetings=[(0, "10:30", "17:00", "Nordvolt – summer check-in", "Nordvolt HQ, Stockholm"),
                   (1, "09:00", "16:00", "Nordvolt – autumn pilot plan", "Nordvolt HQ, Stockholm"),
                   (2, "09:00", "13:00", "Nordvolt – steering committee", "Nordvolt HQ, Stockholm")]),
]

# Paul in Warsaw: (first, last, arrival (day, what, time, where), departure (day, what, time, where), plans)
PAUL = [
    ("2025-09-12", "2025-09-14", ("2025-09-12", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2025-09-14", "Paul's flight LO 381 (16:10)", "14:30", HOME),
     [("2025-09-13", "11:30", "14:00", "Brunch w/ Paul – Charlotte", "SOCIAL-OUT", "Charlotte, pl. Zbawiciela", True)]),
    ("2025-10-17", "2025-10-19", ("2025-10-17", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2025-10-19", "Paul's train back – EC 44 (12:25)", "12:00", CENTRALNA),
     [("2025-10-18", "20:00", "23:00", "Warsaw Film Festival w/ Paul – Kino Muranów", "SOCIAL-OUT", "Kino Muranów", True)]),
    ("2025-11-08", "2025-11-10", ("2025-11-08", "Pick up Paul – EC 45 from Berlin", "15:25", CENTRALNA),
     ("2025-11-10", "Paul's flight LO 379 (07:15)", "05:45", HOME),
     [("2025-11-08", "19:30", "22:30", "Dinner at home w/ Paul", "PAUL", HOME, False)]),
    ("2025-11-24", "2025-11-26", ("2025-11-24", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2025-11-26", "Paul's flight LO 381 (16:10)", "14:30", HOME),
     [("2025-11-25", "19:00", "22:30", "Dinner @ mine w/ Kasia & Tomek (+Paul)", "GUESTS-HOME", HOME, False)]),
    ("2025-12-12", "2025-12-14", ("2025-12-12", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2025-12-14", "Paul's train back – EC 44 (12:25)", "12:00", CENTRALNA),
     [("2025-12-13", "15:00", "19:00", "Christmas market Old Town w/ Paul", "SOCIAL-OUT", "Rynek Starego Miasta", True)]),
    ("2026-01-16", "2026-01-18", ("2026-01-16", "Pick up Paul – EC 45 from Berlin", "15:25", CENTRALNA),
     ("2026-01-18", "Paul's flight LO 381 (16:10)", "14:30", HOME),
     [("2026-01-17", "19:30", "22:30", "Cooking night w/ Paul – bigos", "PAUL", HOME, False)]),
    ("2026-02-13", "2026-02-15", ("2026-02-13", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2026-02-15", "Paul's train back – EC 44 (12:25)", "12:00", CENTRALNA),
     [("2026-02-14", "19:30", "22:30", "Valentine's dinner w/ Paul – Nolita", "SOCIAL-OUT", "Nolita, ul. Wilcza 46", True)]),
    ("2026-03-13", "2026-03-15", ("2026-03-13", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2026-03-15", "Paul's flight LO 381 (16:10)", "14:30", HOME), []),
    ("2026-04-24", "2026-04-26", ("2026-04-24", "Pick up Paul – EC 45 from Berlin", "15:25", CENTRALNA),
     ("2026-04-26", "Paul's flight LO 381 (16:10)", "14:30", HOME),
     [("2026-04-25", "10:30", "13:00", "Łazienki park walk w/ Paul", "SPORT", "Łazienki Park", True)]),
    ("2026-05-29", "2026-05-31", ("2026-05-29", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2026-05-31", "Paul's train back – EC 44 (12:25)", "12:00", CENTRALNA),
     [("2026-05-30", "19:00", "22:30", "Dinner @ mine w/ Marta & Bartek (+Paul)", "GUESTS-HOME", HOME, False)]),
    ("2026-06-19", "2026-06-21", ("2026-06-19", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2026-06-21", "Paul's flight LO 381 (16:10)", "14:30", HOME),
     [("2026-06-20", "20:00", "23:30", "Wianki midsummer festival w/ Paul", "SOCIAL-OUT", "Vistula boulevards", True)]),
    ("2026-07-03", "2026-07-05", ("2026-07-03", "Pick up Paul – EC 45 from Berlin", "15:25", CENTRALNA),
     ("2026-07-05", "Paul's flight LO 381 (16:10)", "14:30", HOME),
     [("2026-07-04", "12:00", "17:00", "Vistula beach w/ Paul", "SOCIAL-OUT", "Plaża Poniatówka", True)]),
    ("2026-07-14", "2026-07-16", ("2026-07-14", "Paul lands – LO 386 from BER", "19:40", WAW),
     ("2026-07-16", "Paul's flight LO 379 (07:15)", "05:45", HOME),
     [("2026-07-15", "19:00", "22:30", "Dinner at home w/ Paul – planning Portugal", "PAUL", HOME, False)]),
    ("2026-08-08", "2026-08-09", ("2026-08-08", "Paul lands – LO 380 from BER", "12:30", WAW),
     ("2026-08-09", "Paul's flight LO 381 (16:10)", "14:30", HOME),
     [("2026-08-08", "19:30", "22:30", "Dinner at home w/ Paul", "PAUL", HOME, False)]),
]

HOLIDAYS = {  # Polish public holidays (days off)
    "2025-11-01": "All Saints' Day", "2025-11-11": "Independence Day", "2025-12-24": "Christmas Eve (day off)",
    "2025-12-25": "Christmas Day", "2025-12-26": "Second Day of Christmas", "2026-01-01": "New Year's Day",
    "2026-01-06": "Epiphany", "2026-04-05": "Easter Sunday", "2026-04-06": "Easter Monday", "2026-05-01": "Labour Day",
    "2026-05-03": "Constitution Day", "2026-06-04": "Corpus Christi", "2026-08-15": "Assumption Day",
}

# Special evenings/days at home or in town (day, start, end, summary, category, location, description, away?)
SPECIAL = [
    ("2025-09-20", "11:30", "14:00", "Brunch w/ Kasia & Marta", "SOCIAL-OUT", "Charlotte, pl. Zbawiciela", "", True),
    ("2025-10-04", "19:00", "23:30", "Board game night @ mine", "GUESTS-HOME", HOME, "Kasia, Marta, Tomek, Ola, Bartek. Making chili.", False),
    ("2025-10-13", "14:00", "15:30", "Heat pump service visit – TermoSerwis", "CHORES", HOME, "Annual service before winter.", False),
    ("2025-11-13", "08:00", "08:45", "Dentist – dr Nowak", "PERSONAL", "Dental clinic, ul. Hoża 42", "", True),
    ("2025-11-14", "19:00", "21:30", "Concert – Filharmonia Narodowa w/ Bartek", "SOCIAL-OUT", "Filharmonia Narodowa, ul. Jasna 5", "", True),
    ("2025-11-21", "19:30", "23:30", "Kasia's birthday dinner", "SOCIAL-OUT", "Beirut Hummus & Music Bar, ul. Poznańska 12", "Gift: ceramics workshop voucher.", True),
    ("2025-12-06", "18:30", "23:59", "Christmas board game night @ mine", "GUESTS-HOME", HOME, "Kasia, Marta, Tomek, Ola, Bartek. Secret Santa (limit 50 zł). Mulled wine.", False),
    ("2025-12-11", "18:30", "23:59", "Flexa Christmas party", "SOCIAL-OUT", "Elektrownia Powiśle, ul. Dobra 42", "", True),
    ("2025-12-20", "15:00", "19:00", "Christmas shopping + mulled wine w/ Ola", "SOCIAL-OUT", "Nowy Świat", "", True),
    ("2026-01-03", "19:00", "23:30", "Board game night @ mine", "GUESTS-HOME", HOME, "Tomek brings Brass: Birmingham.", False),
    ("2026-01-24", "20:00", "01:30", "Tomek's birthday party", "SOCIAL-OUT", "Tomek's flat, Praga", "", True),
    ("2026-01-27", "18:30", "19:15", "Physio", "PERSONAL", "Physio clinic, ul. Mokotowska 49", "", True),
    ("2026-02-17", "08:00", "08:45", "GP check-up – blood tests", "PERSONAL", "LuxMed, ul. Chmielna 85", "Fasting!", True),
    ("2026-03-01", "11:30", "14:00", "Sunday brunch – Kasia, Marta, Tomek", "SOCIAL-OUT", "Charlotte, pl. Zbawiciela", "", True),
    ("2026-03-14", "19:00", "01:00", "My birthday party @ mine", "GUESTS-HOME", HOME, "Paul + Kasia, Marta, Tomek, Ola, Bartek. Order sushi 18:30, cake from Blikle.", False),
    ("2026-03-21", "19:00", "22:00", "Theatre w/ Marta – Teatr Polski", "SOCIAL-OUT", "Teatr Polski, ul. Karasia 2", "", True),
    ("2026-04-11", "19:00", "23:30", "Board game night @ mine", "GUESTS-HOME", HOME, "Kasia, Tomek, Ola, Bartek.", False),
    ("2026-04-18", "20:00", "00:30", "Bartek's birthday", "SOCIAL-OUT", "Pardon, To Tu, pl. Grzybowski", "", True),
    ("2026-04-27", None, None, "PIT tax return – deadline 30 Apr", "PERSONAL", "", "e-Urząd Skarbowy.", False),
    ("2026-05-09", "12:00", "17:00", "Picnic w/ friends – Pole Mokotowskie", "SOCIAL-OUT", "Pole Mokotowskie", "Bring blanket + frisbee.", True),
    ("2026-05-19", "08:00", "08:45", "Dentist – dr Nowak", "PERSONAL", "Dental clinic, ul. Hoża 42", "", True),
    ("2026-05-23", "19:00", "23:00", "Dinner @ mine w/ Kasia & Tomek", "GUESTS-HOME", HOME, "Asparagus risotto.", False),
    ("2026-06-02", "18:30", "19:15", "Physio", "PERSONAL", "Physio clinic, ul. Mokotowska 49", "", True),
    ("2026-06-13", "15:00", "22:00", "Ola's birthday BBQ", "SOCIAL-OUT", "Plaża Poniatówka", "", True),
    ("2026-07-28", "21:00", "23:30", "Open-air cinema w/ Ola", "SOCIAL-OUT", "Park Szczęśliwicki", "", True),
    ("2026-08-01", "16:45", "18:30", "Godzina W – Warsaw Uprising remembrance", "PERSONAL", "Rondo Dmowskiego", "", True),
    ("2026-08-23", "20:00", "20:30", "Laundry + pack for Split!", "CHORES", HOME, "Sunscreen, snorkel, adapter.", False),
    ("2026-08-24", "06:00", "06:30", "Taxi to airport", "TRAVEL-PRIVATE", HOME, "Bolt booked for 06:00.", True),
    ("2026-08-24", "07:10", "09:15", "Flight LO 577 WAW → SPU", "TRAVEL-PRIVATE", WAW, "Seat 4A. Booking ref K7Q2ZP.", True),
]


# =====================================================================================
# 1) Trips
# =====================================================================================
def flight_events(day, leg, cat, taxi=True):
    code, route, dep, arr, note = leg
    if taxi and route.startswith("WAW"):
        add(day, minus(dep, 75), minus(dep, 45), "Taxi to airport", cat, HOME, f"Bolt booked for {minus(dep, 75)}.")
    add(day, dep, arr, f"Flight {code} {route}", cat, WAW if route.startswith("WAW") else route.split(" → ")[0],
        " ".join(x for x in (f"Seat {rng.choice('ACDF')}{rng.randint(2, 18)}.", note) if x))


def train_events(day, leg, cat):
    code, route, dep, arr = leg
    add(day, dep, arr, f"Train {code} {route}", cat, CENTRALNA if route.startswith("Warszawa") else route.split(" → ")[0],
        f"Car {rng.randint(2, 9)}, seat {rng.randint(11, 88)}.")


leave_home, arrive_home = {}, {}    # date -> time she leaves / comes back (for filling the rest of the day)
TRIPS.sort(key=lambda t: t["first"])
for t in TRIPS:
    first, last = d(t["first"]), d(t["last"])
    cat = "TRAVEL-WORK" if t["kind"] == "work" else "TRAVEL-PRIVATE"
    desc = " ".join(x for x in (t.get("stay", "") + (" (%d nights)." % (last - first).days if t.get("stay") and last > first else ""), t.get("desc", "")) if x)
    allday(first, last, t["title"], cat, t["place"], desc.strip())
    mode, key = t["via"]
    if mode == "flight":
        out, back = FLIGHTS[key]
        out = t.get("out_override", out)
        flight_events(first, out, cat)
        flight_events(last, back, cat, taxi=False)
        leave_home[first] = minus(out[2], 75)
        arrive_home[last] = plus(back[3], 45)
    elif mode == "train":
        out, back = TRAINS[key]
        train_events(first, out, cat)
        train_events(last, back, cat)
        leave_home[first] = minus(out[2], 20)
        arrive_home[last] = plus(back[3], 20)
    else:  # car with a friend
        add(first, "08:30", "12:30", f"Drive to Mazury w/ {key}", cat, HOME, f"{key} picks me up at 08:30.")
        add(last, "14:00", "18:00", f"Drive back w/ {key}", cat, "Giżycko")
        leave_home[first], arrive_home[last] = "08:30", "18:15"
    for off, s, e, title, loc in t["meetings"]:
        add(first + timedelta(days=off), s, e, title, "WORK" if t["kind"] == "work" else "PAUL" if "Paul" in title else "SOCIAL-OUT", loc)
    day = first
    while day <= last:
        if day < last:
            away_nights.add(day)
        s = hm(leave_home[first]) if day == first else time(0, 0)
        e = hm(arrive_home[last]) if day == last else time(23, 59)
        block(day, s, e)
        day += timedelta(days=1)
    # packing / laundry the evening before (or the morning of) most trips of >= 1 night
    if last > first and rng.random() < 0.75:
        eve = first - timedelta(days=1)
        if free(eve, "20:00", "20:30"):
            add(eve, "20:00", "20:30", f"Laundry + pack for {t['place'].split(',')[0]}", "CHORES", HOME, block=False)

leave_home[d("2026-08-24")] = "06:00"                                  # Split holiday: flight 07:10 (see SPECIAL)
for day in (d("2026-08-24") + timedelta(days=k) for k in range(8)):   # Split holiday (all-day entry is in the existing file)
    away_nights.add(day)
    block(day, "06:00" if day == d("2026-08-24") else "00:00", "23:59")

# =====================================================================================
# 2) Paul in Warsaw
# =====================================================================================
for first, last, arrival, departure, plans in PAUL:
    first, last = d(first), d(last)
    allday(first, last, "Paul in Warsaw", "PAUL", HOME)
    k = first
    while k <= last:
        paul_days.add(k)
        k += timedelta(days=1)
    a_day, a_what, a_time, a_where = arrival
    if a_where == WAW:
        add(d(a_day), minus(a_time, 40), plus(a_time, 50), a_what, "PAUL", a_where)
    else:
        add(d(a_day), a_time, plus(a_time, 30), a_what, "PAUL", a_where, "Arrives %s." % a_time)
    p_day, p_what, p_time, p_where = departure
    add(d(p_day), p_time, plus(p_time, 30), p_what, "PAUL", p_where, block=False)
    for day, s, e, title, cat, loc, away in plans:
        add(d(day), s, e, title, cat, loc, block=True)

# =====================================================================================
# 3) Holidays + special days
# =====================================================================================
for day, name in HOLIDAYS.items():
    allday(d(day), d(day), f"Public holiday – {name}", "PERSONAL")
for day, s, e, title, cat, loc, desc, away in SPECIAL:
    if s is None:
        allday(d(day), d(day), title, cat, loc, desc)
    else:
        add(d(day), s, e, title, cat, loc, desc)

# =====================================================================================
# 4) Everyday life (rules, only into free time)
# =====================================================================================
OFFICE_MEETINGS = ["Q{q} partnership pipeline review", "Product roadmap sync", "Budget review", "Tender prep – municipal flexibility",
                   "Partner onboarding – new DSO", "Sales & partnerships weekly", "Lunch w/ Marta", "Hiring interview – partner manager",
                   "Legal review – data sharing agreement", "All-hands"]
WFH_MEETINGS = ["Nordvolt pilot – weekly call", "VoltHaus – tariff model review", "KrakGrid – data quality call",
                "Focus: write partner proposal", "DonauNetz – tender Q&A", "Kraftly – integration check-in",
                "Isarwatt – API follow-up", "Polderstroom – offer review", "Expense report + travel booking"]
FRIENDS = ["Kasia", "Marta", "Tomek", "Ola", "Bartek"]
PLACES_OUT = ["Hala Koszyki, ul. Koszykowa 63", "Hala Gwardii", "Beirut Hummus & Music Bar", "Browar Warszawski",
              "Kawiarnia Relaks, ul. Puławska 48", "Pardon, To Tu", "Nolita, ul. Wilcza 46", "Bar Studio, PKiN"]


def quarter(day):
    return (day.month - 1) // 3 + 1


grocery_due = set()
last_grocery = FIRST - timedelta(days=7)
for t in TRIPS:
    if (d(t["last"]) - d(t["first"])).days >= 3:
        grocery_due.add(d(t["last"]) + timedelta(days=1))

day = FIRST
while day <= LAST:
    wd = day.weekday()
    holiday = day.isoformat() in HOLIDAYS
    fully_away = day in away_nights and (day - timedelta(days=1)) in away_nights and day not in leave_home and day not in arrive_home
    if fully_away:
        day += timedelta(days=1)
        continue
    leaves, returns = leave_home.get(day), arrive_home.get(day)

    # --- work mode on working days ---
    if wd < 5 and not holiday:
        if leaves and hm(leaves) < time(12, 0) or returns and hm(returns) > time(13, 0) and not leaves:
            pass                                             # travel day, no office/WFH entry
        elif leaves or returns:
            allday(day, day, "WFH (morning)" if leaves else "WFH (afternoon)", "WFH", HOME)
        else:
            office = rng.random() < {0: 0.35, 1: 0.85, 2: 0.4, 3: 0.85, 4: 0.2}[wd] and day not in paul_days
            if office:
                allday(day, day, "Office", "OFFICE", OFFICE)
                block(day, "08:15", "18:00")
                title = rng.choice(OFFICE_MEETINGS).format(q=quarter(day))
                s = rng.choice(["10:00", "11:00", "13:00", "14:30"])
                add(day, s, plus(s, 60), title, "WORK", "Hala Gwardii" if "Lunch" in title else "Room 'Wisła', 18th floor", block=False)
            else:
                allday(day, day, "WFH", "WFH", HOME, "Paul working from mine too." if day in paul_days and rng.random() < 0.6 else "")
                for _ in range(rng.choice([1, 1, 2])):
                    s = rng.choice(["10:00", "11:00", "14:00", "15:30", "16:00"])
                    add(day, s, plus(s, 60), rng.choice(WFH_MEETINGS), "WORK", "Microsoft Teams", block=False)

    # --- evenings / weekends, only when she is in Warsaw and free ---
    in_town_evening = not leaves and (not returns or hm(returns) < time(18, 0))
    if in_town_evening:
        if wd == 2 and day not in paul_days and rng.random() < 0.7 and free(day, "19:00", "21:00"):
            add(day, "19:00", "21:00", "Bouldering w/ " + rng.choice(["Tomek & Ola", "Ola", "Tomek", "Bartek"]), "SPORT", GYM)
        elif wd == 0 and rng.random() < 0.25 and free(day, "18:30", "19:30"):
            add(day, "18:30", "19:30", "Yoga – Joga Studio", "SPORT", "Joga Studio, ul. Mokotowska 51")
        elif wd in (1, 3) and day not in paul_days and rng.random() < 0.3 and free(day, "19:00", "22:00"):
            add(day, "19:00", "22:00", f"Dinner w/ {rng.choice(FRIENDS)}", "SOCIAL-OUT", rng.choice(PLACES_OUT))
        elif wd == 4 and day not in paul_days and rng.random() < 0.3 and free(day, "19:30", "23:00"):
            add(day, "19:30", "23:00", rng.choice(["Cinema w/ Ola – Kino Muranów", "Drinks w/ Bartek & Tomek",
                                                   "Concert w/ Marta – Klub Hydrozagadka"]), "SOCIAL-OUT",
                rng.choice(["Kino Muranów", "Pardon, To Tu", "Klub Hydrozagadka, ul. 11 Listopada 22"]))
    morning_free = not leaves or hm(leaves) > time(12, 0)
    if wd == 5 and morning_free and not returns and rng.random() < 0.5 and free(day, "09:30", "10:30"):
        add(day, "09:30", "10:30", "Run – Pole Mokotowskie", "SPORT", "Pole Mokotowskie")
    if wd == 6 and morning_free and not returns and day not in paul_days and rng.random() < 0.25 and free(day, "11:30", "14:00"):
        add(day, "11:30", "14:00", "Sunday brunch w/ " + " & ".join(rng.sample(FRIENDS, 2)), "SOCIAL-OUT",
            rng.choice(["Charlotte, pl. Zbawiciela", "Kawiarnia Relaks, ul. Puławska 48", "Hala Koszyki"]))
    if wd == 6 and not leaves and rng.random() < 0.4 and free(day, "20:00", "20:45"):
        add(day, "20:00", "20:45", "Call Mum", "PERSONAL", HOME, block=False)

    # --- groceries: weekly on Sundays at home, and the day after longer trips ---
    weekly = wd == 6 and (day - last_grocery).days > 3 and rng.random() < 0.6
    if (day in grocery_due or weekly) and not leaves and free(day, "18:00", "19:00"):
        add(day, "18:00", "19:00", "Grocery delivery (Frisco)", "CHORES", HOME,
            "Fridge is empty after the trip." if day in grocery_due else "", block=False)
        last_grocery = day
    day += timedelta(days=1)

# recurring meetings (same as in the existing calendar, for this period)
events.append(dict(start=datetime(2025, 9, 1, 9, 30), end=datetime(2025, 9, 1, 9, 50), summary="Team stand-up", cat="WORK",
                   location="Microsoft Teams", desc="Partnerships team weekly stand-up.", busy=True,
                   rrule="FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20260831T215959Z"))
events.append(dict(start=datetime(2025, 9, 4, 10, 0), end=datetime(2025, 9, 4, 10, 45), summary="1:1 with Anna", cat="WORK",
                   location="Microsoft Teams", desc="Bi-weekly 1:1 with manager (Anna Wróblewska).", busy=True,
                   rrule="FREQ=WEEKLY;INTERVAL=2;BYDAY=TH;UNTIL=20260831T215959Z"))


# =====================================================================================
# Serialisation (same format as the existing calendar)
# =====================================================================================
VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Warsaw
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE""".split("\n")


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    out, b, first = [], line.encode("utf-8"), True
    while b:
        cut = min(75 if first else 74, len(b))
        while cut < len(b) and (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(("" if first else " ") + b[:cut].decode("utf-8"))
        b, first = b[cut:], False
    return "\r\n".join(out)


def vevent(e):
    key = f"{e['start']}{e['summary']}{e.get('rrule', '')}"
    lines = ["BEGIN:VEVENT", f"UID:{hashlib.md5(key.encode()).hexdigest()}@aleksandra.hackowatt", "DTSTAMP:20260929T090000Z"]
    if isinstance(e["start"], datetime):
        lines += [f"DTSTART;TZID=Europe/Warsaw:{e['start']:%Y%m%dT%H%M%S}", f"DTEND;TZID=Europe/Warsaw:{e['end']:%Y%m%dT%H%M%S}"]
    else:
        lines += [f"DTSTART;VALUE=DATE:{e['start']:%Y%m%d}", f"DTEND;VALUE=DATE:{e['end']:%Y%m%d}"]
    if e.get("rrule"):
        lines.append(f"RRULE:{e['rrule']}")
    lines.append(f"SUMMARY:{esc(e['summary'])}")
    if e["location"]:
        lines.append(f"LOCATION:{esc(e['location'])}")
    if e["desc"]:
        lines.append(f"DESCRIPTION:{esc(e['desc'])}")
    lines += [f"CATEGORIES:{e['cat']}", f"TRANSP:{'OPAQUE' if e['busy'] else 'TRANSPARENT'}", "END:VEVENT"]
    return lines


def write(path, blocks_):
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HackoWatt//Aleksandra Calendar//EN", "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH", "X-WR-CALNAME:Aleksandra", "X-WR-TIMEZONE:Europe/Warsaw"] + VTIMEZONE
    body = [fold(l) for l in head]
    for b in blocks_:
        body += b
    body.append("END:VCALENDAR")
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8")


def existing_blocks():
    """VEVENT blocks of the existing calendar, copied line by line (already folded)."""
    text = EXISTING.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    blocks_, cur = [], None
    for line in text:
        if line == "BEGIN:VEVENT":
            cur = [line]
        elif cur is not None:
            cur.append(line)
            if line == "END:VEVENT":
                blocks_.append(cur)
                cur = None
    return blocks_


new_blocks = [[fold(l) for l in vevent(e)] for e in sorted(events, key=lambda e: (str(e["start"]), e["summary"]))]
write(OUT_NEW, new_blocks)
write(OUT_FULL, new_blocks + existing_blocks())

nights = (LAST - FIRST).days + 1
print(f"{len(events)} events ({len(new_blocks)} VEVENTs) -> {OUT_NEW.name}")
print(f"{len(new_blocks) + len(existing_blocks())} VEVENTs -> {OUT_FULL.name}")
print(f"nights away: {len(away_nights)} of {nights} ({len(away_nights) / nights:.0%}), Paul in Warsaw: {len(paul_days)} days, "
      f"trips: {len(TRIPS) + 1}")
