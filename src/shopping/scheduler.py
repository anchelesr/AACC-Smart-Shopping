"""Job Scheduler: leased forecast jobs that adapt to the operating mode (docs/carbon-adaptation.md).

GREEN: run every due job, concurrency 3. AMBER: run a job only when at most half of its deadline window is left,
concurrency 1. RED: wait for the deadline, concurrency 1. The deadline (24 h by default, set when the job is
created and never reset by later price changes) wins in every mode, also over the concurrency cap. A running job
holds a lease; a job whose lease expired (worker crashed, pod evicted) is requeued. Every decision, run and its
estimated energy and carbon are written to job_log (feedback, NFR-10).

Energy is ESTIMATED from a configured average power per pool class and the measured duration (assumption).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from events.consumer import Metrics

from .core import JobScheduler
from .energy import iso
from .forecast import ForecastWorker, ModelEvaluator
from .policy import Policy

CONCURRENCY = {"GREEN": 3, "AMBER": 1, "RED": 1}
POWER_W = {"standard": 65.0, "eco": 45.0}            # assumed average power of a worker per pool class
LEASE = timedelta(minutes=5)
RETRY_BACKOFF = timedelta(minutes=10)
MAX_ATTEMPTS = 3
EVALUATION_INTERVAL = timedelta(days=1)
MAX_OPTIONAL_DEFERRAL = timedelta(days=7)


def _dt(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class Scheduler(JobScheduler):
    def __init__(self, db, worker: ForecastWorker, evaluator: ModelEvaluator, policy_source: Callable[[], Policy], mode_reader,
                 signals: Callable[[], dict], metrics: Optional[Metrics] = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 timer: Callable[[], float] = time.perf_counter, assumed_duration_s: Optional[float] = None, immediate: bool = False) -> None:
        super().__init__(db)
        # assumed_duration_s: the demonstration jobs take milliseconds; with a value set, the energy estimate uses it instead of the
        #   measured time (an ASSUMPTION that stands for a production-size job, see docs/carbon-experiment.md)
        # immediate: baseline for the carbon experiment only: every job runs as soon as it exists, whatever the mode
        self.assumed_duration_s, self.immediate = assumed_duration_s, immediate
        self.worker, self.evaluator, self.policy_source, self.mode_reader, self.signals = worker, evaluator, policy_source, mode_reader, signals
        self.metrics = metrics if metrics is not None else Metrics()
        self.clock, self.timer = clock, timer

    # ---- creation: the deadline is fixed when the job is created
    def enqueue_or_keep(self, laptop_id: str) -> bool:
        now = self.clock()
        deadline = now + timedelta(hours=self.policy_source().deadline_hours)
        cur = self.db.execute("INSERT OR IGNORE INTO forecast_jobs (laptop_id, status, created_at, deadline, attempts) VALUES (?, 'queued', ?, ?, 0)",
                              (laptop_id, iso(now), iso(deadline)))
        self.db.commit()
        return bool(cur.rowcount)

    # ---- leases
    def recover_expired(self, now: datetime) -> int:
        n = 0
        for jid, laptop, attempts in self.db.execute("SELECT id, laptop_id, attempts FROM forecast_jobs WHERE status='running' AND lease_until < ?", (iso(now),)).fetchall():
            with self.db:
                if attempts >= MAX_ATTEMPTS:
                    self.db.execute("UPDATE forecast_jobs SET status='failed', lease_until=NULL WHERE id=?", (jid,))
                else:
                    self.db.execute("UPDATE forecast_jobs SET status='queued', lease_until=NULL WHERE id=?", (jid,))
            self._log(jid, laptop, now, "recover", "lease expired", None)
            n += 1
        return n

    # ---- decision for one job
    def decision(self, job: dict, mode: str, now: datetime) -> tuple[str, str]:
        created, deadline = _dt(job["created_at"]), _dt(job["deadline"])
        if self.immediate:
            return "run", "immediate baseline"
        if now >= deadline:
            return "run", "deadline reached"
        if job["next_check"] and now < _dt(job["next_check"]):
            return "defer", "retry backoff"
        if mode == "GREEN":
            return "run", "mode GREEN"
        half = created + (deadline - created) / 2
        if mode == "AMBER":
            return ("run", "AMBER: at most half of the window left") if now >= half else ("defer", "AMBER: waits until half of the window is left")
        return "defer", "RED: waits for the deadline"

    def tick(self) -> dict:
        """One scheduling step: recover leases, decide, run as many jobs as the mode allows, run optional batches."""
        now = self.clock()
        mode, target = self.mode_reader.current()
        recovered = self.recover_expired(now)
        running = self.db.execute("SELECT COUNT(*) FROM forecast_jobs WHERE status='running'").fetchone()[0]
        capacity = max(0, CONCURRENCY[mode] - running)
        out = {"mode": mode, "recovered": recovered, "ran": [], "deferred": [], "failed": [], "optional": None}
        cols = ("id", "laptop_id", "created_at", "deadline", "next_check", "attempts")
        jobs = [dict(zip(cols, r)) for r in self.db.execute("SELECT id, laptop_id, created_at, deadline, next_check, attempts FROM forecast_jobs WHERE status='queued' ORDER BY deadline, id")]
        for job in jobs:
            action, reason = self.decision(job, mode, now)
            overdue = reason == "deadline reached" or self.immediate
            if action == "run" and not overdue and capacity <= 0:
                action, reason = "defer", f"concurrency limit {CONCURRENCY[mode]} reached"
            if action == "defer":
                out["deferred"].append(job["laptop_id"])
                self.metrics["jobs_deferred"] += 1
                self._log(job["id"], job["laptop_id"], now, "defer", reason, mode)
                continue
            if not overdue:
                capacity -= 1
            self._run(job, mode, target, reason, now, out)
        out["optional"] = self.run_optional(now, mode)
        return out

    def _run(self, job: dict, mode: str, target: str, reason: str, now: datetime, out: dict) -> None:
        if not self._claim(job, now):                                  # another worker took it: skip
            return
        started = self.timer()
        try:
            result = self.worker.run_job(job["laptop_id"], now)
            ok = result["outcome"] in ("ok", "insufficient_data")      # insufficient data is a result, not a failure
        except Exception as exc:                                       # a crashing job must not stop the scheduler
            result, ok = {"outcome": "error", "error": str(exc)}, False
        duration = self.timer() - started
        sig = self.signals()
        kwh = POWER_W.get(target, POWER_W["standard"]) * (self.assumed_duration_s or duration) / 3_600_000
        gco2e = kwh * sig["intensity"] if sig.get("intensity") is not None else None
        with self.db:
            if ok:
                self.db.execute("UPDATE forecast_jobs SET status='done', lease_until=NULL WHERE id=?", (job["id"],))
            else:
                attempts = job["attempts"] + 1                         # the claim already counted this attempt
                if attempts >= MAX_ATTEMPTS:
                    self.db.execute("UPDATE forecast_jobs SET status='failed', lease_until=NULL WHERE id=?", (job["id"],))
                else:
                    self.db.execute("UPDATE forecast_jobs SET status='queued', lease_until=NULL, next_check=? WHERE id=?", (iso(now + RETRY_BACKOFF), job["id"]))
        self._log(job["id"], job["laptop_id"], now, "run", reason, mode, sig.get("intensity"), kwh, gco2e, duration, result["outcome"])
        (out["ran"] if ok else out["failed"]).append(job["laptop_id"])
        self.metrics["jobs_run" if ok else "jobs_failed"] += 1

    def _claim(self, job: dict, now: datetime) -> bool:
        with self.db:
            cur = self.db.execute("UPDATE forecast_jobs SET status='running', lease_until=?, attempts=attempts+1 WHERE id=? AND status='queued'",
                                  (iso(now + LEASE), job["id"]))
        return bool(cur.rowcount)

    def _log(self, job_id, laptop, now, decision, reason, mode, intensity=None, kwh=None, gco2e=None, duration=None, outcome=None) -> None:
        if decision in ("defer", "defer_optional"):                    # a repeated identical deferral is counted in metrics, not logged again
            last = self.db.execute("SELECT decision, reason, mode FROM job_log WHERE laptop_id=? ORDER BY id DESC LIMIT 1", (laptop,)).fetchone()
            if last is not None and tuple(last) == (decision, reason, mode):
                return
        with self.db:
            self.db.execute("""INSERT INTO job_log (job_id, laptop_id, decided_at, decision, reason, mode, intensity, kwh, gco2e, duration_s, outcome)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (job_id, laptop, iso(now), decision, reason, mode, intensity, kwh, gco2e, duration, outcome))

    # ---- optional batches
    def run_optional(self, now: datetime, mode: str) -> dict:
        """Model evaluation: runs in GREEN; in AMBER and RED it waits, but never longer than 7 days."""
        last = self.db.execute("SELECT MAX(evaluated_at) FROM model_registry").fetchone()[0]
        if last and now - _dt(last) < EVALUATION_INTERVAL:
            return {"action": "not_due"}
        first_wait = self.db.execute("SELECT MIN(decided_at) FROM job_log WHERE decision='defer_optional' AND decided_at > ?", (last or "",)).fetchone()[0]
        overdue = bool(first_wait) and now - _dt(first_wait) >= MAX_OPTIONAL_DEFERRAL
        if mode != "GREEN" and not overdue:
            self._log(None, "model-evaluation", now, "defer_optional", f"deferred in {mode}", mode)
            self.metrics["optional_deferred"] += 1
            return {"action": "deferred", "mode": mode}
        report = self.evaluator.evaluate(now)
        self._log(None, "model-evaluation", now, "run_optional", "mode GREEN" if mode == "GREEN" else "maximum deferral of 7 days reached", mode)
        return {"action": "ran", "report": report}

    def log(self, limit: int = 50) -> list[dict]:
        cols = ("id", "job_id", "laptop_id", "decided_at", "decision", "reason", "mode", "intensity", "kwh", "gco2e", "duration_s", "outcome")
        return [dict(zip(cols, r)) for r in self.db.execute(f"SELECT {', '.join(cols)} FROM job_log ORDER BY id DESC LIMIT ?", (limit,))]
