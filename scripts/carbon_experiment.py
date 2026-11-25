#!/usr/bin/env python3
"""Carbon experiment: the same forecast jobs run (a) immediately and (b) by the adaptive scheduler, on the same
deterministic signal trace. Writes docs/carbon-experiment.md. Everything is simulated: the signal is the
SimulatedFeed wave, the job energy is an ASSUMPTION (configured power x assumed duration), nothing is measured.

    PYTHONPATH=src python scripts/carbon_experiment.py [--days 14] [--job-seconds 600] [--out docs/carbon-experiment.md]
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shopping.energy import SimulatedFeed
from shopping.policy import Policy
from shopping.scheduler import POWER_W
from shopping.seed import LAPTOPS, synthetic_csv
from shopping.service import Application

START = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)     # a Monday after the last seeded observation (10:00); the trace is a pure function of the clock and the seed
TICK = timedelta(minutes=15)
ARRIVALS = (6, 18)                                              # hours (UTC) at which a price update asks for new forecasts


class VirtualClock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def run_once(seed: int, days: int, job_seconds: float, immediate: bool, renewable_hours: tuple) -> dict:
    clock = VirtualClock(START)
    app = Application("sqlite://:memory:", clock=clock, feed=SimulatedFeed(seed=seed, renewable_hours=renewable_hours), ops_token="x", mode_cache_seconds=0,
                      initial_policy=Policy())
    app.scheduler.assumed_duration_s, app.scheduler.immediate = job_seconds, immediate
    app.imports.run(synthetic_csv(START), "csv", "experiment")        # history for the forecasts
    app.db.execute("DELETE FROM forecast_jobs"); app.db.commit()
    end, last_arrival_day = START + timedelta(days=days), None
    modes: dict[str, int] = {"GREEN": 0, "AMBER": 0, "RED": 0}
    while clock.t < end:
        key = (clock.t.date(), clock.t.hour)
        if clock.t.hour in ARRIVALS and clock.t.minute == 0:
            for laptop_id, *_ in LAPTOPS:
                app.scheduler.enqueue_or_keep(laptop_id)
        app.step_control()
        app.step_work()
        modes[app.policy.state()["mode"]] += 1
        clock.t += TICK
    # drain: let the open jobs finish under the same rules (their deadline is at most 24 h away)
    for _ in range(24 * 4 + 2):
        app.step_control(); app.step_work(); clock.t += TICK
    runs = app.db.execute("SELECT j.laptop_id, j.decided_at, j.kwh, j.gco2e, j.intensity, f.created_at, f.deadline, j.mode FROM job_log j "
                          "JOIN forecast_jobs f ON f.id = j.job_id WHERE j.decision='run' AND j.outcome IN ('ok','insufficient_data')").fetchall()
    waits = [(datetime.fromisoformat(r[1]) - datetime.fromisoformat(r[5])).total_seconds() / 3600 for r in runs]
    late = sum(1 for r in runs if datetime.fromisoformat(r[1]) > datetime.fromisoformat(r[6]) + TICK)
    return {"jobs": len(runs), "kwh": sum(r[2] for r in runs), "gco2e": sum(r[3] for r in runs), "mean_intensity": statistics.mean(r[4] for r in runs),
            "mean_wait_h": statistics.mean(waits), "max_wait_h": max(waits), "late": late, "modes": modes,
            "by_mode": {m: sum(1 for r in runs if r[7] == m) for m in ("GREEN", "AMBER", "RED")}}


SCENARIOS = (
    ("A", "Default simulator: renewable window 11:00-15:00 UTC, which coincides with the peak of the simulated carbon intensity", (11, 15)),
    ("B", "Coherent trace: renewable window 00:00-05:00 UTC, in the trough of the simulated carbon intensity", (0, 5)),
)


def table(results: list[dict]) -> tuple[str, list[float]]:
    rows, changes = [], []
    for r in results:
        a, i = r["adaptive"], r["immediate"]
        ch = (a["mean_intensity"] / i["mean_intensity"] - 1) * 100                  # timing only
        per_job = ((a["gco2e"] / a["jobs"]) / (i["gco2e"] / i["jobs"]) - 1) * 100  # timing + assumed pool power; job counts can differ
        changes.append((ch, per_job))
        rows.append(f"| {r['seed']} | {i['jobs']} / {a['jobs']} | {i['mean_intensity']:.0f} | {a['mean_intensity']:.0f} | {ch:+.1f} % | {i['gco2e']:.1f} | {a['gco2e']:.1f} | "
                    f"{per_job:+.1f} % | {a['mean_wait_h']:.1f} | {a['max_wait_h']:.1f} | {a['late']} |")
    head = ("| Seed | Jobs (immediate / adaptive) | Mean intensity at start, immediate (gCO2e/kWh) | Mean intensity at start, adaptive | "
            "Timing effect (intensity at start) | Emissions immediate (gCO2e) | Emissions adaptive (gCO2e) | Per job, timing + pool power | Mean wait adaptive (h) | Longest wait (h) | Jobs after deadline |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
    return head + "\n".join(rows), changes


def report(results: dict, days: int, job_seconds: float, seeds: list[int]) -> str:
    sections, summary = [], []
    for key, text, _ in SCENARIOS:
        t, ch = table(results[key])
        sections.append(f"### Scenario {key}: {text}\n\n{t}\n")
        t_eff, per_job = [c[0] for c in ch], [c[1] for c in ch]
        summary.append(f"- **Scenario {key}:** the carbon intensity at job start changed by **{statistics.mean(t_eff):+.1f} %** on average (range {min(t_eff):+.1f} % to {max(t_eff):+.1f} %; timing only); "
                       f"estimated emissions per job changed by {statistics.mean(per_job):+.1f} % (timing plus the assumed power of the pool each job ran on), "
                       f"longest wait {max(r['adaptive']['max_wait_h'] for r in results[key]):.1f} h, jobs after the deadline: {sum(r['adaptive']['late'] for r in results[key])}.")
    return f"""# Carbon experiment: adaptive scheduling against immediate execution

*Generated by `scripts/carbon_experiment.py` ({days} simulated days, seeds {seeds}, assumed job length {job_seconds:.0f} s). Re-run it to reproduce every number.*

## What was compared

The same forecast jobs ({len(LAPTOPS)} laptops, a price update at {" and ".join(f"{h:02d}:00" for h in ARRIVALS)} UTC every day, deadline 24 h) were executed twice on the same simulated signal trace:

- **Immediate:** every job runs in the first scheduler step after it exists (no energy awareness).
- **Adaptive:** the implemented Policy Engine and Job Scheduler decide per step (GREEN runs, AMBER runs when half of the window is left, RED waits for the deadline), with a 15 minute step.

The energy of one job is **assumed**: {POWER_W['standard']:.0f} W (standard pool) x {job_seconds:.0f} s = {POWER_W['standard'] * job_seconds / 3600:.2f} Wh, because the demonstration jobs take milliseconds and say nothing about a production workload. On the eco pool the assumed power is {POWER_W['eco']:.0f} W. Emissions are that energy times the carbon intensity of the sample taken when the job started. The two variants can run different numbers of jobs: a job that is still waiting blocks a new job for the same laptop (one open job per laptop), so the adaptive variant coalesces some price updates into one forecast. That saves energy by itself, so the main comparison is the **carbon intensity at job start** (timing only); emissions per job additionally contain the assumed power difference of the eco pool, and the totals and job counts are shown as well. Two traces are reported because the result depends on one property of the simulator, explained below.

## Results (negative = adaptive is cleaner)

{chr(10).join(summary)}

{chr(10).join(sections)}

## What the results mean

- **Scenario A shows a weakness, not a saving.** In the default simulator the renewable window (11:00 to 15:00) lies on the peak of the simulated carbon intensity. The Policy Engine rule "renewable energy forces GREEN" then makes the scheduler run the waiting jobs at the dirtiest time of the day. The rule is right for a real grid (renewable supply and low intensity go together) but the simulated trace contradicts it. The consequence is that the demonstration feed is not a good basis for a carbon claim, and the default window of the simulator should be moved (open decision, see docs/implementation.md).
- **Scenario B is the intended behaviour.** When the renewable window lies in the trough, deferred jobs move into it and the intensity at job start falls, at the price of a wait that never exceeds the 24 h window. In this scenario the adaptive variant also runs fewer jobs (see the job counts), because jobs that wait absorb later price updates; that coalescing lowers the total emissions further, but it is a different effect from the timing and is not included in the per-job percentage.
- **Not general.** Both traces are smooth daily waves with a 24 h period, and the job window is also 24 h; a real grid has weather-driven jumps and the saving would differ. The experiment shows that the mechanism behaves as designed on a coherent trace and exposes where it does not, not what a deployment would save.
- **Only forecast jobs are included.** The assistant and the web tier cannot be deferred; their estimated energy is exposed by the live metrics.
- **No measurement.** Power per pool is a configured constant; Kepler or a power meter would be needed to replace it (see docs/observability.md).
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--job-seconds", type=float, default=600.0)
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 11, 23, 42, 101])
    ap.add_argument("--out", default="docs/carbon-experiment.md")
    a = ap.parse_args()
    results: dict = {}
    for key, _, hours in SCENARIOS:
        results[key] = []
        for seed in a.seeds:
            r = {"seed": seed, "immediate": run_once(seed, a.days, a.job_seconds, True, hours), "adaptive": run_once(seed, a.days, a.job_seconds, False, hours)}
            print(f"scenario {key} seed {seed}: immediate {r['immediate']['gco2e']:.2f} gCO2e, adaptive {r['adaptive']['gco2e']:.2f} gCO2e, adaptive late jobs {r['adaptive']['late']}", flush=True)
            results[key].append(r)
    Path(a.out).write_text(report(results, a.days, a.job_seconds, a.seeds), encoding="utf-8")
    print("written", a.out)


if __name__ == "__main__":
    sys.exit(main())
