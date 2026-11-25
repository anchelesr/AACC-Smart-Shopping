"""Watch Monitor: device-scoped price watch with in-app alerts (FR-06).

No account and no personal data: the client generates a random device id and the server stores only that id,
the laptop id and the target price. A scheduled check (the pull path) compares the latest fresh comparable price
with each target. An alert is created once per episode (price at or below the target); it is persisted together
with its deduplication key in one transaction, and the episode ends when a fresh price rises above the target.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from events.consumer import Metrics

from .catalog import lowest_offer

DEVICE_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")
MAX_WATCHES_PER_DEVICE = 20          # demonstration limit
MAX_AGE = timedelta(hours=48)        # an observation older than this is stale and never triggers an alert


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class WatchService:
    def __init__(self, db: sqlite3.Connection, metrics: Optional[Metrics] = None, max_age: timedelta = MAX_AGE) -> None:
        self.db, self.metrics, self.max_age = db, metrics if metrics is not None else Metrics(), max_age

    # ---- IWatchlist (called by the Shopping API on behalf of a device)
    def save_watch(self, device_id: str, laptop_id: str, target_price: float) -> dict:
        if not DEVICE_ID.match(device_id or ""):
            raise ValueError("invalid device id")
        if not isinstance(target_price, (int, float)) or isinstance(target_price, bool) or not 0 < target_price <= 100000:
            raise ValueError("target price must be a positive amount")
        if self.db.execute("SELECT 1 FROM products WHERE laptop_id=?", (laptop_id,)).fetchone() is None:
            raise ValueError("unknown laptop")
        row = self.db.execute("SELECT id, target_price FROM watches WHERE device_id=? AND laptop_id=?", (device_id, laptop_id)).fetchone()
        with self.db:
            if row is None:
                if self.db.execute("SELECT COUNT(*) FROM watches WHERE device_id=?", (device_id,)).fetchone()[0] >= MAX_WATCHES_PER_DEVICE:
                    raise ValueError("too many watches for this device")
                self.db.execute("INSERT INTO watches (device_id, laptop_id, target_price) VALUES (?, ?, ?)", (device_id, laptop_id, target_price))
            elif row[1] != target_price:             # a new target starts a new episode
                self.db.execute("UPDATE watches SET target_price=?, alerted=0, episode=episode+1 WHERE id=?", (target_price, row[0]))
        return self.get_watch(device_id, laptop_id)

    def get_watch(self, device_id: str, laptop_id: str) -> dict:
        r = self.db.execute("SELECT laptop_id, target_price, enabled FROM watches WHERE device_id=? AND laptop_id=?", (device_id, laptop_id)).fetchone()
        return {"laptop_id": r[0], "target_price": r[1], "enabled": bool(r[2])}

    def list_watches(self, device_id: str) -> list[dict]:
        return [{"laptop_id": l, "target_price": t, "enabled": bool(e)} for l, t, e in
                self.db.execute("SELECT laptop_id, target_price, enabled FROM watches WHERE device_id=? ORDER BY laptop_id", (device_id,))]

    def set_enabled(self, device_id: str, laptop_id: str, enabled: bool) -> None:     # alert preference: pause or resume
        with self.db:
            self.db.execute("UPDATE watches SET enabled=? WHERE device_id=? AND laptop_id=?", (1 if enabled else 0, device_id, laptop_id))

    def delete_watch(self, device_id: str, laptop_id: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM watches WHERE device_id=? AND laptop_id=?", (device_id, laptop_id))

    def list_alerts(self, device_id: str, unread_only: bool = False) -> list[dict]:
        q = """SELECT a.id, w.laptop_id, a.price, w.target_price, a.retailer, a.observed_at, a.created_at, a.read_at
               FROM alerts a JOIN watches w ON w.id = a.watch_id WHERE w.device_id = ?""" + (" AND a.read_at IS NULL" if unread_only else "") + " ORDER BY a.id"
        keys = ("id", "laptop_id", "price", "target_price", "retailer", "observed_at", "created_at", "read_at")
        return [dict(zip(keys, r)) for r in self.db.execute(q, (device_id,))]

    def mark_read(self, device_id: str, alert_ids: list[int]) -> None:
        with self.db:
            for aid in alert_ids:
                self.db.execute("""UPDATE alerts SET read_at = datetime('now') WHERE id = ? AND read_at IS NULL
                                   AND watch_id IN (SELECT id FROM watches WHERE device_id = ?)""", (aid, device_id))

    # ---- IWatchCheck (started by the scheduler)
    def run_check(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now(timezone.utc)
        out = {"checked": 0, "alerted": 0, "already_alerted": 0, "stale": 0, "not_reached": 0, "reset": 0}
        for wid, laptop_id, target, alerted, episode in self.db.execute(
                "SELECT id, laptop_id, target_price, alerted, episode FROM watches WHERE enabled=1 ORDER BY id").fetchall():
            out["checked"] += 1
            offer = lowest_offer(self.db, laptop_id)
            if offer is None or now - _parse(offer["observed_at"]) > self.max_age:
                out["stale"] += 1                       # stale or missing data never triggers or resets anything
                continue
            if offer["price"] <= target:
                if alerted:
                    out["already_alerted"] += 1
                    continue
                try:
                    with self.db:                       # flag and alert in one transaction
                        if self.db.execute("UPDATE watches SET alerted=1 WHERE id=? AND alerted=0", (wid,)).rowcount == 0:
                            out["already_alerted"] += 1
                            continue
                        self.db.execute("INSERT INTO alerts (watch_id, price, retailer, observed_at, dedup_key) VALUES (?, ?, ?, ?, ?)",
                                        (wid, offer["price"], offer["retailer"], offer["observed_at"], f"{wid}:{episode}"))
                    out["alerted"] += 1
                except sqlite3.IntegrityError:          # the alert of this episode already exists: the transaction was rolled back
                    out["already_alerted"] += 1
            else:
                out["not_reached"] += 1
                if alerted:                             # the price rose above the target: the next dip alerts again
                    with self.db:
                        self.db.execute("UPDATE watches SET alerted=0, episode=episode+1 WHERE id=?", (wid,))
                    out["reset"] += 1
        with self.db:
            self.db.execute("INSERT INTO watch_checks (run_at, checked, alerted, skipped) VALUES (?, ?, ?, ?)",
                            (now.isoformat(timespec="seconds"), out["checked"], out["alerted"], out["stale"] + out["not_reached"]))
        for k, v in out.items():
            if v:
                self.metrics[f"watch_{k}"] += v
        return out
