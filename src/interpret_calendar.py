"""Step 2 – an LLM reads every calendar day and predicts when Aleksandra is home (isHome LLM step).
Results are cached in data/llm_cache/<provider>_<model>/; a day is only sent again when its entries change.

Usage:  python3 src/interpret_calendar.py              # all days 1 Sep 2025 – 12 Oct 2026
        python3 src/interpret_calendar.py 2026-09-22   # one day: prints the prompt and the result
Provider: ISHOME_PROVIDER=gemini (default; needs GEMINI_API_KEY or API_KEY=... in .secret)
          ISHOME_PROVIDER=ollama (needs `ollama serve` + `ollama pull qwen3:8b`)
          ISHOME_PROVIDER=claude (needs ANTHROPIC_API_KEY or `ant auth login`)
"""
import sys
import time
from datetime import date

from hackowatt.calendar_parse import entries_by_day
from hackowatt.llm_ishome import (CACHE, MODEL, PROVIDER, SYSTEM, DailyLimitReached, build_prompt, calendar_days,
                                  interpret_day)


def main():
    by_day = entries_by_day()
    print(f"provider {PROVIDER}, model {MODEL}, cache {CACHE.name}/")
    if len(sys.argv) > 1:
        d = date.fromisoformat(sys.argv[1])
        print(SYSTEM, "\n----\n", build_prompt(by_day, d), "\n----")
        for iv in interpret_day(by_day, d)["intervals"]:
            print(f"{iv['start']}–{iv['end']}  away {iv['away_score']:3d}  people {iv['people']}  {iv['reason']}")
        return
    done = 0
    for d in calendar_days():
        t0 = time.time()
        try:
            result = interpret_day(by_day, d)
        except DailyLimitReached:
            print(f"\nDaily request limit reached at {d} ({done} days done in this run). Everything so far is saved – "
                  "run this script again after the reset (midnight Pacific time = 09:00 Warsaw in summer).")
            return
        done += 1
        print(f"{d}  {len(result['intervals'])} intervals  {time.time() - t0:5.0f} s", flush=True)
    print("all days interpreted")


if __name__ == "__main__":
    main()
