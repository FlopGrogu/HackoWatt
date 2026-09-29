"""Run configuration shared by all generation stages."""
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]

# The apartment is 0.8 km south-west of the city coordinates that are handed to Open-Meteo (Warsaw: ul. Chmielna 71).
HOME_OFFSET = (-0.0001, -0.0092)


@dataclass
class Config:
    seed: int = 2026
    lat: float = 52.2297                 # city coordinates (weather, sun, all local places)
    lon: float = 21.0122
    city: str = "Warsaw"
    iata: str = "WAW"                    # home airport code used in flight entries
    tz: str = "Europe/Warsaw"
    year: int = 2026                     # simulated year
    weather_year: int = 2025             # real weather that is replayed as `year`
    today: datetime = field(default_factory=lambda: datetime(2026, 9, 29))   # rows before this are "history"
    offline: bool = False                # never touch the network, use cached weather files only
    target_away: float = 0.47            # share of the year spent on trips (office hours come on top)

    @property
    def zone(self):
        return ZoneInfo(self.tz)

    @property
    def start(self):
        return datetime(self.year, 1, 1)

    @property
    def end(self):                        # exclusive
        return datetime(self.year + 1, 1, 1)

    @property
    def hours(self):
        return int((self.end - self.start).total_seconds() // 3600)

    @property
    def home(self):
        return self.lat + HOME_OFFSET[0], self.lon + HOME_OFFSET[1]

    # ---- paths ----
    @property
    def data(self):
        return ROOT / "data"

    @property
    def calendar_dir(self):
        return self.data / "calendar"

    @property
    def full_calendar(self):
        return self.calendar_dir / f"aleksandra_calendar_{self.year}.ics"

    def rng(self, name):
        """Independent, reproducible random stream per stage (string seeds are hashed deterministically)."""
        return random.Random(f"{self.seed}:{name}")

    def stamp(self, dt):
        """Local wall-clock time with the UTC offset in force at that time, e.g. 2026-07-01T14:00:00+02:00."""
        return dt.replace(tzinfo=self.zone).isoformat(timespec="seconds")


def clipped_gauss(rng, mu, sigma, lo, hi):
    """Normally distributed value, truncated to [lo, hi]."""
    return min(hi, max(lo, rng.gauss(mu, sigma)))
