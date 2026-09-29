"""Read the generated calendar (data/calendar/aleksandra_calendar_<year>.ics) into calendar entries grouped per day."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from .datagen.ics import read_ics
from .paths import ROOT

ICS = ROOT / "data" / "calendar" / "aleksandra_calendar_2026.ics"      # src/generate_all.py


def load_entries():
    """All calendar entries as dicts: summary, location, description, all_day, start, end (naive local time)."""
    entries = []
    for e in read_ics(ICS):
        s, en = (datetime.combine(e.start, datetime.min.time()), datetime.combine(e.end, datetime.min.time())) if e.all_day else (e.start, e.end)
        entries.append(dict(summary=e.summary, location=e.location, description=e.desc, all_day=e.all_day, start=s, end=en))
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
