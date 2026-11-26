"""Market signals: parsing, counting, failure handling, deferral in the scheduler, API and unchanged recommendation. No network."""
from datetime import timedelta

import pytest

from conftest import NOW
from market_fixtures import FEED_A, FEED_B, atom, rss
from shopping.api import make_wsgi
from shopping.market import MarketScanner, NOTICE, current_signals, normalise, parse_feed
from shopping.seed import synthetic_csv
from test_api import Client, OPS
from test_forecast_scheduler import set_mode


def fetcher(mapping):
    def fetch(url):
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value
    return fetch


FEEDS = ("https://a.example/rss.xml", "https://b.example/rss.xml")


# ------------------------------------------------------------------ parsing
def test_parse_rss_and_atom_keep_only_http_links():
    items = parse_feed(rss([("AI data centres push memory prices up", "https://x.example/1", "Tue, 24 Nov 2026 10:00:00 GMT"),
                            ("Bad link", "javascript:alert(1)", None)]))
    assert [(i.title, i.link) for i in items] == [("AI data centres push memory prices up", "https://x.example/1"), ("Bad link", None)]
    assert items[0].published.year == 2026
    entries = parse_feed(atom([("DRAM shortage", "https://y.example/2", "2026-11-24T09:00:00Z")]))
    assert entries[0].title == "DRAM shortage" and entries[0].link == "https://y.example/2" and entries[0].published is not None


def test_parse_refuses_entity_declarations():
    evil = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
    with pytest.raises(ValueError):
        parse_feed(evil)


def test_normalise_ignores_case_and_punctuation():
    assert normalise("AI data-centres: DRAM prices!") == "ai data centres dram prices"


# ------------------------------------------------------------------ counting
def test_counts_distinct_headlines_and_sources(make_app):
    app, clock = make_app()
    sc = MarketScanner(app.db, FEEDS, fetch=fetcher({FEEDS[0]: FEED_A, FEEDS[1]: FEED_B}))
    report = sc.scan(NOW, "GREEN")
    assert report["outcome"] == "ok" and report["failed"] == 0
    sig = {s["topic"]: s for s in current_signals(app.db, NOW)}
    assert "ai_datacentres" in sig and sig["ai_datacentres"]["mentions"] >= 3 and sig["ai_datacentres"]["sources"] == 2
    assert "memory_prices" not in sig                                    # one headline only: below the threshold, not a signal
    assert report["signals"] == len([s for s in sig.values() if s["origin"] == "news"])


def test_same_headline_in_two_feeds_counts_once(make_app):
    app, _ = make_app()
    same = rss([("AI data centres need more memory", "https://x.example/1", None)])
    sc = MarketScanner(app.db, FEEDS, fetch=fetcher({FEEDS[0]: same, FEEDS[1]: same}), min_mentions=1, min_sources=1)
    sc.scan(NOW)
    sig = current_signals(app.db, NOW)
    assert sig[0]["mentions"] == 1 and sig[0]["sources"] == 2


def test_old_headlines_outside_the_window_are_ignored(make_app):
    app, _ = make_app()
    old = rss([("AI data centres again", "https://x.example/1", "Mon, 01 Jan 2024 10:00:00 GMT")])
    MarketScanner(app.db, FEEDS[:1], fetch=fetcher({FEEDS[0]: old}), min_mentions=1, min_sources=1).scan(NOW)
    assert current_signals(app.db, NOW) == []


# ------------------------------------------------------------------ failures
def test_one_broken_feed_gives_a_partial_result(make_app):
    app, _ = make_app()
    sc = MarketScanner(app.db, FEEDS, fetch=fetcher({FEEDS[0]: TimeoutError("slow"), FEEDS[1]: FEED_B}), min_sources=1)
    report = sc.scan(NOW)
    assert report["outcome"] == "partial" and report["failed"] == 1 and report["errors"] == ["a.example: TimeoutError"]


def test_all_feeds_failing_keeps_the_previous_signals_until_they_expire(make_app):
    app, _ = make_app()
    MarketScanner(app.db, FEEDS, fetch=fetcher({FEEDS[0]: FEED_A, FEEDS[1]: FEED_B})).scan(NOW)
    before = current_signals(app.db, NOW)
    assert before
    later = NOW + timedelta(hours=6)
    broken = MarketScanner(app.db, FEEDS, fetch=fetcher({FEEDS[0]: OSError("down"), FEEDS[1]: OSError("down")}))
    assert broken.scan(later)["outcome"] == "failed"
    assert [s["topic"] for s in current_signals(app.db, later)] == [s["topic"] for s in before]
    assert current_signals(app.db, NOW + timedelta(hours=49)) == []      # a scan older than 48 h is no longer shown


def test_no_feeds_is_a_failed_run(make_app):
    app, _ = make_app()
    assert MarketScanner(app.db, (), fetch=fetcher({})).scan(NOW)["outcome"] == "failed"


# ------------------------------------------------------------------ scheduling
def market_app(make_app, mapping=None):
    app, clock = make_app()
    sc = MarketScanner(app.db, FEEDS, fetch=fetcher(mapping or {FEEDS[0]: FEED_A, FEEDS[1]: FEED_B}))
    app.market = app.scheduler.market = sc
    return app, clock, sc


def test_scan_runs_at_once_in_green_and_is_logged_with_estimated_energy(make_app):
    app, clock, _ = market_app(make_app)
    out = app.scheduler.tick()["market"]
    assert out["action"] == "ran" and out["report"]["outcome"] == "ok"
    row = app.db.execute("SELECT decision, mode, kwh, outcome FROM job_log WHERE laptop_id='market-scan'").fetchone()
    assert row[0] == "run_market" and row[1] == "GREEN" and row[2] is not None and row[3] == "ok"
    assert app.scheduler.tick()["market"] == {"action": "not_due"}      # the interval has not passed


@pytest.mark.parametrize("mode", ["AMBER", "RED"])
def test_scan_waits_outside_green_but_never_longer_than_24_hours(make_app, mode):
    app, clock, _ = market_app(make_app)
    set_mode(app, mode)
    assert app.scheduler.tick()["market"]["action"] == "deferred"
    clock.advance(hours=23)
    assert app.scheduler.tick()["market"]["action"] == "deferred"
    clock.advance(hours=1, minutes=1)
    out = app.scheduler.tick()["market"]
    assert out["action"] == "ran"
    row = app.db.execute("SELECT reason FROM job_log WHERE decision='run_market'").fetchone()
    assert "24 h" in row[0]


def test_market_deferrals_do_not_change_the_model_evaluation_rules(make_app):
    app, clock, _ = market_app(make_app)
    set_mode(app, "RED")
    app.scheduler.tick()
    assert app.db.execute("SELECT COUNT(*) FROM job_log WHERE decision='defer_optional'").fetchone()[0] == 1   # only the evaluation's own deferral
    assert app.db.execute("SELECT COUNT(*) FROM job_log WHERE decision='defer_market'").fetchone()[0] == 1


def test_scheduler_without_a_scanner_is_unchanged(make_app):
    app, _ = make_app()
    assert app.market is None and "market" not in app.scheduler.tick()


# ------------------------------------------------------------------ shopper API, operator API, metrics
def test_recommendation_and_forecast_do_not_change_when_signals_exist(make_app):
    app, clock, sc = market_app(make_app)
    app.scheduler.market = None                                          # no scan during the seeding steps
    app.imports.run(synthetic_csv(clock()), "csv", "seed")
    for _ in range(2):
        app.step()
    before = app.service.insights("lap-001")
    assert before["market"]["signals"] == [] and before["market"]["notice"] == NOTICE
    sc.scan(clock())
    after = app.service.insights("lap-001")
    assert after["market"]["signals"]
    for key in ("product", "present", "past", "future", "recommendation", "generated_at"):
        assert after[key] == before[key]


def test_operator_event_is_shown_audited_and_expires(make_app):
    app, clock, _ = market_app(make_app)
    app.imports.run(synthetic_csv(clock()), "csv", "seed")
    c = Client(app)
    assert c.call("POST", "/ops/market-events", {"topic": "DRAM contract prices", "category": "memory", "valid_days": 2})[0] == 401
    code, body, _ = c.call("POST", "/ops/market-events", {"topic": "DRAM contract prices", "category": "memory", "note": "supplier announcement", "valid_days": 2}, headers=OPS)
    assert code == 200 and body["signals"][0]["origin"] == "operator"
    assert c.call("GET", "/products/lap-001/insights")[1]["market"]["signals"][0]["topic"] == "DRAM contract prices"
    assert app.db.execute("SELECT COUNT(*) FROM ops_audit WHERE action='market.event'").fetchone()[0] == 1
    clock.advance(days=3)
    assert c.call("GET", "/products/lap-001/insights")[1]["market"]["signals"] == []
    for bad in ({"topic": ""}, {"topic": "x", "valid_days": 0}, {"topic": "x", "valid_days": 400}, {"topic": "x" * 100}):
        assert c.call("POST", "/ops/market-events", bad, headers=OPS)[0] == 400


def test_ops_market_view_and_metrics(make_app):
    app, clock, _ = market_app(make_app)
    c = Client(app)
    assert c.call("GET", "/ops/market", headers=OPS)[1]["enabled"] is True
    app.scheduler.tick()
    body = c.call("GET", "/ops/market", headers=OPS)[1]
    assert body["runs"][0]["outcome"] == "ok" and body["signals"]
    text = c.call("GET", "/metrics", headers=OPS)[1]
    for name in ("shopping_market_scan_runs_total", "shopping_market_headlines_scanned", "shopping_market_active_signals",
                 "shopping_market_last_success_age_seconds", "shopping_market_source_errors_total", "shopping_market_estimated_energy_kwh_total"):
        assert name in text
    from prometheus_client import parser
    assert list(parser.text_string_to_metric_families(text))


def test_scan_is_off_unless_enabled(make_app, monkeypatch):
    monkeypatch.delenv("SHOPPING_MARKET_SCAN", raising=False)
    app, _ = make_app()
    assert app.market is None
    c = Client(app)
    assert c.call("GET", "/ops/market", headers=OPS)[1]["enabled"] is False
    monkeypatch.setenv("SHOPPING_MARKET_SCAN", "on")
    monkeypatch.setenv("SHOPPING_NEWS_FEEDS", "https://a.example/rss.xml, https://b.example/rss.xml")
    on, _ = make_app()
    assert on.market is not None and on.market.feeds == ("https://a.example/rss.xml", "https://b.example/rss.xml")


# ------------------------------------------------------------------ tags, description, hashtags, wider dictionary
from market_fixtures import rich
from shopping.market import TOPICS, clean_text, search_text


def topic_hits(title):
    text = f" {search_text(title)} "
    return {t.topic for t in TOPICS if any(f" {normalise(p)} " in text for p in t.phrases)}


@pytest.mark.parametrize("title,topic", [
    ("Hyperscalers raise spending on new capacity", "ai_datacentres"), ("Nvidia customers build GPU clusters", "ai_datacentres"), ("Why every company wants an AI factory", "ai_datacentres"),
    ("DDR5 prices jump again", "memory_prices"), ("Memory shortage hits PC makers", "memory_prices"), ("NAND flash demand rises", "memory_prices"),
    ("US Chips Act money reaches new fabs", "chip_supply"), ("Rare earths curbs worry electronics makers", "chip_supply"), ("Chip supply chain disruption continues", "chip_supply"),
    ("New customs duties on electronics", "trade_tariffs"), ("Import tax on laptops raised", "trade_tariffs"), ("Export ban widened", "trade_tariffs"),
    ("Lithium shortage could slow battery output", "batteries"), ("Battery prices fall for a second year", "batteries"), ("Gigafactory opens in Poland", "batteries"),
    ("OLED laptops get cheaper", "displays"), ("Display shortage eases", "displays"), ("Mini LED screens spread to mid-range", "displays"),
])
def test_wider_phrases_match_real_looking_headlines(title, topic):
    assert topic in topic_hits(title)


@pytest.mark.parametrize("title", [
    "Local football results", "Flash flood warning for the coast", "Wafer-thin majority wins vote", "Sanctions on shipping reviewed",
    "Solar panel prices drop again", "The fab four reunite on stage", "Heat wave hits southern Europe", "Contract prices for gas stay flat",
])
def test_ambiguous_single_words_do_not_match(title):
    assert topic_hits(title) == set()


def test_hashtags_are_matched_in_all_spellings():
    for text in ("#AIDataCentres rush", "#ai-data-centres rush", "#ai_data_centres rush", "#DataCentres rush"):
        assert topic_hits(text) == {"ai_datacentres"}, text
    assert topic_hits("#DRAM shortage") == {"memory_prices"}


def test_markup_and_long_fields_are_cleaned_and_limited():
    assert clean_text("<p>AI &amp; <b>chips</b></p>   now", 100) == "AI & chips now"
    items = parse_feed(rich([{"title": "t", "tags": ["x" * 500] + [f"tag{i}" for i in range(20)], "description": "<script>bad()</script>" + "word " * 1000}]))
    assert len(items[0].summary) <= 500 and len(items[0].tags) <= 8 and all(len(t) <= 60 for t in items[0].tags)


def test_atom_category_term_and_dc_subject_are_read():
    feed = (b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/"><entry><title>T</title>'
            b'<category term="Semiconductors"/><dc:subject>Memory</dc:subject><summary>Short &lt;i&gt;text&lt;/i&gt;</summary></entry></feed>')
    item = parse_feed(feed)[0]
    assert item.tags == ("Semiconductors", "Memory") and item.summary == "Short text"


def scan_rich(app, feeds, **kw):
    sc = MarketScanner(app.db, FEEDS, fetch=fetcher(feeds), **kw)
    sc.scan(NOW)
    return {s["topic"]: s for s in current_signals(app.db, NOW)}


def test_tags_and_description_confirm_but_never_count_towards_the_threshold(make_app):
    app, _ = make_app()
    only_extra = [{"title": f"Market report {i}", "link": f"https://a.example/{i}", "tags": ["Data centres"], "description": "Ahead of AI data centres demand"} for i in range(5)]
    assert scan_rich(app, {FEEDS[0]: rich(only_extra), FEEDS[1]: rich(only_extra)}) == {}            # no title matches: no signal
    row = app.db.execute("SELECT mentions, active, samples FROM market_signals WHERE topic='ai_datacentres'").fetchone()
    assert row[0] == 0 and row[1] == 0 and '"supporting": 5' in row[2]                                # reported, not counted


def test_evidence_and_supporting_counts_are_reported(make_app):
    app, _ = make_app()
    a = rich([{"title": "New data centres planned", "link": "https://a.example/1", "tags": ["Data centres"], "description": "Hyperscalers expand"},
              {"title": "Data centres need power", "link": "https://a.example/2"},
              {"title": "Quarterly outlook", "link": "https://a.example/4", "description": "mentions data centres in passing"}])
    b = rich([{"title": "#AIDataCentres boom", "link": "https://b.example/1"}])
    sig = scan_rich(app, {FEEDS[0]: a, FEEDS[1]: b})["ai_datacentres"]
    assert sig["mentions"] == 3 and sig["sources"] == 2 and sig["supporting_mentions"] == 1
    first = next(e for e in sig["examples"] if e["title"] == "New data centres planned")
    assert first["evidence"] == ["title", "tag", "summary"]


def test_description_text_is_not_stored_in_the_database(make_app):
    app, _ = make_app()
    marker = "UNIQUE-DESCRIPTION-MARKER"
    feed = rich([{"title": "New data centres planned", "tags": ["TAG-MARKER"], "description": f"{marker} data centres"}])
    scan_rich(app, {FEEDS[0]: feed, FEEDS[1]: feed}, min_mentions=1, min_sources=1)
    for table in ("market_signals", "market_scan_runs", "market_events", "job_log"):
        dump = " ".join(str(v) for row in app.db.execute(f"SELECT * FROM {table}").fetchall() for v in row)
        assert marker not in dump and "TAG-MARKER" not in dump, table


def test_default_dictionary_has_six_topics_with_unique_ids():
    ids = [t.topic for t in TOPICS]
    assert len(ids) == len(set(ids)) == 6 and all(t.phrases and t.categories for t in TOPICS)
