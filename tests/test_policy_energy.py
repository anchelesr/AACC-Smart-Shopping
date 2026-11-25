from datetime import timedelta

import pytest

from conftest import Clock, NOW
from events.model import TOPIC_MODE
from shopping.energy import CarbonMonitor, ElectricityMapsFeed, FeedError, FileFeed, Reading, SimulatedFeed, StaticFeed
from shopping.policy import Policy, PolicyError, next_level


def run(app, clock, feed, intensity, price=0.10, renewable=False, minutes=5):
    feed.reading = Reading(intensity, price, renewable)
    app.monitor.collect()
    out = app.policy.evaluate()
    clock.advance(minutes=minutes)
    return out


def test_hysteresis_matches_the_documented_thresholds(make_app):
    feed = StaticFeed(Reading(250, 0.1))
    app, clock = make_app(feed=feed)
    modes = [run(app, clock, feed, v)["mode"] for v in (250, 310, 310, 440, 460, 460, 420, 406, 404, 300, 271, 269)]
    assert modes == ["GREEN", "GREEN", "AMBER", "AMBER", "AMBER", "RED", "RED", "RED", "AMBER", "AMBER", "AMBER", "GREEN"]


def test_a_single_noisy_sample_does_not_change_the_mode(make_app):
    feed = StaticFeed(Reading(250, 0.1))
    app, clock = make_app(feed=feed)
    assert [run(app, clock, feed, v)["mode"] for v in (250, 500, 250, 500, 250)] == ["GREEN"] * 5


def test_the_more_restrictive_signal_decides_and_names_the_cause(make_app):
    feed = StaticFeed(Reading(100, 0.1))
    app, clock = make_app(feed=feed)
    run(app, clock, feed, 100, 0.35)
    out = run(app, clock, feed, 100, 0.35)
    assert out["mode"] == "RED" and "price" in out["reason"] and out["placement_target"] == "eco"


def test_renewable_energy_forces_green_and_the_eco_pool(make_app):
    feed = StaticFeed(Reading(500, 0.1))
    app, clock = make_app(feed=feed)
    run(app, clock, feed, 500); run(app, clock, feed, 500)
    out = run(app, clock, feed, 500, renewable=True)
    assert (out["mode"], out["placement_target"], out["reason"]) == ("GREEN", "eco", "renewable")


def test_missing_or_stale_signal_means_green_with_reason_signal_stale(make_app):
    feed = StaticFeed(Reading(350, 0.1))
    app, clock = make_app(feed=feed)
    run(app, clock, feed, 350); run(app, clock, feed, 350)
    assert app.policy.state()["mode"] == "AMBER"
    clock.advance(minutes=31)                                   # no new sample for longer than the stale limit
    out = app.policy.evaluate()
    assert (out["mode"], out["reason"]) == ("GREEN", "signal_stale")


def test_one_missing_signal_lets_the_other_decide(make_app):
    feed = StaticFeed(Reading(350, None))
    app, clock = make_app(feed=feed)
    run(app, clock, feed, 350, None); out = run(app, clock, feed, 350, None)
    assert out["mode"] == "AMBER" and "unavailable" in out["reason"]


def test_invalid_and_failing_feeds_are_recorded_and_ignored(make_app, tmp_path):
    feed = StaticFeed(Reading(9999, 0.1))
    app, clock = make_app(feed=feed)
    assert app.monitor.collect()["status"] == "invalid"
    app.monitor.feed = FileFeed(str(tmp_path / "missing.json"))
    assert app.monitor.collect()["status"] == "unavailable"
    assert app.db.execute("SELECT COUNT(*) FROM energy_samples WHERE status='ok'").fetchone()[0] == 0


def test_mode_changed_is_published_once_per_change(make_app):
    feed = StaticFeed(Reading(250, 0.1))
    app, clock = make_app(feed=feed)
    probe = app.bus.subscribe(TOPIC_MODE, "probe")
    for v in (250, 310, 310, 310, 310, 250):
        run(app, clock, feed, v)
    got = []
    while (d := probe.poll(0)):
        got.append(d.event.data["mode"]); probe.commit(d)
    assert got == ["AMBER", "GREEN"]


def test_override_expires_and_is_limited_to_24_hours(make_app):
    feed = StaticFeed(Reading(100, 0.1))
    app, clock = make_app(feed=feed)
    with pytest.raises(PolicyError):
        app.policy.set_override("RED", 25, "op")
    app.policy.set_override("RED", 2, "op")
    assert run(app, clock, feed, 100)["mode"] == "RED"
    clock.advance(hours=3)
    assert run(app, clock, feed, 100)["mode"] == "GREEN"
    assert app.db.execute("SELECT COUNT(*) FROM ops_audit WHERE action='mode.override'").fetchone()[0] == 1


def test_policy_versions_are_immutable_and_validated(make_app):
    app, _ = make_app()
    assert app.policy_store.current()[0] == 1
    v = app.policy_store.save(Policy(carbon_amber=280), "op")
    assert v == 2 and app.policy_store.current()[1].carbon_amber == 280 and len(app.policy_store.history()) == 2
    for bad in (Policy(carbon_amber=500, carbon_red=400), Policy(margin=0.5), Policy(deadline_hours=100), Policy(override_max_hours=48)):
        with pytest.raises(PolicyError):
            app.policy_store.save(bad, "op")
    assert app.db.execute("SELECT policy_version FROM operating_mode_state").fetchone()[0] == 2


def test_next_level_function_directly():
    assert next_level(0, 310, 300, 450, .1, 0, 0, 2) == (0, 1, 1)
    assert next_level(0, 310, 300, 450, .1, 1, 1, 2) == (1, 0, 0)
    assert next_level(2, 410, 300, 450, .1, 0, 0, 2)[0] == 2           # 405 is the exit threshold
    assert next_level(2, 404, 300, 450, .1, 0, 0, 2)[0] == 1
    assert next_level(2, 100, 300, 450, .1, 0, 0, 2)[0] == 0


def test_simulated_feed_is_deterministic_and_has_a_renewable_window():
    f = SimulatedFeed(seed=3)
    assert f.read(NOW) == f.read(NOW)
    assert f.read(NOW.replace(hour=12)).renewable and not f.read(NOW.replace(hour=3)).renewable


def test_electricity_maps_adapter_parses_and_survives_errors():
    import io, json
    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    ok = ElectricityMapsFeed("t", "SK", opener=lambda req, timeout: Resp(json.dumps({"carbonIntensity": 123, "datetime": "2026-11-25T11:00:00Z"}).encode()))
    assert ok.read(NOW).intensity == 123
    def boom(req, timeout): raise OSError("down")
    with pytest.raises(FeedError):
        ElectricityMapsFeed("t", "SK", opener=boom).read(NOW)
