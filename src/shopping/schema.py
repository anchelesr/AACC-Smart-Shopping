"""The relational schema (docs/data-model-api.md) written once in the SQLite dialect.

`to_postgres()` translates it for PostgreSQL (see db.py). Money columns are DOUBLE PRECISION in this
demonstration; a production schema would use NUMERIC(12,2).
"""
from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS retailers (retailer TEXT PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS products (laptop_id TEXT PRIMARY KEY, brand TEXT, model TEXT);
CREATE TABLE IF NOT EXISTS observations (laptop_id TEXT NOT NULL, retailer TEXT NOT NULL, observed_at TEXT NOT NULL, price REAL NOT NULL,
                                         currency TEXT NOT NULL DEFAULT 'EUR', source TEXT NOT NULL DEFAULT 'import',
                                         PRIMARY KEY (laptop_id, retailer, observed_at, source));
CREATE TABLE IF NOT EXISTS raw_batches (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, received_at TEXT NOT NULL,
                                        checksum TEXT NOT NULL, record_count INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, started_at TEXT NOT NULL,
                                        finished_at TEXT, status TEXT NOT NULL, mode TEXT, kind TEXT, accepted INTEGER NOT NULL DEFAULT 0,
                                        rejected INTEGER NOT NULL DEFAULT 0, inserted INTEGER NOT NULL DEFAULT 0,
                                        unchanged INTEGER NOT NULL DEFAULT 0, report TEXT);
CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL, laptop_id TEXT NOT NULL,
                                    target_price REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                                    alerted INTEGER NOT NULL DEFAULT 0, episode INTEGER NOT NULL DEFAULT 0,
                                    created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE (device_id, laptop_id));
CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
                                   price REAL, retailer TEXT, observed_at TEXT, dedup_key TEXT NOT NULL UNIQUE,
                                   created_at TEXT NOT NULL DEFAULT (datetime('now')), read_at TEXT);
CREATE TABLE IF NOT EXISTS watch_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, checked INTEGER, alerted INTEGER, skipped INTEGER);
CREATE TABLE IF NOT EXISTS forecast_runs (laptop_id TEXT, generated_at TEXT);
CREATE TABLE IF NOT EXISTS forecasts (id INTEGER PRIMARY KEY AUTOINCREMENT, laptop_id TEXT NOT NULL, generated_at TEXT NOT NULL,
                                      model_id TEXT NOT NULL, shadow INTEGER NOT NULL DEFAULT 0, base_price REAL, prices TEXT,
                                      change REAL, status TEXT NOT NULL, target_day TEXT, realised REAL, scored_at TEXT);
CREATE TABLE IF NOT EXISTS model_registry (model_id TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0,
                                           mae REAL, baseline_mae REAL, worse_streak INTEGER NOT NULL DEFAULT 0,
                                           evaluated_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS drift_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, checked_at TEXT NOT NULL, model_id TEXT NOT NULL,
                                         live_mae REAL, baseline_mae REAL, n INTEGER, worse INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS forecast_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, laptop_id TEXT, status TEXT, created_at TEXT,
                                          deadline TEXT, lease_until TEXT, next_check TEXT, attempts INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_job_per_laptop ON forecast_jobs(laptop_id) WHERE status IN ('queued', 'running');
CREATE TABLE IF NOT EXISTS job_log (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, laptop_id TEXT, decided_at TEXT NOT NULL,
                                    decision TEXT NOT NULL, reason TEXT, mode TEXT, intensity REAL, kwh REAL, gco2e REAL,
                                    duration_s REAL, outcome TEXT);
CREATE TABLE IF NOT EXISTS operating_mode_state (id INTEGER PRIMARY KEY CHECK (id = 1), mode TEXT, reason TEXT,
                                                 since TEXT, placement_target TEXT, policy_version INTEGER);
INSERT OR IGNORE INTO operating_mode_state VALUES (1, 'GREEN', 'initial', '1970-01-01T00:00:00+00:00', 'standard', 1);
CREATE TABLE IF NOT EXISTS policy_versions (version INTEGER PRIMARY KEY, created_at TEXT NOT NULL, created_by TEXT NOT NULL, policy TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mode_override (id INTEGER PRIMARY KEY CHECK (id = 1), mode TEXT, expires_at TEXT, set_by TEXT, set_at TEXT);
CREATE TABLE IF NOT EXISTS energy_samples (id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT NOT NULL, intensity REAL, price REAL,
                                           renewable INTEGER, status TEXT NOT NULL, source TEXT);
CREATE TABLE IF NOT EXISTS simulation_signal (id INTEGER PRIMARY KEY CHECK (id = 1), intensity REAL, price REAL, renewable INTEGER NOT NULL DEFAULT 0, set_by TEXT, set_at TEXT);
CREATE TABLE IF NOT EXISTS signal_state (signal TEXT PRIMARY KEY, level INTEGER NOT NULL, pending_level INTEGER NOT NULL DEFAULT 0, pending_count INTEGER NOT NULL DEFAULT 0,
                                          last_sample INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS placement_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, decided_at TEXT NOT NULL, mode TEXT,
                                                target_pool TEXT, outcome TEXT NOT NULL, reason TEXT);
CREATE TABLE IF NOT EXISTS traces (id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT NOT NULL, created_at TEXT NOT NULL, route TEXT,
                                   reason TEXT, model TEXT, prompt_version TEXT, v_score INTEGER, tokens_in INTEGER, tokens_out INTEGER,
                                   latency_ms REAL, guardrail TEXT, est_wh REAL, est_gco2e REAL, est_cost_eur REAL, mode TEXT, flagged INTEGER);
CREATE TABLE IF NOT EXISTS review_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT NOT NULL, created_at TEXT NOT NULL,
                                         question TEXT, answer TEXT, reason TEXT, decision TEXT, decided_at TEXT);
CREATE TABLE IF NOT EXISTS token_budget (day TEXT PRIMARY KEY, tokens_used INTEGER NOT NULL DEFAULT 0, large_used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS ops_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS market_scan_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL, mode TEXT, feeds INTEGER NOT NULL, failed INTEGER NOT NULL,
                                             headlines INTEGER NOT NULL, signals INTEGER NOT NULL, outcome TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS market_signals (id INTEGER PRIMARY KEY AUTOINCREMENT, computed_at TEXT NOT NULL, topic TEXT NOT NULL, label TEXT, categories TEXT,
                                           mentions INTEGER NOT NULL, sources INTEGER NOT NULL, window_days INTEGER NOT NULL, active INTEGER NOT NULL, samples TEXT);
CREATE TABLE IF NOT EXISTS market_events (id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, category TEXT, note TEXT, valid_until TEXT NOT NULL, set_by TEXT, set_at TEXT NOT NULL);
"""


def to_postgres(ddl: str) -> str:
    """Translate the SQLite dialect above into PostgreSQL."""
    s = ddl
    s = s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    s = s.replace(" REAL", " DOUBLE PRECISION")
    s = s.replace("(datetime('now'))", "(to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))")
    s = s.replace("INSERT OR IGNORE INTO operating_mode_state VALUES (1, 'GREEN', 'initial', '1970-01-01T00:00:00+00:00', 'standard', 1);",
                  "INSERT INTO operating_mode_state VALUES (1, 'GREEN', 'initial', '1970-01-01T00:00:00+00:00', 'standard', 1) ON CONFLICT DO NOTHING;")
    assert "INSERT OR IGNORE" not in s and "AUTOINCREMENT" not in s
    return s
