"""Prometheus exposition (text format 0.0.4) for the whole system.

State that every process must agree on (operating mode, signals, jobs, placement, model, assistant, estimated
energy and emissions) is read from the database at scrape time, so any replica answers with the same values and no
counter is lost when a pod is evicted and restarted. Only what is really per process is kept in memory: the HTTP
latency histogram and `shopping_process_info` (role and node of the pod that answers).

All energy and emission values are ESTIMATES from configured power factors and the carbon intensity of the
simulated or configured feed (docs/carbon-experiment.md); the metric names say so (`_estimated_`).
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Iterable, Optional

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
MODES = ("GREEN", "AMBER", "RED")
POOLS = ("standard", "eco")
JOB_STATES = ("queued", "running", "done", "failed")


def _esc(v) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt(v: float) -> str:
    return repr(float(v)) if v == v else "NaN"


class Histogram:
    """Request latency by route template and status class (in process, thread safe)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: dict[tuple[str, str], list] = {}

    def observe(self, route: str, status: int, seconds: float) -> None:
        key = (route, f"{status // 100}xx")
        with self.lock:
            counts, total, n = self.data.setdefault(key, [[0] * len(BUCKETS), 0.0, 0])
            for i, b in enumerate(BUCKETS):
                if seconds <= b:
                    counts[i] += 1
            self.data[key][1] += seconds
            self.data[key][2] += 1

    def lines(self, name: str) -> list[str]:
        out = [f"# HELP {name} HTTP request latency in seconds.", f"# TYPE {name} histogram"]
        with self.lock:
            for (route, cls), (counts, total, n) in sorted(self.data.items()):
                lab = f'route="{_esc(route)}",status="{cls}"'
                out += [f'{name}_bucket{{{lab},le="{b}"}} {c}' for b, c in zip(BUCKETS, counts)]
                out += [f'{name}_bucket{{{lab},le="+Inf"}} {n}', f"{name}_sum{{{lab}}} {_fmt(total)}", f"{name}_count{{{lab}}} {n}"]
        return out


class Exposition:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self._declared: set[str] = set()

    def add(self, name: str, kind: str, help_: str, samples: Iterable[tuple[dict, float]]) -> None:
        samples = list(samples)
        if name not in self._declared:
            self.lines += [f"# HELP {name} {help_}", f"# TYPE {name} {kind}"]
            self._declared.add(name)
        for labels, value in samples:
            lab = ",".join(f'{k}="{_esc(v)}"' for k, v in labels.items())
            self.lines.append(f"{name}{{{lab}}} {_fmt(value)}" if lab else f"{name} {_fmt(value)}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _age(ts: Optional[str], now: datetime) -> Optional[float]:
    if not ts:
        return None
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - dt).total_seconds())


def render(app, http: Optional[Histogram] = None) -> str:
    x, now = Exposition(), app.clock()
    one = lambda q, *a: app.db.execute(q, a).fetchone()
    rows = lambda q, *a: app.db.execute(q, a).fetchall()
    with app.lock:
        try:
            one("SELECT 1")
            up = 1
        except Exception:
            up = 0
        x.add("shopping_database_up", "gauge", "1 if the database answers.", [({}, up)])
        if not up:
            return x.text()
        role = os.environ.get("SHOPPING_ROLE", "all")
        x.add("shopping_process_info", "gauge", "Role and node of the process that answered this scrape.",
              [({"role": role, "node": os.environ.get("NODE_NAME", "unknown"), "pod": os.environ.get("POD_NAME", "unknown")}, 1)])

        # ---- operating mode and placement
        mode, reason, since, target, pv = one("SELECT mode, reason, since, placement_target, policy_version FROM operating_mode_state WHERE id=1")
        x.add("shopping_operating_mode", "gauge", "Current operating mode (1 = active).", [({"mode": m}, 1 if m == mode else 0) for m in MODES])
        x.add("shopping_operating_mode_age_seconds", "gauge", "Seconds since the last mode change.", [({}, _age(since, now) or 0.0)])
        x.add("shopping_placement_target", "gauge", "Node pool that flexible workloads should run on (1 = target).", [({"pool": p}, 1 if p == target else 0) for p in POOLS])
        x.add("shopping_policy_version", "gauge", "Version of the active energy policy.", [({}, pv)])
        o = one("SELECT mode FROM mode_override WHERE id=1 AND expires_at > ?", now.isoformat(timespec="seconds"))
        x.add("shopping_mode_override_active", "gauge", "1 while an operator override is in force.", [({}, 1 if o else 0)])
        x.add("shopping_placement_decisions_total", "counter", "Placement decisions by outcome (stored changes only; repeats are collapsed).",
              [({"outcome": r[0]}, r[1]) for r in rows("SELECT outcome, COUNT(*) FROM placement_decisions GROUP BY outcome")])

        # ---- signals
        sig = app.monitor.latest()
        if sig["intensity"] is not None:
            x.add("shopping_carbon_intensity_gco2e_per_kwh", "gauge", "Latest valid carbon intensity of the electricity (simulated unless a real feed is configured).", [({}, sig["intensity"])])
            x.add("shopping_signal_age_seconds", "gauge", "Age of the latest valid sample of each signal.",
                  [({"signal": s}, _age(sig.get(f"{s}_at"), now)) for s in ("intensity", "price") if sig.get(f"{s}_at")])
        if sig["price"] is not None:
            x.add("shopping_electricity_price_eur_per_kwh", "gauge", "Latest valid electricity price.", [({}, sig["price"])])
        x.add("shopping_renewable_available", "gauge", "1 if the renewable window is open.", [({}, 1 if sig["renewable"] else 0)])
        x.add("shopping_signal_samples_total", "counter", "Collected samples by status.",
              [({"status": r[0]}, r[1]) for r in rows("SELECT status, COUNT(*) FROM energy_samples GROUP BY status")])
        sim = one("SELECT 1 FROM simulation_signal WHERE id=1")
        x.add("shopping_signal_simulation_override", "gauge", "1 while the signal is set by the operator (demonstration).", [({}, 1 if sim else 0)])

        # ---- forecast jobs
        counts = dict(rows("SELECT status, COUNT(*) FROM forecast_jobs GROUP BY status"))
        x.add("shopping_forecast_jobs", "gauge", "Forecast jobs by state.", [({"state": s}, counts.get(s, 0)) for s in JOB_STATES])
        x.add("shopping_forecast_jobs_overdue", "gauge", "Open jobs past their deadline (must be 0 in normal operation).",
              [({}, one("SELECT COUNT(*) FROM forecast_jobs WHERE status IN ('queued','running') AND deadline < ?", now.isoformat(timespec="seconds"))[0])])
        oldest = one("SELECT MIN(created_at) FROM forecast_jobs WHERE status='queued'")[0]
        x.add("shopping_forecast_oldest_queued_age_seconds", "gauge", "Age of the oldest waiting job.", [({}, _age(oldest, now) or 0.0)])
        last = one("SELECT MAX(generated_at) FROM forecasts WHERE shadow=0")[0]
        if last:
            x.add("shopping_forecast_age_seconds", "gauge", "Age of the newest stored forecast.", [({}, _age(last, now))])
        x.add("shopping_job_decisions_total", "counter", "Scheduler decisions by kind and mode.",
              [({"decision": r[0], "mode": r[1] or "none"}, r[2]) for r in rows("SELECT decision, mode, COUNT(*) FROM job_log GROUP BY decision, mode")])
        e = one("SELECT COALESCE(SUM(kwh),0), COALESCE(SUM(gco2e),0), COUNT(*) FROM job_log WHERE decision='run'")
        x.add("shopping_job_estimated_energy_kwh_total", "counter", "ESTIMATED energy of forecast jobs (configured power x duration).", [({}, e[0])])
        x.add("shopping_job_estimated_emissions_gco2e_total", "counter", "ESTIMATED emissions of forecast jobs (energy x intensity at start).", [({}, e[1])])
        x.add("shopping_job_estimated_energy_by_mode_kwh_total", "counter", "ESTIMATED job energy by operating mode.",
              [({"mode": r[0] or "none"}, r[1]) for r in rows("SELECT mode, COALESCE(SUM(kwh),0) FROM job_log WHERE decision='run' GROUP BY mode")])
        x.add("shopping_model_active", "gauge", "Active forecast model (1) and the other registered ones (0).",
              [({"model": r[0]}, r[1]) for r in rows("SELECT model_id, active FROM model_registry")])
        x.add("shopping_model_mae", "gauge", "Backtest MAE (EUR) by model.", [({"model": r[0]}, r[1]) for r in rows("SELECT model_id, mae FROM model_registry WHERE mae IS NOT NULL")])
        x.add("shopping_model_worse_streak", "gauge", "Consecutive live checks in which the active model was worse than the baseline.",
              [({"model": r[0]}, r[1]) for r in rows("SELECT model_id, worse_streak FROM model_registry")])

        # ---- assistant (LLM gateway)
        x.add("shopping_router_decisions_total", "counter", "Assistant router decisions by route and mode.",
              [({"route": r[0] or "none", "mode": r[1] or "none"}, r[2]) for r in rows("SELECT route, mode, COUNT(*) FROM traces GROUP BY route, mode")])
        t = one("SELECT COALESCE(SUM(tokens_in+tokens_out),0), COALESCE(SUM(est_wh),0), COALESCE(SUM(est_gco2e),0), COALESCE(SUM(est_cost_eur),0), COALESCE(SUM(flagged),0) FROM traces")
        x.add("shopping_assistant_tokens_total", "counter", "Tokens used by the assistant.", [({}, t[0])])
        x.add("shopping_assistant_estimated_energy_wh_total", "counter", "ESTIMATED energy of assistant answers.", [({}, t[1])])
        x.add("shopping_assistant_estimated_emissions_gco2e_total", "counter", "ESTIMATED emissions of assistant answers.", [({}, t[2])])
        x.add("shopping_assistant_estimated_cost_eur_total", "counter", "ESTIMATED cost of assistant answers.", [({}, t[3])])
        x.add("shopping_assistant_flagged_total", "counter", "Answers sent to the review queue.", [({}, t[4])])
        x.add("shopping_review_queue_pending", "gauge", "Review items without a decision.", [({}, one("SELECT COUNT(*) FROM review_queue WHERE decision IS NULL")[0])])
        x.add("shopping_assistant_by_model_total", "counter", "Assistant answers by model (shows the model exchange).",
              [({"model": r[0] or "none", "mode": r[1] or "none"}, r[2]) for r in rows("SELECT model, mode, COUNT(*) FROM traces GROUP BY model, mode")])
        b = one("SELECT tokens_used, large_used FROM token_budget WHERE day=?", now.date().isoformat())
        x.add("shopping_token_budget_used_today", "gauge", "Tokens used today (total, large model).", [({"kind": "total"}, b[0] if b else 0), ({"kind": "large"}, b[1] if b else 0)])

        # ---- data
        x.add("shopping_import_runs_total", "counter", "Price import runs by status.",
              [({"status": r[0]}, r[1]) for r in rows("SELECT status, COUNT(*) FROM import_runs GROUP BY status")])
        x.add("shopping_observations", "gauge", "Stored price observations.", [({}, one("SELECT COUNT(*) FROM observations")[0])])

        # ---- in-process counters of the components (reset on restart; use rate())
        proc = {}
        for k, v in app.metrics.items():
            name, _, labels = k.partition("{")
            proc.setdefault(name, []).append((dict(p.split("=", 1) for p in labels.rstrip("}").split(",")) if labels else {}, v))
        for name, samples in sorted(proc.items()):
            x.add(f"shopping_process_{name}", "counter", "In-process counter of this replica (resets on restart).", samples)
    if http is not None:
        x.lines += http.lines("shopping_http_request_duration_seconds")
    return x.text()
