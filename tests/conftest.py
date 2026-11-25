import os
from datetime import datetime, timezone

import pytest

from shopping.energy import Reading, StaticFeed
from shopping.seed import synthetic_csv
from shopping.service import Application

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        from datetime import timedelta
        self.t += timedelta(**kw)


def database_urls():
    urls = ["sqlite://:memory:"]
    if os.environ.get("SHOPPING_TEST_POSTGRES"):
        urls.append(os.environ["SHOPPING_TEST_POSTGRES"])
    return urls


def reset(url):
    """Empty PostgreSQL schema between tests (SQLite is in memory)."""
    if url.startswith("postgresql"):
        import psycopg
        with psycopg.connect(url, autocommit=True) as c:
            c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")


@pytest.fixture(params=database_urls(), ids=lambda u: u.split(":")[0])
def make_app(request):
    """Factory for applications on every configured database (SQLite always, PostgreSQL when SHOPPING_TEST_POSTGRES is set)."""
    reset(request.param)
    made = []

    def factory(clock=None, feed=None, **kw):
        clock = clock or Clock()
        app = Application(request.param, clock=clock, feed=feed or (None if kw.get('feed_kind') == 'controlled' else StaticFeed(Reading(200.0, 0.10, False))), ops_token="tok", **kw)
        made.append(app)
        return app, clock
    yield factory
    for a in made:
        a.db.close()


@pytest.fixture
def seeded(make_app):
    app, clock = make_app()
    app.imports.run(synthetic_csv(clock()), "csv", "seed")
    return app, clock
