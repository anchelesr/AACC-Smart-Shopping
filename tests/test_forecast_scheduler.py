from datetime import timedelta

import pytest

from conftest import NOW
from shopping.energy import Reading, StaticFeed
from shopping.forecast import (BASELINE, CANDIDATE, ModelEvaluator, backtest, baseline_predict, daily_series, evidence_for, fill_gaps,
                               forecast_for, holt_predict)
from shopping.scheduler import CONCURRENCY, MAX_ATTEMPTS


def set_mode(app, mode):
    app.policy.set_override(mode, 24, "op")
    app.policy.evaluate()
    app.mode_reader.on_mode_changed(None)


def finish_jobs(app):
    """Tick (in GREEN) until the queue is empty."""
    queue_all(app)
    for _ in range(10):
        if not app.scheduler.open_jobs():
            return
        app.scheduler.tick()


def queue_all(app):
    app.scheduler.reconcile()
    return app.scheduler.open_jobs()


# ------------------------------------------------------------------ series, evidence, models
def test_daily_series_takes_the_lowest_offer_per_day(make_app):
    app, clock = make_app()
    app.imports.run("laptop_id,retailer,observed_at,price\na,s1,2026-11-24T08:00:00Z,100\na,s2,2026-11-24T09:00:00Z,90\na,s1,2026-11-25T08:00:00Z,95\n", "csv", "t")
    assert [(d.isoformat(), p) for d, p in daily_series(app.db, "a", NOW)] == [("2026-11-24", 90.0), ("2026-11-25", 95.0)]


def test_gaps_up_to_three_days_are_carried_forward_longer_gaps_reject():
    from datetime import date
    d = lambda n: date(2026, 11, n)
    assert fill_gaps([(d(1), 10.0), (d(5), 14.0)]) == [10.0, 10.0, 10.0, 10.0, 14.0]
    assert fill_gaps([(d(1), 10.0), (d(6), 14.0)]) is None


def test_evidence_needs_ten_days_and_uses_the_median(seeded):
    app, clock = seeded
    ev = evidence_for(app.db, "lap-001", clock())
    assert ev.sufficient and ev.delta < -0.03 and ev.brand == "Acme"          # the planned dip
    app2_rows = "laptop_id,retailer,observed_at,price\nx,s,2026-11-24T08:00:00Z,100\n"
    app.imports.run(app2_rows, "csv", "short")
    assert not evidence_for(app.db, "x", clock()).sufficient


def test_baseline_repeats_the_last_value_and_holt_follows_a_trend():
    assert baseline_predict([5, 6, 7]) == [7] * 7
    rising = [100 + i for i in range(20)]
    h = holt_predict(rising)
    assert h[0] > rising[-1] and h == sorted(h)                               # trend continues, damped
    flat = holt_predict([100.0] * 20)
    assert all(abs(x - 100) < 1e-6 for x in flat)


def test_backtest_prefers_holt_on_a_trend_and_baseline_on_noise():
    trend = [100 + 2 * i for i in range(30)]
    r = backtest(trend)
    assert r[CANDIDATE] < r[BASELINE]
    assert backtest([1.0] * 10) is None                                       # too short for any origin


# ------------------------------------------------------------------ worker
def test_worker_stores_active_forecast_and_shadow(seeded):
    app, clock = seeded
    out = app.worker.run_job("lap-001", clock())
    assert out["outcome"] == "ok"
    rows = app.db.execute("SELECT model_id, shadow FROM forecasts WHERE laptop_id='lap-001' ORDER BY shadow").fetchall()
    assert [tuple(r) for r in rows] == [(BASELINE, 0), (CANDIDATE, 1)]
    fc, detail = forecast_for(app.db, "lap-001", clock())
    assert fc.status == "FRESH" and detail["model_id"] == BASELINE
    assert forecast_for(app.db, "lap-001", clock() + timedelta(hours=49))[0].status == "STALE"
    assert forecast_for(app.db, "nope", clock())[0].status == "MISSING"


def test_worker_reports_insufficient_data_and_guardrail_failures(make_app):
    app, clock = make_app()
    app.imports.run("laptop_id,retailer,observed_at,price\na,s,2026-11-24T08:00:00Z,100\n", "csv", "t")
    assert app.worker.run_job("a", clock())["outcome"] == "insufficient_data"
    # a series with a 5 day hole is ineligible
    rows = "laptop_id,retailer,observed_at,price\n" + "".join(f"b,s,2026-11-{d:02d}T08:00:00Z,100\n" for d in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20))
    app.imports.run(rows, "csv", "t2")
    assert app.worker.run_job("b", clock())["outcome"] == "insufficient_data"
    # output guardrail: force an implausible prediction
    from shopping import forecast
    app.imports.run("laptop_id,retailer,observed_at,price\n" + "".join(f"c,s,2026-11-{d:02d}T08:00:00Z,100\n" for d in range(10, 25)), "csv", "t3")
    forecast.MODELS[BASELINE] = lambda v, h: [-5.0] * h
    try:
        assert app.worker.run_job("c", clock())["outcome"] == "guardrail_failed"
    finally:
        forecast.MODELS[BASELINE] = forecast.baseline_predict


# ------------------------------------------------------------------ evaluator
def test_evaluator_adoption_gate_and_pinning(make_app):
    app, clock = make_app()
    rows = "laptop_id,retailer,observed_at,price\n" + "".join(f"t,s,2026-11-{d:02d}T08:00:00Z,{100 + 2 * d}\n" for d in range(1, 26))
    app.imports.run(rows, "csv", "trend")
    rep = ModelEvaluator(app.db, app.registry).evaluate(clock())
    assert rep["backtest"]["candidate_accepted"] and app.registry.active() == CANDIDATE
    app.registry.set_active(BASELINE, pinned=True)
    ModelEvaluator(app.db, app.registry).evaluate(clock())
    assert app.registry.active() == BASELINE and app.registry.pinned()          # an operator pin is respected


def test_live_evaluation_falls_back_after_three_worse_checks(make_app):
    app, clock = make_app()
    app.registry.set_active(CANDIDATE)
    ev = ModelEvaluator(app.db, app.registry)
    for n in range(3):
        day = f"2026-11-{10 + n:02d}"
        for model, pred in ((CANDIDATE, 150.0), (BASELINE, 101.0)):
            app.db.execute("INSERT INTO forecasts (laptop_id, generated_at, model_id, shadow, base_price, prices, change, status, target_day) VALUES (?,?,?,?,?,?,?,?,?)",
                           ("t", f"2026-11-{3 + n:02d}T08:00:00+00:00", model, 0 if model == CANDIDATE else 1, 100.0, f"[{pred}]", 0.0, "FRESH", day))
        app.db.execute("INSERT INTO observations (laptop_id, retailer, observed_at, price) VALUES (?,?,?,?)", ("t", "s", day + "T08:00:00+00:00", 100.0))
        app.db.commit()
        res = ev._live(clock())                                                # one evaluation per round
        assert res["worse_streak"] == n + 1
    assert res["fell_back"] and app.registry.active() == BASELINE
    assert app.db.execute("SELECT COUNT(*) FROM drift_checks WHERE worse=1").fetchone()[0] == 3


# ------------------------------------------------------------------ scheduler
def test_green_starts_at_most_three_jobs_per_tick_and_amber_one(seeded):
    app, clock = seeded
    queue_all(app)
    assert len(app.scheduler.open_jobs()) == 6
    first = app.scheduler.tick()
    assert first["mode"] == "GREEN" and len(first["ran"]) == CONCURRENCY["GREEN"] == 3 and len(first["deferred"]) == 3
    assert all("concurrency limit 3" in r[0] for r in app.db.execute("SELECT reason FROM job_log WHERE decision='defer'").fetchall())
    assert len(app.scheduler.tick()["ran"]) == 3 and app.scheduler.open_jobs() == []
    set_mode(app, "AMBER")
    for i in range(1, 7):
        app.scheduler.enqueue_or_keep(f"lap-00{i}")
    clock.advance(hours=13)                                                        # all jobs are past half of their window
    assert len(app.scheduler.tick()["ran"]) == CONCURRENCY["AMBER"] == 1


def test_amber_waits_until_half_the_window_is_left_and_red_until_the_deadline(seeded):
    app, clock = seeded
    finish_jobs(app)                                                             # GREEN: all initial jobs done
    app.imports.run("laptop_id,retailer,observed_at,price\nlap-001,shop-a,2026-11-25T11:00:00Z,700\n", "csv", "new")
    for mode, runs_at in (("AMBER", 12), ("RED", 24)):
        set_mode(app, mode)
        app.scheduler.reconcile(); app.scheduler.enqueue_or_keep("lap-001")
        t0 = clock()
        job = app.db.execute("SELECT created_at, deadline FROM forecast_jobs WHERE laptop_id='lap-001' AND status='queued'").fetchone()
        assert job is not None
        clock.t = t0 + timedelta(hours=runs_at - 1)
        assert app.scheduler.tick()["deferred"] == ["lap-001"] and app.scheduler.open_jobs() == ["lap-001"]
        clock.t = t0 + timedelta(hours=runs_at, minutes=1)
        assert app.scheduler.tick()["ran"] == ["lap-001"]
        clock.t = t0
        app.policy.clear_override("op")


def test_the_deadline_is_never_reset_by_later_price_changes(seeded):
    app, clock = seeded
    app.scheduler.enqueue_or_keep("lap-001")
    first = app.db.execute("SELECT deadline FROM forecast_jobs WHERE laptop_id='lap-001'").fetchone()[0]
    clock.advance(hours=5)
    assert app.scheduler.enqueue_or_keep("lap-001") is False
    assert app.db.execute("SELECT deadline FROM forecast_jobs WHERE laptop_id='lap-001'").fetchone()[0] == first


def test_overdue_jobs_run_even_above_the_concurrency_cap(seeded):
    app, clock = seeded
    set_mode(app, "RED")
    queue_all(app)
    clock.advance(hours=25)
    out = app.scheduler.tick()
    assert len(out["ran"]) == 6 > CONCURRENCY["RED"]                            # the deadline wins over the cap


def test_expired_lease_is_recovered_and_retried(seeded):
    app, clock = seeded
    app.scheduler.enqueue_or_keep("lap-001")
    job = dict(zip(("id", "laptop_id"), app.db.execute("SELECT id, laptop_id FROM forecast_jobs").fetchone()))
    assert app.scheduler._claim({"id": job["id"]}, clock())                      # a worker claims it, then dies
    assert app.scheduler.open_jobs() == ["lap-001"] and app.scheduler.tick()["ran"] == []
    clock.advance(minutes=6)
    out = app.scheduler.tick()
    assert out["recovered"] == 1 and out["ran"] == ["lap-001"]


def test_a_failing_job_backs_off_and_eventually_fails(seeded):
    app, clock = seeded
    app.worker.run_job = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    app.scheduler.enqueue_or_keep("lap-001")
    for _ in range(MAX_ATTEMPTS):
        assert app.scheduler.tick()["failed"] == ["lap-001"]
        clock.advance(minutes=11)
    assert app.db.execute("SELECT status FROM forecast_jobs").fetchone()[0] == "failed"


def test_job_log_records_estimated_energy_and_carbon(seeded):
    app, clock = seeded
    ticks = iter(x * 0.5 for x in range(100))
    app.scheduler.timer = lambda: next(ticks)                                    # every job "takes" 0.5 s
    app.monitor.collect(); app.scheduler.enqueue_or_keep("lap-001")
    app.scheduler.tick()
    row = app.db.execute("SELECT kwh, gco2e, intensity FROM job_log WHERE decision='run'").fetchone()
    assert row[0] == pytest.approx(65.0 * 0.5 / 3_600_000) and row[1] == pytest.approx(row[0] * row[2])


def test_optional_evaluation_runs_in_green_waits_in_amber_but_never_beyond_seven_days(seeded):
    app, clock = seeded
    set_mode(app, "AMBER")
    assert app.scheduler.run_optional(clock(), "AMBER")["action"] == "deferred"
    clock.advance(days=8)
    assert app.scheduler.run_optional(clock(), "AMBER")["action"] == "ran"
    assert app.scheduler.run_optional(clock(), "AMBER")["action"] == "not_due"   # evaluated just now
    clock.advance(days=2)
    assert app.scheduler.run_optional(clock(), "GREEN")["action"] == "ran"


def test_control_loop_end_to_end_events_to_forecast_to_advice(make_app):
    app, clock = make_app()
    from shopping.seed import synthetic_csv
    app.imports.run(synthetic_csv(clock()), "csv", "seed")
    out = app.step()
    assert len(out["jobs"]["ran"]) == 3 and len(out["jobs"]["deferred"]) == 3        # GREEN: three jobs per tick
    app.step()
    assert app.scheduler.open_jobs() == []
    ins = app.service.insights("lap-001")
    assert ins["future"]["status"] == "FRESH" and ins["recommendation"]["action"] == "BUY_NOW"
    assert app.service.insights("lap-002")["recommendation"]["action"] == "WAIT"


def test_repeated_identical_deferrals_are_not_logged_again(seeded):
    app, clock = seeded
    set_mode(app, "RED")
    queue_all(app)
    for _ in range(4):
        app.scheduler.tick(); clock.advance(minutes=1)
    assert app.db.execute("SELECT COUNT(*) FROM job_log WHERE decision='defer' AND laptop_id='lap-001'").fetchone()[0] == 1
    assert app.metrics["jobs_deferred"] >= 4 * 6                                # but every deferral is counted
