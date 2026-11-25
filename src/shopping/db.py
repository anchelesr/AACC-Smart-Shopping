"""Database access (IDataAccess): SQLite for the demonstration and tests, PostgreSQL for the deployment.

The application code uses the small part of the sqlite3 API that both back ends offer: execute, executemany,
commit, rollback and `with db:`. `PgConnection` gives PostgreSQL the same surface and rewrites the few
SQLite-specific constructs (`?` placeholders, `INSERT OR IGNORE`, `datetime('now')`). An integrity violation is
re-raised as `sqlite3.IntegrityError` so that the callers need one exception type.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Iterable

from .schema import DDL, to_postgres

_NOW_PG = "to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')"


def translate(sql: str) -> str:
    """SQLite -> PostgreSQL for run-time statements."""
    s = sql.strip().rstrip(";")
    ignore = re.match(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", s) is not None
    if ignore:
        s = re.sub(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", s, count=1) + " ON CONFLICT DO NOTHING"
    s = s.replace("datetime('now')", _NOW_PG)
    return s.replace("?", "%s")


class PgConnection:
    """sqlite3-like wrapper around a psycopg connection."""

    def __init__(self, dsn: str) -> None:
        import psycopg                       # imported lazily: only the PostgreSQL back end needs it
        self._psycopg = psycopg
        self.raw = psycopg.connect(dsn)
        self.raw.autocommit = False

    def execute(self, sql: str, params: Iterable[Any] = ()):
        cur = self.raw.cursor()
        try:
            cur.execute(translate(sql), tuple(params))
        except self._psycopg.errors.IntegrityError as exc:
            self.raw.rollback()
            raise sqlite3.IntegrityError(str(exc)) from exc
        return cur

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]):
        cur = self.raw.cursor()
        try:
            cur.executemany(translate(sql), [tuple(p) for p in seq])
        except self._psycopg.errors.IntegrityError as exc:
            self.raw.rollback()
            raise sqlite3.IntegrityError(str(exc)) from exc
        return cur

    def executescript(self, script: str) -> None:
        with self.raw.cursor() as cur:
            cur.execute(script)
        self.raw.commit()

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()

    def __enter__(self) -> "PgConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()


def open_database(url: str = "sqlite://:memory:"):
    """`sqlite://<path>` or `postgresql://user:password@host:port/db`; creates the schema if it is missing."""
    if url.startswith(("postgresql://", "postgres://")):
        db = PgConnection(url)
        # several processes (api, worker, controller) start together: only one may create the schema at a time
        with db.raw.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(727274)")
            try:
                cur.execute(to_postgres(DDL))
                db.raw.commit()
            finally:
                db.raw.rollback()
                cur.execute("SELECT pg_advisory_unlock(727274)")
        db.raw.commit()
        return db
    path = url[len("sqlite://"):] if url.startswith("sqlite://") else url
    db = sqlite3.connect(path or ":memory:", check_same_thread=False)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(DDL)
    return db
