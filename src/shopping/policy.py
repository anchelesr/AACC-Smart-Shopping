"""Policy Engine: turns the two energy signals into an operating mode (GREEN, AMBER, RED) and a placement target.

Rules (docs/carbon-adaptation.md): each signal has a class; the mode is the more restrictive class; a class rises
only after N consecutive samples above its threshold and falls only when the value is below the threshold by a
margin (hysteresis); renewable energy forces GREEN with the eco pool; a signal without a valid sample for longer
than the stale limit is ignored, and with no signal at all the mode is GREEN with reason `signal_stale`; the
operator can override the mode for at most 24 hours. Policies are immutable versions, so a change needs no
redeployment. The decision is stored and published by core.PolicyEngine.decide().
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from events.bus import EventBus
from events.consumer import Metrics

from . import core
from .energy import CarbonMonitor, age_minutes, iso

GREEN, AMBER, RED = "GREEN", "AMBER", "RED"
LEVEL_MODE = {0: GREEN, 1: AMBER, 2: RED}
MODE_LEVEL = {v: k for k, v in LEVEL_MODE.items()}


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Policy:
    carbon_amber: float = 300.0           # gCO2e/kWh
    carbon_red: float = 450.0
    price_amber: float = 0.20             # EUR/kWh
    price_red: float = 0.30
    margin: float = 0.10                  # a class falls only below threshold * (1 - margin)
    consecutive: int = 2                  # samples above a threshold before a class rises
    stale_minutes: int = 30
    override_max_hours: int = 24
    dwell_minutes: int = 15               # placement: minimum time between pool changes
    deadline_hours: int = 24              # forecast job deadline window

    def validate(self) -> "Policy":
        if not 0 < self.carbon_amber < self.carbon_red or not 0 < self.price_amber < self.price_red:
            raise PolicyError("thresholds must be positive and ascending (AMBER below RED) for both signals")
        if not 0 <= self.margin <= 0.30:
            raise PolicyError("margin must be between 0 and 0.30")
        if not 1 <= self.consecutive <= 10:
            raise PolicyError("consecutive samples must be between 1 and 10")
        if not 1 <= self.stale_minutes <= 1440:
            raise PolicyError("stale limit must be 1-1440 minutes")
        if not 1 <= self.deadline_hours <= 72:
            raise PolicyError("deadline must be 1-72 hours")
        if not 1 <= self.override_max_hours <= 24:
            raise PolicyError("override limit must be at most 24 hours")
        if not 0 <= self.dwell_minutes <= 1440:
            raise PolicyError("dwell time must be 0-1440 minutes")
        return self


def audit(db, actor: str, action: str, detail: str, now: datetime) -> None:
    db.execute("INSERT INTO ops_audit (at, actor, action, detail) VALUES (?, ?, ?, ?)", (iso(now), actor, action, detail))


class PolicyStore:
    """Immutable policy versions; version 1 is the default (seeded from the configuration in Git)."""

    def __init__(self, db, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), initial: Optional[Policy] = None) -> None:
        self.db, self.clock, self.initial = db, clock, initial or Policy()

    def current(self) -> tuple[int, Policy]:
        row = self.db.execute("SELECT version, policy FROM policy_versions ORDER BY version DESC LIMIT 1").fetchone()
        if row is None:
            try:
                self.save(self.initial, "system", seed=True)
            except sqlite3.IntegrityError:                         # another process seeded version 1 first
                pass
            row = self.db.execute("SELECT version, policy FROM policy_versions ORDER BY version DESC LIMIT 1").fetchone()
        return row[0], Policy(**json.loads(row[1]))

    def save(self, policy: Policy, author: str, seed: bool = False) -> int:
        policy.validate()
        row = self.db.execute("SELECT COALESCE(MAX(version), 0) FROM policy_versions").fetchone()
        version = row[0] + 1
        now = self.clock()
        with self.db:
            self.db.execute("INSERT INTO policy_versions (version, created_at, created_by, policy) VALUES (?, ?, ?, ?)",
                            (version, iso(now), author, json.dumps(asdict(policy), sort_keys=True)))
            self.db.execute("UPDATE operating_mode_state SET policy_version=? WHERE id=1", (version,))
            audit(self.db, author, "policy.save", f"version {version}", now)
        return version

    def history(self) -> list[dict]:
        return [{"version": v, "created_at": c, "created_by": a, "policy": json.loads(p)}
                for v, c, a, p in self.db.execute("SELECT version, created_at, created_by, policy FROM policy_versions ORDER BY version DESC")]


def next_level(level: int, value: float, amber: float, red: float, margin: float, pending_level: int, pending_count: int,
               consecutive: int) -> tuple[int, int, int]:
    """Hysteresis for one signal. Returns (level, pending_level, pending_count)."""
    up = 2 if value > red else 1 if value > amber else 0
    if up > level:                                         # candidate rise: needs consecutive samples
        pending_level = up if pending_count == 0 else min(pending_level, up)
        pending_count += 1
        if pending_count >= consecutive:
            return pending_level, 0, 0
        return level, pending_level, pending_count
    amber_exit, red_exit = amber * (1 - margin), red * (1 - margin)
    down = 2 if value > red_exit else 1 if value > amber_exit else 0
    if level == 1:
        down = min(down, 1)
    if down < level:                                       # fall only below the threshold by the margin
        return down, 0, 0
    return level, 0, 0


class PolicyEngine(core.PolicyEngine):
    """Evaluates the signals and, if the decision changed, stores it and publishes mode.changed."""

    def __init__(self, db, bus: EventBus, metrics: Metrics, monitor: CarbonMonitor, store: Optional[PolicyStore] = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        super().__init__(db, bus, metrics)
        self.monitor, self.clock = monitor, clock
        self.store = store or PolicyStore(db, clock)

    # ---- operator override (FR-12)
    def set_override(self, mode: str, hours: float, actor: str) -> dict:
        if mode not in MODE_LEVEL:
            raise PolicyError("mode must be GREEN, AMBER or RED")
        _, policy = self.store.current()
        if not 0 < hours <= policy.override_max_hours:
            raise PolicyError(f"an override lasts at most {policy.override_max_hours} hours")
        now = self.clock()
        expires = iso(now + timedelta(hours=hours))
        with self.db:
            self.db.execute("DELETE FROM mode_override")
            self.db.execute("INSERT INTO mode_override (id, mode, expires_at, set_by, set_at) VALUES (1, ?, ?, ?, ?)", (mode, expires, actor, iso(now)))
            audit(self.db, actor, "mode.override", f"{mode} until {expires}", now)
        return {"mode": mode, "expires_at": expires, "set_by": actor}

    def clear_override(self, actor: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM mode_override")
            audit(self.db, actor, "mode.override.clear", "", self.clock())

    def active_override(self, now: datetime) -> Optional[dict]:
        row = self.db.execute("SELECT mode, expires_at, set_by FROM mode_override WHERE id=1").fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(row[1]) <= now:           # expired by itself
            with self.db:
                self.db.execute("DELETE FROM mode_override")
            return None
        return {"mode": row[0], "expires_at": row[1], "set_by": row[2]}

    # ---- evaluation
    def _signal_level(self, name: str, value: Optional[float], at: Optional[str], now: datetime, policy: Policy) -> tuple[Optional[int], str]:
        age = age_minutes(at, now)
        if value is None or age is None or age > policy.stale_minutes:
            return None, "missing" if value is None else "stale"
        amber, red = (policy.carbon_amber, policy.carbon_red) if name == "intensity" else (policy.price_amber, policy.price_red)
        row = self.db.execute("SELECT level, pending_level, pending_count, last_sample FROM signal_state WHERE signal=?", (name,)).fetchone()
        level, pl, pc, seen = row if row else (0, 0, 0, 0)
        last = self.db.execute("SELECT id FROM energy_samples WHERE status='ok' AND " + name + " IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()[0]
        if last != seen:                                   # every stored sample is counted exactly once
            level, pl, pc = next_level(level, value, amber, red, policy.margin, pl, pc, policy.consecutive)
            with self.db:
                if row:
                    self.db.execute("UPDATE signal_state SET level=?, pending_level=?, pending_count=?, last_sample=? WHERE signal=?", (level, pl, pc, last, name))
                else:
                    self.db.execute("INSERT INTO signal_state (signal, level, pending_level, pending_count, last_sample) VALUES (?, ?, ?, ?, ?)", (name, level, pl, pc, last))
        return level, "ok"

    def evaluate(self) -> dict:
        now = self.clock()
        version, policy = self.store.current()
        s = self.monitor.latest()
        override = self.active_override(now)
        ci, ci_state = self._signal_level("intensity", s["intensity"], s["intensity_at"], now, policy)
        pr, pr_state = self._signal_level("price", s["price"], s["price_at"], now, policy)
        renewable = bool(s["renewable"]) and age_minutes(s.get("renewable_at"), now) is not None and age_minutes(s.get("renewable_at"), now) <= policy.stale_minutes
        self.metrics["signal_status_stale"] += (ci is None) + (pr is None)
        if override:
            mode, reason = override["mode"], f"override by {override['set_by']} until {override['expires_at']}"
            target = "eco" if mode != GREEN or renewable else "standard"
        elif ci is None and pr is None:
            mode, reason, target = GREEN, "signal_stale", "standard"
        elif renewable:
            mode, reason, target = GREEN, "renewable", "eco"
        else:
            levels = {"carbon": ci, "price": pr}
            top = max(v for v in levels.values() if v is not None)
            mode = LEVEL_MODE[top]
            if top == 0:
                reason = "signals within normal range" + ("" if None not in levels.values() else " (one signal unavailable)")
            else:
                cause = " and ".join(k for k, v in levels.items() if v == top)
                reason = f"{cause} signal at {mode}" + ("" if None not in levels.values() else " (other signal unavailable)")
            target = "standard" if mode == GREEN else "eco"
        changed = self.decide(mode, reason, target, iso(now))
        if changed:
            self.metrics["mode_changes_total"] += 1
        else:
            with self.db:                                                  # the reason may change without a mode change
                self.db.execute("UPDATE operating_mode_state SET reason=? WHERE id=1", (reason,))
        return {"mode": mode, "reason": reason, "placement_target": target, "changed": changed, "policy_version": version,
                "signals": {"intensity": s["intensity"], "price": s["price"], "renewable": renewable,
                            "intensity_state": ci_state, "price_state": pr_state}, "override": override}

    def state(self) -> dict:
        mode, reason, since, target, version = self.db.execute(
            "SELECT mode, reason, since, placement_target, policy_version FROM operating_mode_state WHERE id=1").fetchone()
        return {"mode": mode, "reason": reason, "since": since, "placement_target": target, "policy_version": version,
                "override": self.active_override(self.clock())}
