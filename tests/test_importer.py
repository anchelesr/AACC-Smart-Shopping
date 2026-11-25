import json

from conftest import Clock
from events.model import TOPIC_PRICE
from shopping.seed import synthetic_csv

CSV = "laptop_id,brand,model,retailer,observed_at,price,currency\n{}\n"


def test_import_is_idempotent_and_publishes_once_per_laptop(make_app):
    app, clock = make_app()
    text = synthetic_csv(clock())
    first = app.imports.run(text, "csv", "seed")
    assert first["status"] == "ok" and first["inserted"] == 648 and first["published"] == 6
    again = app.imports.run(text, "csv", "seed")
    assert again["status"] == "duplicate_batch"
    other = app.imports.run(text, "csv", "second-source")        # same rows from another source: nothing new is inserted
    assert other["inserted"] == 0 and other["unchanged"] == 648 and other["published"] == 0
    assert app.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 648


def test_invalid_rows_are_rejected_with_reasons_and_valid_rows_kept(make_app):
    app, clock = make_app()
    rows = ["a,B,M,s,2026-11-24T10:00:00Z,100,EUR", "b,B,M,s,2026-11-24T10:00:00Z,-1,EUR", "c,B,M,s,2026-11-24T10:00:00Z,100,USD",
            "d,B,M,s,not-a-date,100,EUR", ",B,M,s,2026-11-24T10:00:00Z,100,EUR", "e,B,M,s,2027-06-01T10:00:00Z,100,EUR", "f,B,M,s,2026-11-24T10:00:00Z,abc,EUR"]
    r = app.imports.run(CSV.format("\n".join(rows)), "csv", "t")
    assert r["status"] == "partial" and r["accepted"] == 1 and r["rejected"] == 6 and len(r["problems"]) == 6
    assert any("currency USD" in p for p in r["problems"]) and any("future" in p for p in r["problems"])
    assert app.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1


def test_timestamps_are_normalised_so_equal_instants_are_one_observation(make_app):
    app, _ = make_app()
    r = app.imports.run(CSV.format("a,B,M,s,2026-11-24T10:00:00Z,100,EUR\na,B,M,s,2026-11-24T11:00:00+01:00,100,EUR"), "csv", "t")
    assert r["inserted"] == 1


def test_json_and_malformed_batches(make_app):
    app, _ = make_app()
    ok = app.imports.run(json.dumps([{"laptop_id": "a", "retailer": "s", "observed_at": "2026-11-24T10:00:00Z", "price": 10}]), "json", "j")
    assert ok["status"] == "ok"
    assert app.imports.run("{not json", "json", "bad")["status"] == "failed"
    assert app.imports.run("a,b\n1,2\n", "csv", "bad2")["status"] == "failed"
    assert [x["status"] for x in app.imports.reports()][:2] == ["failed", "failed"]


def test_import_survives_a_broken_bus(make_app):
    app, clock = make_app()
    app.bus.down = True
    r = app.imports.run(CSV.format("a,B,M,s,2026-11-24T10:00:00Z,100,EUR"), "csv", "t")
    assert r["inserted"] == 1 and r["publish_failed"] == 1
    app.bus.down = False
    app.scheduler.reconcile()                                   # the pull path repairs the lost event
    assert app.scheduler.open_jobs() == ["a"]


def test_backfill_is_deferred_in_amber_but_daily_runs(make_app):
    app, clock = make_app()
    app.policy.set_override("AMBER", 24, "op"); app.policy.evaluate(); app.mode_reader.on_mode_changed(None)
    row = CSV.format("a,B,M,s,2026-11-24T10:00:00Z,100,EUR")
    assert app.imports.run(row, "csv", "t", kind="backfill")["status"] == "deferred"
    assert app.imports.run(row, "csv", "t", kind="daily")["status"] == "ok"
    clock.advance(days=8)
    assert app.imports.run(CSV.format("b,B,M,s,2026-11-24T10:00:00Z,100,EUR"), "csv", "u", kind="backfill")["status"] == "ok"   # max deferral 7 days
