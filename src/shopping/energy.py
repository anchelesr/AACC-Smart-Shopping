"""Carbon Monitor: collects the two energy signals (carbon intensity, electricity price) and the renewable flag.

Sources sit behind one interface (`IEnergyFeed.read() -> Reading`): a deterministic simulator (default), a JSON
file (for replay and tests) and an Electricity Maps adapter (optional, not tested against the live service).
Every reading is validated and stored, including the invalid ones with a status, so a missing or implausible
signal is visible instead of silent. Units: carbon in gCO2e/kWh, price in EUR/kWh.
"""
from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

from events.consumer import Metrics

INTENSITY_RANGE = (0.0, 1500.0)
PRICE_RANGE = (-0.5, 5.0)            # negative prices exist on real markets


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Reading:
    intensity: Optional[float] = None
    price: Optional[float] = None
    renewable: bool = False
    observed_at: Optional[str] = None      # feed time; the collection time is used if absent


class EnergyFeed(Protocol):
    def read(self, now: datetime) -> Reading: ...


class FeedError(Exception):
    pass


class SimulatedFeed:
    """Slow daily wave plus a seeded pseudo-random jump; renewable energy in a configurable hour window.
    Deterministic for the same time and seed, so tests and demonstrations are repeatable."""

    def __init__(self, seed: int = 7, renewable_hours: tuple[int, int] = (11, 15)) -> None:
        self.seed, self.renewable_hours = seed, renewable_hours

    def read(self, now: datetime) -> Reading:
        h = now.hour + now.minute / 60
        wave = math.sin((h - 6) / 24 * 2 * math.pi)                          # one slow daily wave, peak at 12:00
        slot = int(now.timestamp() // 1800)                                  # new jitter every 30 minutes
        jitter = ((slot * 2654435761 + self.seed * 40503) % 1000) / 1000 - 0.5
        intensity = 330 + 140 * wave + 60 * jitter
        price = 0.19 + 0.09 * math.sin((h - 9) / 24 * 2 * math.pi) + 0.03 * jitter
        lo, hi = self.renewable_hours
        return Reading(round(intensity, 1), round(price, 4), lo <= now.hour < hi, iso(now))


class StaticFeed:
    def __init__(self, reading: Reading) -> None:
        self.reading = reading

    def read(self, now: datetime) -> Reading:
        return self.reading


class FileFeed:
    """Reads {"intensity":..,"price":..,"renewable":..,"observed_at":..} from a JSON file (replay, tests)."""

    def __init__(self, path: str) -> None:
        self.path = path

    def read(self, now: datetime) -> Reading:
        try:
            with open(self.path, encoding="utf-8") as fh:
                o = json.load(fh)
            return Reading(o.get("intensity"), o.get("price"), bool(o.get("renewable", False)), o.get("observed_at"))
        except (OSError, ValueError, AttributeError) as exc:
            raise FeedError(str(exc)) from exc


class ControlledFeed:
    """For demonstrations and acceptance tests: the signal is set by the operator (`PUT /ops/simulation`) and stored
    in the database, so that every process sees it. Without a stored value it falls back to the daily wave.
    It is a simulation and is labelled as such everywhere (source `controlled-simulation`)."""

    def __init__(self, db, fallback: Optional[EnergyFeed] = None) -> None:
        self.db, self.fallback = db, fallback or SimulatedFeed()

    def read(self, now: datetime) -> Reading:
        row = self.db.execute("SELECT intensity, price, renewable FROM simulation_signal WHERE id=1").fetchone()
        if row is None:
            return self.fallback.read(now)
        return Reading(row[0], row[1], bool(row[2]), iso(now))

    def set(self, intensity: Optional[float], price: Optional[float], renewable: bool, by: str, now: datetime) -> dict:
        with self.db:
            self.db.execute("DELETE FROM simulation_signal WHERE id=1")
            self.db.execute("INSERT INTO simulation_signal (id, intensity, price, renewable, set_by, set_at) VALUES (1, ?, ?, ?, ?, ?)",
                            (intensity, price, 1 if renewable else 0, by, iso(now)))
        return self.state()

    def clear(self) -> None:
        with self.db:
            self.db.execute("DELETE FROM simulation_signal WHERE id=1")

    def state(self) -> dict:
        row = self.db.execute("SELECT intensity, price, renewable, set_by, set_at FROM simulation_signal WHERE id=1").fetchone()
        return {"active": row is not None, **({} if row is None else dict(zip(("intensity", "price", "renewable", "set_by", "set_at"), (row[0], row[1], bool(row[2]), row[3], row[4]))))}


class ElectricityMapsFeed:
    """Latest carbon intensity from Electricity Maps (`/v3/carbon-intensity/latest?zone=..`, header `auth-token`).
    Price and renewable flag are not part of this call. Not tested against the live service (needs a token)."""

    def __init__(self, token: str, zone: str, opener: Callable = urllib.request.urlopen, base: str = "https://api.electricitymaps.com") -> None:
        self.token, self.zone, self.opener, self.base = token, zone, opener, base

    def read(self, now: datetime) -> Reading:
        req = urllib.request.Request(f"{self.base}/v3/carbon-intensity/latest?zone={self.zone}", headers={"auth-token": self.token})
        try:
            with self.opener(req, timeout=5) as resp:
                o = json.loads(resp.read().decode("utf-8"))
            return Reading(float(o["carbonIntensity"]), None, False, o.get("datetime"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise FeedError(str(exc)) from exc


class CarbonMonitor:
    def __init__(self, db, feed: EnergyFeed, metrics: Optional[Metrics] = None, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.db, self.feed, self.metrics, self.clock = db, feed, metrics if metrics is not None else Metrics(), clock

    def collect(self) -> dict:
        """One sensing step. Stores the reading (or the failure) and returns its status."""
        now = self.clock()
        try:
            r = self.feed.read(now)
        except FeedError as exc:
            return self._store(now, Reading(), "unavailable", str(exc))
        problems = []
        if r.intensity is not None and not (isinstance(r.intensity, (int, float)) and INTENSITY_RANGE[0] <= r.intensity <= INTENSITY_RANGE[1]):
            problems.append("intensity out of range")
        if r.price is not None and not (isinstance(r.price, (int, float)) and PRICE_RANGE[0] <= r.price <= PRICE_RANGE[1]):
            problems.append("price out of range")
        if r.intensity is None and r.price is None:
            problems.append("no signal in reading")
        if problems:
            return self._store(now, Reading(), "invalid", "; ".join(problems))
        return self._store(now, r, "ok", "")

    def _store(self, now: datetime, r: Reading, status: str, note: str) -> dict:
        with self.db:
            self.db.execute("INSERT INTO energy_samples (observed_at, intensity, price, renewable, status, source) VALUES (?, ?, ?, ?, ?, ?)",
                            (r.observed_at or iso(now), r.intensity, r.price, 1 if r.renewable else 0, status, note or type(self.feed).__name__))
        self.metrics[f"signal_samples_{status}"] += 1
        return {"status": status, "note": note, "intensity": r.intensity, "price": r.price, "renewable": r.renewable}

    def latest(self) -> dict:
        """Newest valid value of each signal with its age in minutes (None if there is none)."""
        out: dict = {"renewable": False}
        for name in ("intensity", "price"):
            row = self.db.execute(f"SELECT {name}, observed_at FROM energy_samples WHERE status='ok' AND {name} IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
            out[name], out[f"{name}_at"] = (row[0], row[1]) if row else (None, None)
        row = self.db.execute("SELECT renewable, observed_at FROM energy_samples WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            out["renewable"], out["renewable_at"] = bool(row[0]), row[1]
        return out


def age_minutes(ts: Optional[str], now: datetime) -> Optional[float]:
    if ts is None:
        return None
    dt = datetime.fromisoformat(ts)
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 60
