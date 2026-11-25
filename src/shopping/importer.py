"""Import of price data (FR-09, FR-10): CSV or JSON batches of offers, validated and stored idempotently.

Pipeline: keep the raw batch (checksum) -> validate every row -> upsert products and retailers -> insert new
observations (core.PriceImporter, which publishes price.changed once per laptop) -> write an import report.
Re-importing the same file changes nothing. The mandatory daily import always runs; an optional backfill is
deferred in AMBER and RED (max deferral 7 days, docs/carbon-adaptation.md).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from events.bus import EventBus
from events.consumer import Metrics

from .core import PriceImporter

REQUIRED = ("laptop_id", "retailer", "observed_at", "price")
MAX_PRICE = 100000.0
MAX_ROWS = 200000
MAX_BACKFILL_DEFERRAL = timedelta(days=7)


def normalise_time(value: str, now: datetime) -> str:
    dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if dt > now + timedelta(days=1):
        raise ValueError("observation is in the future")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_batch(text: str, fmt: str) -> list[dict]:
    if fmt == "json":
        data = json.loads(text)
        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
            raise ValueError("JSON batch must be a list of objects")
        return data
    if fmt == "csv":
        reader = csv.DictReader(io.StringIO(text))
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing columns: {', '.join(missing)}")
        return list(reader)
    raise ValueError("format must be csv or json")


def validate_row(row: dict, now: datetime) -> tuple[Optional[tuple], Optional[str]]:
    """Returns ((laptop, brand, model, retailer, observed_at, price), None) or (None, reason)."""
    try:
        laptop, retailer = str(row.get("laptop_id") or "").strip(), str(row.get("retailer") or "").strip()
        if not laptop or not retailer:
            return None, "missing laptop_id or retailer"
        if len(laptop) > 64 or len(retailer) > 64:
            return None, "identifier too long"
        currency = str(row.get("currency") or "EUR").strip().upper()
        if currency != "EUR":
            return None, f"currency {currency} is not comparable (only EUR)"
        price = float(row.get("price"))
        if not 0 < price <= MAX_PRICE or price != price:
            return None, "price must be a positive amount"
        observed = normalise_time(row.get("observed_at"), now)
    except (TypeError, ValueError) as exc:
        return None, f"invalid value: {exc}"
    brand = str(row.get("brand") or "").strip()[:64] or None
    model = str(row.get("model") or "").strip()[:128] or None
    return (laptop, brand, model, retailer, observed, round(price, 2)), None


class ImportService:
    def __init__(self, db, bus: EventBus, metrics: Optional[Metrics] = None, mode_reader=None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.db, self.metrics, self.mode_reader, self.clock = db, metrics if metrics is not None else Metrics(), mode_reader, clock
        self.importer = PriceImporter(db, bus, self.metrics)

    def run(self, text: str, fmt: str = "csv", source: str = "upload", kind: str = "daily") -> dict:
        """kind 'daily' (mandatory, always runs) or 'backfill' (optional, deferred in AMBER and RED)."""
        now = self.clock()
        mode = self.mode_reader.current()[0] if self.mode_reader else "GREEN"
        if kind == "backfill" and mode != "GREEN" and not self._deferral_exhausted(now):
            self._record_deferral(now, source, mode)
            return {"status": "deferred", "mode": mode, "reason": f"optional backfill deferred in {mode}"}
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if self.db.execute("SELECT 1 FROM raw_batches WHERE checksum=? AND source=?", (checksum, source)).fetchone():
            return self._finish(now, source, mode, kind, "duplicate_batch", 0, 0, 0, 0, ["this exact batch was imported before"])
        try:
            rows = parse_batch(text, fmt)
        except (ValueError, KeyError) as exc:
            return self._finish(now, source, mode, kind, "failed", 0, 0, 0, 0, [f"cannot parse batch: {exc}"])
        if len(rows) > MAX_ROWS:
            return self._finish(now, source, mode, kind, "failed", 0, 0, 0, 0, [f"batch has more than {MAX_ROWS} rows"])
        with self.db:
            self.db.execute("INSERT INTO raw_batches (source, received_at, checksum, record_count, payload) VALUES (?, ?, ?, ?, ?)",
                            (source, now.isoformat(timespec="seconds"), checksum, len(rows), text))
        good, problems = [], []
        for i, row in enumerate(rows, start=1):
            parsed, reason = validate_row(row, now)
            if parsed is None:
                problems.append(f"row {i}: {reason}")
            else:
                good.append(parsed)
        with self.db:
            for laptop, brand, model, retailer, *_ in good:
                self.db.execute("INSERT OR IGNORE INTO products (laptop_id, brand, model) VALUES (?, ?, ?)", (laptop, brand, model))
                self.db.execute("INSERT OR IGNORE INTO retailers (retailer, name) VALUES (?, ?)", (retailer, retailer))
        result = self.importer.import_batch(checksum[:12], [(l, r, t, p) for l, _, _, r, t, p in good])
        status = "ok" if not problems else ("partial" if good else "failed")
        return self._finish(now, source, mode, kind, status, len(good), len(problems), result["accepted"], len(good) - result["accepted"],
                            problems[:50], extra={"published": result["published"], "publish_failed": result["publish_failed"]})

    # ---- bookkeeping
    def _finish(self, now, source, mode, kind, status, accepted, rejected, inserted, unchanged, problems, extra=None) -> dict:
        report = {"status": status, "mode": mode, "accepted": accepted, "rejected": rejected, "inserted": inserted,
                  "unchanged": unchanged, "problems": problems, **(extra or {})}
        with self.db:
            self.db.execute("""INSERT INTO import_runs (source, started_at, finished_at, status, mode, kind, accepted, rejected, inserted, unchanged, report)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (source, now.isoformat(timespec="seconds"), self.clock().isoformat(timespec="seconds"), status, mode, kind,
                             accepted, rejected, inserted, unchanged, json.dumps(report)))
        self.metrics[f"import_{status}"] += 1
        return report

    def _deferral_exhausted(self, now: datetime) -> bool:
        row = self.db.execute("""SELECT MIN(started_at) FROM import_runs WHERE status='deferred' AND kind='backfill'
                                 AND started_at > COALESCE((SELECT MAX(started_at) FROM import_runs WHERE kind='backfill' AND status IN ('ok', 'partial')), '')""").fetchone()
        return bool(row and row[0] and now - datetime.fromisoformat(row[0]) >= MAX_BACKFILL_DEFERRAL)

    def _record_deferral(self, now, source, mode) -> None:
        with self.db:
            self.db.execute("INSERT INTO import_runs (source, started_at, finished_at, status, mode, kind, report) VALUES (?, ?, ?, 'deferred', ?, 'backfill', ?)",
                            (source, now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"), mode, json.dumps({"reason": "deferred"})))
        self.metrics["import_deferred"] += 1

    def reports(self, limit: int = 20) -> list[dict]:
        return [{"id": i, "source": s, "started_at": a, "status": st, "mode": m, "accepted": ac, "rejected": rj, "inserted": ins, "unchanged": un,
                 "report": json.loads(rep) if rep else None}
                for i, s, a, st, m, ac, rj, ins, un, rep in self.db.execute(
                    "SELECT id, source, started_at, status, mode, accepted, rejected, inserted, unchanged, report FROM import_runs ORDER BY id DESC LIMIT ?", (limit,))]
