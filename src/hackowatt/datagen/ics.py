"""Minimal iCalendar writer/reader for the calendars this pipeline produces (no recurrence rules, one TZID)."""
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class Event:
    start: object                 # datetime (timed) or date (all-day)
    end: object                   # exclusive for all-day
    summary: str
    cat: str
    location: str = ""
    desc: str = ""
    busy: bool = True

    @property
    def all_day(self):
        return not isinstance(self.start, datetime)

    @property
    def first_day(self):
        return self.start if self.all_day else self.start.date()

    @property
    def last_day(self):
        return self.end - timedelta(days=1) if self.all_day else (self.end - timedelta(seconds=1)).date()


def _vtimezone(tz):
    if tz != "Europe/Warsaw":       # other zones: readers fall back to the TZID name
        return []
    return ["BEGIN:VTIMEZONE", "TZID:Europe/Warsaw", "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
            "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT", "BEGIN:STANDARD",
            "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET", "DTSTART:19701025T030000",
            "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD", "END:VTIMEZONE"]


def _esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _unesc(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append("\n" if s[i + 1] in "nN" else s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _fold(line):
    out, b, first = [], line.encode("utf-8"), True
    while b:
        cut = min(75 if first else 74, len(b))
        while cut < len(b) and (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(("" if first else " ") + b[:cut].decode("utf-8"))
        b, first = b[cut:], False
    return "\r\n".join(out)


def _vevent(e, tz, stamp):
    uid = hashlib.md5(f"{e.start}{e.end}{e.summary}{e.location}".encode()).hexdigest()
    lines = ["BEGIN:VEVENT", f"UID:{uid}@aleksandra.hackowatt", f"DTSTAMP:{stamp}"]
    if e.all_day:
        lines += [f"DTSTART;VALUE=DATE:{e.start:%Y%m%d}", f"DTEND;VALUE=DATE:{e.end:%Y%m%d}"]
    else:
        lines += [f"DTSTART;TZID={tz}:{e.start:%Y%m%dT%H%M%S}", f"DTEND;TZID={tz}:{e.end:%Y%m%dT%H%M%S}"]
    lines.append(f"SUMMARY:{_esc(e.summary)}")
    if e.location:
        lines.append(f"LOCATION:{_esc(e.location)}")
    if e.desc:
        lines.append(f"DESCRIPTION:{_esc(e.desc)}")
    lines += [f"CATEGORIES:{e.cat}", f"TRANSP:{'OPAQUE' if e.busy else 'TRANSPARENT'}", "END:VEVENT"]
    return lines


def write_ics(path, events, tz, year):
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HackoWatt//Aleksandra Calendar//EN", "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH", "X-WR-CALNAME:Aleksandra", f"X-WR-TIMEZONE:{tz}"] + _vtimezone(tz)
    stamp = f"{year}0101T000000Z"          # fixed, so the files are byte-identical between runs
    body = list(head)
    for e in sorted(events, key=lambda e: (str(e.start), e.summary)):
        body += _vevent(e, tz, stamp)
    body.append("END:VCALENDAR")
    path.write_text("\r\n".join(_fold(l) for l in body) + "\r\n", encoding="utf-8")


def read_ics(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = []
    for l in text.split("\n"):
        if l.startswith((" ", "\t")) and lines:
            lines[-1] += l[1:]
        else:
            lines.append(l)
    events, cur = [], None
    for l in lines:
        if l == "BEGIN:VEVENT":
            cur = {}
        elif l == "END:VEVENT":
            s, e = cur["DTSTART"], cur["DTEND"]
            events.append(Event(s, e, _unesc(cur.get("SUMMARY", "")), cur.get("CATEGORIES", ""), _unesc(cur.get("LOCATION", "")),
                                _unesc(cur.get("DESCRIPTION", "")), cur.get("TRANSP", "OPAQUE") == "OPAQUE"))
            cur = None
        elif cur is not None and ":" in l:
            key, val = l.split(":", 1)
            name = key.split(";")[0]
            if name in ("DTSTART", "DTEND"):
                val = datetime.strptime(val, "%Y%m%dT%H%M%S") if "T" in val else datetime.strptime(val, "%Y%m%d").date()
            cur[name] = val
    return sorted(events, key=lambda e: (str(e.start), e.summary))
