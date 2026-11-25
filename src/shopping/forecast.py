"""Evidence, Forecast Worker and Model Evaluator (docs/ai-architecture.md, section 1).

Series: one value per day, the lowest valid offer of that day; gaps up to 3 days are carried forward, a longer gap
makes the series ineligible (`insufficient_data`). Models: the baseline repeats the last daily value for 7 days;
the one candidate is damped Holt linear smoothing, a classical method that needs no training by us (its two
smoothing parameters are fitted on the series at run time). The candidate becomes the active model only if its
backtest MAE is not worse than the baseline's (adoption gate); if its live MAE is worse for three consecutive
evaluations, the registry falls back to the baseline.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from .advice import Evidence, FRESH, Forecast, MISSING, STALE
from .catalog import lowest_offer
from .energy import iso

HORIZON = 7
WINDOW_DAYS = 30
MIN_DAYS = 10                 # distinct observation days required for a reference (specification)
MAX_GAP = 3
FORECAST_MAX_AGE = timedelta(hours=48)
BASELINE, CANDIDATE = "baseline-last-value", "damped-holt"
PHI = 0.9                     # damping of the trend


# ----------------------------------------------------------------------------- series and evidence
def daily_series(db, laptop_id: str, now: datetime, window: int = WINDOW_DAYS) -> list[tuple[date, float]]:
    """Daily lowest offer for the last `window` days (observation days only, no filling)."""
    start = (now - timedelta(days=window)).date().isoformat()
    best: dict[date, float] = {}
    for observed_at, price in db.execute("SELECT observed_at, price FROM observations WHERE laptop_id=? AND observed_at >= ? ORDER BY observed_at", (laptop_id, start)):
        dt = datetime.fromisoformat(observed_at)
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if dt > now:
            continue
        d = dt.astimezone(timezone.utc).date()
        best[d] = min(price, best.get(d, price))
    return sorted(best.items())


def fill_gaps(series: list[tuple[date, float]]) -> Optional[list[float]]:
    """Dense daily values (carry forward up to MAX_GAP days); None if a longer gap exists."""
    if not series:
        return None
    out, prev = [], series[0]
    out.append(prev[1])
    for d, p in series[1:]:
        gap = (d - prev[0]).days - 1
        if gap > MAX_GAP:
            return None
        out.extend([prev[1]] * gap)
        out.append(p)
        prev = (d, p)
    return out


def evidence_for(db, laptop_id: str, now: datetime) -> Evidence:
    """Median of the daily lowest offers over 30 days (at least 10 distinct days) against the current lowest offer."""
    offer = lowest_offer(db, laptop_id)
    brand = db.execute("SELECT brand FROM products WHERE laptop_id=?", (laptop_id,)).fetchone()
    brand = brand[0] if brand else None
    series = daily_series(db, laptop_id, now)
    if offer is None or len(series) < MIN_DAYS:
        return Evidence(False, None, offer["price"] if offer else None, brand)
    ref = statistics.median(p for _, p in series)
    return Evidence(True, offer["price"] / ref - 1, offer["price"], brand)


# ----------------------------------------------------------------------------- models
def baseline_predict(values: list[float], horizon: int = HORIZON) -> list[float]:
    return [values[-1]] * horizon


def holt_fit(values: list[float]) -> tuple[float, float, float, float]:
    """Grid-search alpha and beta on one-step in-sample error; returns (alpha, beta, level, trend)."""
    best = None
    for a in (0.2, 0.4, 0.6, 0.8):
        for b in (0.05, 0.1, 0.2, 0.4):
            level, trend, sse = values[0], (values[1] - values[0]) if len(values) > 1 else 0.0, 0.0
            for y in values[1:]:
                pred = level + PHI * trend
                sse += (y - pred) ** 2
                new_level = a * y + (1 - a) * pred
                trend = b * (new_level - level) + (1 - b) * PHI * trend
                level = new_level
            if best is None or sse < best[0]:
                best = (sse, a, b, level, trend)
    return best[1], best[2], best[3], best[4]


def holt_predict(values: list[float], horizon: int = HORIZON) -> list[float]:
    if len(values) < 4:
        return baseline_predict(values, horizon)
    _, _, level, trend = holt_fit(values)
    out, damp = [], 0.0
    for h in range(1, horizon + 1):
        damp += PHI ** h
        out.append(level + damp * trend)
    return out


MODELS: dict[str, Callable[[list[float], int], list[float]]] = {BASELINE: baseline_predict, CANDIDATE: holt_predict}


def backtest(values: list[float], origins: int = 5, min_train: int = 12) -> Optional[dict[str, float]]:
    """Rolling origin: forecast 7 days ahead from several past origins; MAE per model, None if the series is too short."""
    errs: dict[str, list[float]] = {m: [] for m in MODELS}
    for k in range(origins):
        cut = len(values) - HORIZON - k
        if cut < min_train:
            break
        train, actual = values[:cut], values[cut:cut + HORIZON]
        for name, fn in MODELS.items():
            errs[name].extend(abs(p - a) for p, a in zip(fn(train, HORIZON), actual))
    if not errs[BASELINE]:
        return None
    return {m: sum(e) / len(e) for m, e in errs.items()}


# ----------------------------------------------------------------------------- registry
class ModelRegistry:
    def __init__(self, db) -> None:
        self.db = db
        with db:
            for m in MODELS:
                db.execute("INSERT OR IGNORE INTO model_registry (model_id, active) VALUES (?, ?)", (m, 1 if m == BASELINE else 0))

    def active(self) -> str:
        row = self.db.execute("SELECT model_id FROM model_registry WHERE active=1 ORDER BY model_id LIMIT 1").fetchone()
        return row[0] if row else BASELINE

    def set_active(self, model_id: str, pinned: bool = False, note: str = "") -> None:
        if model_id not in MODELS:
            raise ValueError(f"unknown model {model_id!r}")
        with self.db:
            self.db.execute("UPDATE model_registry SET active=0")
            self.db.execute("UPDATE model_registry SET active=1, pinned=?, note=? WHERE model_id=?", (1 if pinned else 0, note, model_id))

    def pinned(self) -> bool:
        return bool(self.db.execute("SELECT 1 FROM model_registry WHERE active=1 AND pinned=1").fetchone())

    def rows(self) -> list[dict]:
        return [dict(zip(("model_id", "active", "pinned", "mae", "baseline_mae", "worse_streak", "evaluated_at", "note"), r)) for r in
                self.db.execute("SELECT model_id, active, pinned, mae, baseline_mae, worse_streak, evaluated_at, note FROM model_registry ORDER BY model_id")]


# ----------------------------------------------------------------------------- worker
class ForecastWorker:
    """Runs one forecast job: series -> both models -> output guardrail -> store (active model visible, the other as shadow)."""

    def __init__(self, db, registry: Optional[ModelRegistry] = None) -> None:
        self.db, self.registry = db, registry or ModelRegistry(db)

    def run_job(self, laptop_id: str, now: datetime) -> dict:
        series = daily_series(self.db, laptop_id, now)
        values = fill_gaps(series) if len(series) >= MIN_DAYS else None
        generated = iso(now)
        if values is None:
            self._store(laptop_id, generated, self.registry.active(), 0, None, None, None, "INSUFFICIENT", now)
            return {"outcome": "insufficient_data", "laptop_id": laptop_id}
        lo, hi = 0.5 * min(values), 2.0 * max(values)
        active = self.registry.active()
        stored = {}
        for name, fn in MODELS.items():
            preds = [round(p, 2) for p in fn(values, HORIZON)]
            if not all(p > 0 and lo <= p <= hi for p in preds):               # output guardrail
                if name == active:
                    return {"outcome": "guardrail_failed", "laptop_id": laptop_id, "model": name}   # previous forecast stays visible; the job is retried
                continue
            stored[name] = preds
        if active not in stored:
            return {"outcome": "guardrail_failed", "laptop_id": laptop_id, "model": active}
        for name, preds in stored.items():
            self._store(laptop_id, generated, name, 0 if name == active else 1, values[-1], preds, preds[-1] / values[-1] - 1, "FRESH", now)
        return {"outcome": "ok", "laptop_id": laptop_id, "model": active, "change": stored[active][-1] / values[-1] - 1}

    def _store(self, laptop_id, generated, model, shadow, base, preds, change, status, now) -> None:
        with self.db:
            self.db.execute("""INSERT INTO forecasts (laptop_id, generated_at, model_id, shadow, base_price, prices, change, status, target_day)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (laptop_id, generated, model, shadow, base, json.dumps(preds) if preds else None, change, status,
                             (now + timedelta(days=HORIZON)).date().isoformat()))
            if not shadow:
                self.db.execute("INSERT INTO forecast_runs (laptop_id, generated_at) VALUES (?, ?)", (laptop_id, generated))


def forecast_for(db, laptop_id: str, now: datetime) -> tuple[Forecast, dict]:
    """The stored forecast for the shopper: FRESH within 48 h, STALE when older, MISSING if there is none."""
    row = db.execute("""SELECT generated_at, model_id, prices, change, status, base_price FROM forecasts
                        WHERE laptop_id=? AND shadow=0 AND status='FRESH' ORDER BY id DESC LIMIT 1""", (laptop_id,)).fetchone()
    if row is None:
        return Forecast(MISSING, None), {"status": MISSING, "horizon_days": HORIZON}
    gen = datetime.fromisoformat(row[0])
    status = FRESH if now - gen <= FORECAST_MAX_AGE else STALE
    detail = {"status": status, "horizon_days": HORIZON, "model_id": row[1], "generated_at": row[0], "prices": json.loads(row[2]),
              "change": row[3], "caveat": "Model estimates are uncertain"}
    return Forecast(status, row[3]), detail


# ----------------------------------------------------------------------------- evaluator
class ModelEvaluator:
    """Optional batch (deferred in AMBER and RED by the scheduler): backtest, adoption gate, live scoring, fallback."""

    def __init__(self, db, registry: Optional[ModelRegistry] = None, live_streak_limit: int = 3) -> None:
        self.db, self.registry, self.limit = db, registry or ModelRegistry(db), live_streak_limit

    def evaluate(self, now: datetime) -> dict:
        report = {"backtest": self._backtest(now), "live": self._live(now)}
        return report

    def _backtest(self, now: datetime) -> dict:
        totals: dict[str, list[float]] = {m: [] for m in MODELS}
        laptops = [r[0] for r in self.db.execute("SELECT laptop_id FROM products ORDER BY laptop_id")]
        used = 0
        for lid in laptops:
            series = daily_series(self.db, lid, now)
            values = fill_gaps(series) if len(series) >= MIN_DAYS else None
            res = backtest(values) if values else None
            if res:
                used += 1
                for m, v in res.items():
                    totals[m].append(v)
        if not used:
            return {"laptops": 0, "note": "no series long enough for a backtest; no model change"}
        mae = {m: sum(v) / len(v) for m, v in totals.items()}
        accepted = mae[CANDIDATE] <= mae[BASELINE]                                   # adoption gate
        with self.db:
            for m in MODELS:
                self.db.execute("UPDATE model_registry SET mae=?, baseline_mae=?, evaluated_at=? WHERE model_id=?", (mae[m], mae[BASELINE], iso(now), m))
        if not self.registry.pinned():
            self.registry.set_active(CANDIDATE if accepted else BASELINE, note="backtest gate " + ("passed" if accepted else "failed"))
        return {"laptops": used, "mae": mae, "candidate_accepted": accepted,
                "note": "few origins on a short series: differences may be within noise", "active": self.registry.active()}

    def _live(self, now: datetime) -> dict:
        """Score stored forecasts whose target day has arrived against the realised daily lowest price."""
        errs: dict[str, list[float]] = {m: [] for m in MODELS}
        rows = self.db.execute("SELECT id, laptop_id, model_id, prices, target_day FROM forecasts WHERE realised IS NULL AND prices IS NOT NULL AND target_day <= ?",
                               (now.date().isoformat(),)).fetchall()
        for fid, lid, model, prices, target_day in rows:
            realised = self._realised(lid, target_day, now)
            if realised is None:
                continue
            with self.db:
                self.db.execute("UPDATE forecasts SET realised=?, scored_at=? WHERE id=?", (realised, iso(now), fid))
            errs[model].append(abs(json.loads(prices)[-1] - realised))
        n = len(errs[CANDIDATE])
        if not n or not errs[BASELINE]:
            return {"scored": sum(len(v) for v in errs.values()), "note": "not enough realised prices yet"}
        cand, base = sum(errs[CANDIDATE]) / n, sum(errs[BASELINE]) / len(errs[BASELINE])
        worse = cand > base
        with self.db:
            self.db.execute("INSERT INTO drift_checks (checked_at, model_id, live_mae, baseline_mae, n, worse) VALUES (?, ?, ?, ?, ?, ?)",
                            (iso(now), CANDIDATE, cand, base, n, 1 if worse else 0))
            streak = self.db.execute("SELECT worse_streak FROM model_registry WHERE model_id=?", (CANDIDATE,)).fetchone()[0]
            streak = streak + 1 if worse else 0
            self.db.execute("UPDATE model_registry SET worse_streak=? WHERE model_id=?", (streak, CANDIDATE))
        fell_back = False
        if streak >= self.limit and self.registry.active() == CANDIDATE and not self.registry.pinned():
            self.registry.set_active(BASELINE, note=f"fallback: live MAE worse than baseline {streak} times in a row")
            fell_back = True
        return {"scored": n, "live_mae": cand, "baseline_mae": base, "worse_streak": streak, "fell_back": fell_back}

    def _realised(self, laptop_id: str, day: str, now: datetime) -> Optional[float]:
        row = self.db.execute("SELECT MIN(price) FROM observations WHERE laptop_id=? AND observed_at >= ? AND observed_at < ?",
                              (laptop_id, day, (date.fromisoformat(day) + timedelta(days=1)).isoformat())).fetchone()
        return row[0] if row and row[0] is not None else None

    def drift(self) -> list[dict]:
        return [dict(zip(("checked_at", "model_id", "live_mae", "baseline_mae", "n", "worse"), r)) for r in self.db.execute(
            "SELECT checked_at, model_id, live_mae, baseline_mae, n, worse FROM drift_checks ORDER BY id DESC LIMIT 20")]
