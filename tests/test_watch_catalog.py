from datetime import datetime, timedelta, timezone

import pytest

from events.consumer import Metrics
from shopping.advice import Constraints
from shopping.catalog import current_offers, find_alternatives, lowest_offer
from shopping.core import connect
from shopping.watch import WatchService

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
DEV, OTHER = "device-aaaaaaaaaaaa-0001", "device-bbbbbbbbbbbb-0002"


def iso(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M")


@pytest.fixture
def env():
    db = connect()
    db.executemany("INSERT INTO products VALUES (?, ?, ?)", [("l1", "Acme", "A1"), ("l2", "Beta", "B2"), ("l3", "Acme", "A3"), ("l4", "Acme", "A4")])
    add = lambda l, r, price, h: db.execute("INSERT INTO observations (laptop_id, retailer, observed_at, price) VALUES (?, ?, ?, ?)", (l, r, iso(h), price))
    add("l1", "shop-a", 1100.0, 30); add("l1", "shop-a", 1000.0, 2); add("l1", "shop-b", 1050.0, 3)   # latest per retailer: 1000, 1050
    add("l2", "shop-a", 700.0, 1)
    add("l3", "shop-a", 800.0, 1)
    db.commit()
    return db, WatchService(db, Metrics())


# ---- catalog
def test_current_offers_are_the_latest_per_retailer():
    db = connect(); db.execute("INSERT INTO products VALUES ('l1','Acme','A1')")
    db.executemany("INSERT INTO observations (laptop_id, retailer, observed_at, price) VALUES ('l1', ?, ?, ?)", [("shop-a", iso(30), 1100.0), ("shop-a", iso(2), 1000.0), ("shop-b", iso(3), 1050.0)])
    assert [(o["retailer"], o["price"]) for o in current_offers(db, "l1")] == [("shop-a", 1000.0), ("shop-b", 1050.0)]
    assert lowest_offer(db, "l1")["price"] == 1000.0 and lowest_offer(db, "none") is None


def test_alternatives_respect_budget_brand_and_order(env):
    db, _ = env
    alts = find_alternatives(db, Constraints(budget=900), exclude_laptop="l1")
    assert [a["laptop_id"] for a in alts] == ["l2", "l3"]                        # l1 excluded, l4 has no offers
    assert [a["laptop_id"] for a in find_alternatives(db, Constraints(budget=900, preferred_brands=("acme",)), "l1")] == ["l3"]
    assert find_alternatives(db, Constraints(budget=500), "l1") == []
    assert len(find_alternatives(db, Constraints(), "l1", limit=1)) == 1


# ---- watch: input validation and scoping
@pytest.mark.parametrize("device,laptop,target", [("short", "l1", 900), (DEV, "unknown", 900), (DEV, "l1", 0), (DEV, "l1", -5), (DEV, "l1", True), (DEV, "l1", "900")])
def test_invalid_watches_are_rejected(env, device, laptop, target):
    with pytest.raises(ValueError):
        env[1].save_watch(device, laptop, target)


def test_watch_limit_per_device(env):
    db, svc = env
    for i in range(20):
        db.execute("INSERT INTO products VALUES (?, 'X', 'M')", (f"p{i}",)); svc.save_watch(DEV, f"p{i}", 100)
    db.execute("INSERT INTO products VALUES ('extra', 'X', 'M')")
    with pytest.raises(ValueError):
        svc.save_watch(DEV, "extra", 100)


def test_saving_twice_updates_one_watch(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 900); svc.save_watch(DEV, "l1", 950)
    assert svc.list_watches(DEV) == [{"laptop_id": "l1", "target_price": 950, "enabled": True}]


def test_alerts_are_scoped_to_the_device(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 1000); svc.save_watch(OTHER, "l1", 500)
    svc.run_check(NOW)
    assert len(svc.list_alerts(DEV)) == 1 and svc.list_alerts(OTHER) == []
    svc.mark_read(OTHER, [svc.list_alerts(DEV)[0]["id"]])                         # another device cannot mark it
    assert len(svc.list_alerts(DEV, unread_only=True)) == 1
    svc.mark_read(DEV, [svc.list_alerts(DEV)[0]["id"]])
    assert svc.list_alerts(DEV, unread_only=True) == []


# ---- watch: the check
def test_fresh_price_at_or_below_target_creates_one_alert(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 1000)                                               # lowest current offer is exactly 1000
    assert svc.run_check(NOW)["alerted"] == 1
    a = svc.list_alerts(DEV)[0]
    assert a["price"] == 1000.0 and a["retailer"] == "shop-a" and a["laptop_id"] == "l1"


def test_repeated_checks_do_not_duplicate_the_alert(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 1000)
    svc.run_check(NOW); second = svc.run_check(NOW + timedelta(minutes=30))
    assert second["alerted"] == 0 and second["already_alerted"] == 1 and len(svc.list_alerts(DEV)) == 1


def test_target_not_reached_creates_nothing(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 900)
    out = svc.run_check(NOW)
    assert out["not_reached"] == 1 and svc.list_alerts(DEV) == []


def test_stale_price_never_alerts(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 1000)
    out = svc.run_check(NOW + timedelta(hours=60))                                # the newest observation is now older than 48 h
    assert out["stale"] == 1 and svc.list_alerts(DEV) == []


def test_laptop_without_offers_is_skipped(env):
    _, svc = env
    svc.save_watch(DEV, "l4", 1000)
    assert svc.run_check(NOW)["stale"] == 1


def test_new_episode_after_the_price_rises_above_the_target(env):
    db, svc = env
    svc.save_watch(DEV, "l2", 700)
    svc.run_check(NOW)                                                            # 700 <= 700: alert 1
    db.execute("INSERT INTO observations (laptop_id, retailer, observed_at, price) VALUES ('l2', 'shop-a', ?, 800.0)", (iso(0),)); db.commit()
    assert svc.run_check(NOW)["reset"] == 1                                       # price above target: the episode ends
    db.execute("INSERT INTO observations (laptop_id, retailer, observed_at, price) VALUES ('l2', 'shop-a', ?, 650.0)", ((NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),)); db.commit()
    assert svc.run_check(NOW + timedelta(hours=2))["alerted"] == 1
    assert len(svc.list_alerts(DEV)) == 2


def test_new_target_starts_a_new_episode(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 1000); svc.run_check(NOW)
    svc.save_watch(DEV, "l1", 1050); svc.run_check(NOW)
    assert len(svc.list_alerts(DEV)) == 2


def test_paused_watch_is_not_checked_and_resumes(env):
    _, svc = env
    svc.save_watch(DEV, "l1", 1000); svc.set_enabled(DEV, "l1", False)
    assert svc.run_check(NOW)["checked"] == 0
    svc.set_enabled(DEV, "l1", True)
    assert svc.run_check(NOW)["alerted"] == 1


def test_existing_alert_of_the_episode_rolls_back_the_flag(env):
    db, svc = env
    svc.save_watch(DEV, "l1", 1000)
    wid = db.execute("SELECT id FROM watches").fetchone()[0]
    db.execute("INSERT INTO alerts (watch_id, dedup_key) VALUES (?, ?)", (wid, f"{wid}:0")); db.commit()   # e.g. a concurrent run
    out = svc.run_check(NOW)
    assert out["alerted"] == 0 and out["already_alerted"] == 1
    assert db.execute("SELECT alerted FROM watches").fetchone()[0] == 0           # rolled back together with the failed insert


def test_deleting_a_watch_removes_its_alerts(env):
    db, svc = env
    svc.save_watch(DEV, "l1", 1000); svc.run_check(NOW); svc.delete_watch(DEV, "l1")
    assert svc.list_watches(DEV) == [] and db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0


def test_the_check_is_recorded_and_stored_prices_stay_intact(env):
    db, svc = env
    svc.save_watch(DEV, "l1", 1000)
    before = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    svc.run_check(NOW)
    assert db.execute("SELECT checked, alerted FROM watch_checks").fetchone() == (1, 1)
    assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == before
