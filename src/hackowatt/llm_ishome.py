"""isHome – LLM step: an LLM reads one calendar day and returns when the user is home and with whom.

Provider chosen with ISHOME_PROVIDER: "gemini" (default; Google Gemini API, key in GEMINI_API_KEY or API_KEY
in .secret, model gemini-3.5-flash-lite), "ollama" (local, free – model qwen3:8b) or "claude" (Anthropic API, model
claude-opus-5). ISHOME_MODEL overrides the model. The reason is asked before the score so the model
decides the number after describing the interval.

Runs per calendar day; the result is cached in data/llm_cache/<provider>_<model>/<date>_<hash>.json, where
the hash covers everything sent to the model (entries of the day ± 1 day, instructions, model). A day is
only sent again when its entries change. Each provider/model has its own folder, so results can be compared.

Output per day: time intervals covering 00:00–24:00, each with
  away_score 0–100 (0 = home for sure, 50 = no idea, 100 = away for sure),
  people (number of people in the apartment, incl. the user if she is home), reason.

Run it with src/interpret_calendar.py.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from .calendar_parse import entries_by_day, format_day
from .paths import ROOT
from .profile import profile_text

PROVIDER = os.environ.get("ISHOME_PROVIDER", "gemini")
MODEL = os.environ.get("ISHOME_MODEL", {"ollama": "qwen3:8b", "gemini": "gemini-3.5-flash-lite",
                                        "claude": "claude-opus-5"}[PROVIDER])
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
CACHE = ROOT / "data" / "llm_cache" / re.sub(r"[^A-Za-z0-9.-]+", "-", f"{PROVIDER}_{MODEL}")
MAX_ATTEMPTS = 3              # re-ask when the answer does not cover 00:00–24:00 correctly
GEMINI_RETRY_WAITS = [10, 20, 40, 60, 60]   # seconds, on 429 (rate limit) / 503 (overloaded) / network errors
GEMINI_MIN_INTERVAL = 4.5                   # seconds between requests (≈ 13 per minute, below the free-tier RPM)
_last_gemini_call = 0.0
FIRST_DAY, LAST_DAY = date(2025, 9, 1), date(2026, 10, 12)

SYSTEM = f"""You help a home-energy app predict when its user is physically inside her apartment, based on her
calendar. The app knows nothing about her life beyond what is written below.

USER PROFILE
{profile_text()}

TASK
For the TARGET DAY, think step by step about where she is at every moment. Use the previous and next day
for context (e.g. whether she wakes up at home or elsewhere). Estimate travel times yourself from the
locations in the entries and the home address. Calendar entries can also describe other people's plans,
and some entries say nothing about where she is.
Return consecutive intervals that cover the whole target day from 00:00 to 24:00 without gaps or overlaps.
For each interval give:
- reason: one short sentence (write it first).
- away_score: 0 = certainly in the apartment, 100 = certainly not, 50 = cannot tell. Use 0 or 100 only
  when the calendar states it directly (e.g. an entry at another place at that time, or an overnight stay
  elsewhere). For conclusions you draw yourself (e.g. travel before or after an entry, or plans the
  calendar does not state) use values like 10–30 or 70–90.
- people: number of people physically inside the apartment during the interval – the user only if she is
  there, plus anyone else staying or visiting; 0 if the apartment is empty.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "intervals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "HH:MM"},
                    "end": {"type": "string", "description": "HH:MM, 24:00 for end of day"},
                    "reason": {"type": "string"},
                    "away_score": {"type": "integer"},
                    "people": {"type": "integer"},
                },
                "required": ["start", "end", "reason", "away_score", "people"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["intervals"],
    "additionalProperties": False,
}


def build_prompt(by_day, d):
    parts = []
    for label, day in (("PREVIOUS DAY", d - timedelta(days=1)), ("TARGET DAY", d), ("NEXT DAY", d + timedelta(days=1))):
        parts.append(f"=== {label}: {day:%A %d %B %Y} ===\n{format_day(by_day, day)}")
    return "\n\n".join(parts)


def cache_path(d, prompt):
    h = hashlib.sha256(f"{MODEL}\n{SYSTEM}\n{prompt}".encode()).hexdigest()[:12]
    return CACHE / f"{d.isoformat()}_{h}.json"


def call_claude(prompt):
    import anthropic  # imported lazily: cached results can be read without the SDK installed

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Model refused: {response.stop_details}")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text), response.model


def call_ollama(prompt):
    """Local model via the Ollama HTTP API, with the JSON schema as structured output and thinking on."""
    body = dict(model=MODEL, stream=False, think=True, format=SCHEMA, options={"temperature": 0},
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}])
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        answer = json.loads(resp.read())
    return json.loads(answer["message"]["content"]), f"ollama:{MODEL}"


def _gemini_schema(node):
    """JSON schema -> Gemini response schema (OpenAPI subset: no additionalProperties, keeps field order)."""
    if isinstance(node, dict):
        out = {k: _gemini_schema(v) for k, v in node.items() if k != "additionalProperties"}
        if "properties" in node:
            out["propertyOrdering"] = list(node["properties"])
        return out
    if isinstance(node, list):
        return [_gemini_schema(v) for v in node]
    return node


def _secret(name):
    """Value from the git-ignored .secret file (KEY=value lines) – the key is never printed."""
    path = ROOT / ".secret"
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() == name:
                return v.strip().strip('"\'')
    return None


class DailyLimitReached(RuntimeError):
    """The provider's requests-per-day quota is used up (Gemini free tier resets at midnight Pacific time)."""


def call_gemini(prompt):
    """Google Gemini REST API (generateContent) with JSON output."""
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": _gemini_schema(SCHEMA)},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": os.environ.get("GEMINI_API_KEY") or _secret("API_KEY")})
    global _last_gemini_call
    for wait in GEMINI_RETRY_WAITS + [None]:
        time.sleep(max(0.0, GEMINI_MIN_INTERVAL - (time.time() - _last_gemini_call)))   # pace requests
        _last_gemini_call = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                answer = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 and "PerDay" in body:             # daily quota used up: no point in waiting minutes
                raise DailyLimitReached(body[:300]) from None
            if e.code in (429, 503) and wait is not None:     # per-minute limit / overloaded: wait and retry
                asked = re.search(r'"retryDelay":\s*"(\d+)s"', body)
                wait = max(wait, int(asked.group(1)) + 1) if asked else wait
                print(f"  Gemini {e.code}, retrying in {wait} s", flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f"Gemini API error {e.code}: {body[:500]}") from None
        except (TimeoutError, ConnectionError, urllib.error.URLError) as e:
            if wait is None:
                raise
            print(f"  Gemini network error ({e.__class__.__name__}), retrying in {wait} s", flush=True)
            time.sleep(wait)
    text = "".join(p.get("text", "") for p in answer["candidates"][0]["content"]["parts"])
    return json.loads(text), f"gemini:{answer.get('modelVersion', MODEL)}"


def call_model(prompt):
    return {"ollama": call_ollama, "gemini": call_gemini, "claude": call_claude}[PROVIDER](prompt)


def validate(intervals):
    """Intervals must be consecutive and cover 00:00–24:00; scores clamped to 0–100."""
    if intervals and intervals[-1]["end"] in ("23:59", "00:00"):   # both mean end of day
        intervals[-1]["end"] = "24:00"
    t = "00:00"
    for iv in intervals:
        if iv["start"] != t:
            raise ValueError(f"gap/overlap at {t} -> {iv['start']}")
        t = iv["end"]
        iv["away_score"] = max(0, min(100, iv["away_score"]))
        iv["people"] = max(0, iv["people"])
    if t != "24:00":
        raise ValueError(f"day ends at {t}, not 24:00")
    return intervals


def interpret_day(by_day, d, force=False):
    prompt = build_prompt(by_day, d)
    path = cache_path(d, prompt)
    if path.exists() and not force:
        return json.loads(path.read_text())
    ask = prompt
    for attempt in range(1, MAX_ATTEMPTS + 1):
        data, served_by = call_model(ask)
        try:
            intervals = validate(data["intervals"])
            break
        except (KeyError, ValueError) as e:
            if attempt == MAX_ATTEMPTS:
                raise ValueError(f"{d}: no valid answer after {MAX_ATTEMPTS} attempts ({e})")
            ask = (f"{prompt}\n\nYour previous answer was invalid: {e}. The intervals must be consecutive and "
                   f"cover the whole target day from 00:00 to 24:00.")
    result = dict(date=d.isoformat(), model=served_by, created=datetime.now().isoformat(timespec="seconds"),
                  attempts=attempt, intervals=intervals)
    CACHE.mkdir(parents=True, exist_ok=True)
    for old in CACHE.glob(f"{d.isoformat()}_*.json"):   # entries changed -> drop the stale result
        old.unlink()
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def _minutes(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def hourly(result):
    """Day result -> 24 rows of (hour, away_score, people, reason), time-weighted within each hour."""
    rows = []
    for h in range(24):
        a, b = h * 60, h * 60 + 60
        score = people = 0.0
        reasons = []
        for iv in result["intervals"]:
            overlap = min(b, _minutes(iv["end"])) - max(a, _minutes(iv["start"]))
            if overlap > 0:
                score += iv["away_score"] * overlap / 60
                people += iv["people"] * overlap / 60
                reasons.append(iv["reason"])
        rows.append(dict(hour=h, away_score=round(score, 1), people=round(people, 2), reason=" / ".join(dict.fromkeys(reasons))))
    return rows


def cached_results():
    """{date: result} for days whose cached answer matches the current prompt (stale answers are ignored)."""
    by_day, out = entries_by_day(), {}
    for d in calendar_days():
        path = cache_path(d, build_prompt(by_day, d))
        if path.exists():
            out[d] = json.loads(path.read_text())
    return out


def calendar_days():
    d = FIRST_DAY
    while d <= LAST_DAY:
        yield d
        d += timedelta(days=1)
