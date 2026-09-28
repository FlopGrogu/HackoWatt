"""Read aleksandra_calendar.ics into calendar entries grouped per day (recurring events expanded)."""
from collections import defaultdict
from datetime import date, datetime, timedelta

import icalendar

from .paths import ROOT

ICS = ROOT / "aleksandra_calendar.ics"
WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _occurrences(ev):
    """Start datetimes/dates of an event, expanding simple weekly RRULEs (BYDAY, INTERVAL, UNTIL)."""
    start = ev.decoded("DTSTART")
    rule = ev.get("RRULE")
    if not rule:
        return [start]
    until = rule["UNTIL"][0]
    until = until.replace(tzinfo=None) if isinstance(until, datetime) else datetime.combine(until, datetime.max.time())
    interval = int(rule.get("INTERVAL", [1])[0])
    days = {WEEKDAYS.index(d) for d in rule.get("BYDAY", [WEEKDAYS[start.weekday()]])}
    week0 = start.date() - timedelta(days=start.weekday())
    out, cur = [], start
    while cur.replace(tzinfo=None) <= until:
        week = ((cur.date() - timedelta(days=cur.weekday())) - week0).days // 7
        if cur.weekday() in days and week % interval == 0:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def load_entries():
    """All calendar entries as dicts: summary, location, description, all_day, start, end (naive local time)."""
    cal = icalendar.Calendar.from_ical(ICS.read_bytes())
    entries = []
    for ev in cal.walk("VEVENT"):
        dur = ev.decoded("DTEND") - ev.decoded("DTSTART")
        for s in _occurrences(ev):
            all_day = not isinstance(s, datetime)
            if all_day:
                s = datetime.combine(s, datetime.min.time())
            s = s.replace(tzinfo=None)
            entries.append(dict(summary=str(ev.get("SUMMARY", "")), location=str(ev.get("LOCATION", "")),
                                description=str(ev.get("DESCRIPTION", "")), all_day=all_day, start=s, end=s + dur))
    return sorted(entries, key=lambda e: (e["start"], not e["all_day"]))


def entries_by_day(entries=None):
    """{date: [entries touching that day]}. Multi-day all-day entries appear on every day they cover."""
    by_day = defaultdict(list)
    for e in entries or load_entries():
        d = e["start"].date()
        last = (e["end"] - timedelta(seconds=1)).date()
        while d <= last:
            by_day[d].append(e)
            d += timedelta(days=1)
    return by_day


def format_entry(e):
    if e["all_day"]:
        span = f"all day ({e['start']:%d %b} – {(e['end'] - timedelta(days=1)):%d %b})"
    else:
        span = f"{e['start']:%H:%M}–{e['end']:%H:%M}"
    text = f"{span}  {e['summary']}"
    if e["location"]:
        text += f"  @ {e['location']}"
    if e["description"]:
        text += f"  ({e['description']})"
    return text


def format_day(by_day, d: date):
    lines = [format_entry(e) for e in by_day.get(d, [])]
    return "\n".join(lines) if lines else "(no entries)"
