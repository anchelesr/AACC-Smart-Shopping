"""Event envelope and the two topic schemas (FR-19).

An event is a small notification, not state: the database stays the source of truth.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

TOPIC_PRICE = "price.changed"   # key = laptop id; consumers: Job Scheduler
TOPIC_MODE = "mode.changed"     # key = "operating-mode" (one partition, strict order)
TOPIC_DEAD = "events.dead"      # events that failed after all attempts, or could not be parsed
MODE_KEY = "operating-mode"
SCHEMA_VERSION = 1

MODES = {"GREEN", "AMBER", "RED"}
POOLS = {"standard", "eco"}

_FIELDS = {
    TOPIC_PRICE: {"laptop_id": str, "batch_id": str, "new_observations": int},
    TOPIC_MODE: {"mode": str, "reason": str, "since": str, "placement_target": str, "policy_version": int},
}


class InvalidEvent(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    key: str
    occurred_at: str
    data: dict = field(default_factory=dict)
    version: int = SCHEMA_VERSION

    @staticmethod
    def new(topic: str, key: str, data: dict) -> "Event":
        ev = Event(id=str(uuid.uuid4()), type=topic, key=key, occurred_at=_now(), data=dict(data))
        ev.validate()
        return ev

    def validate(self) -> None:
        schema = _FIELDS.get(self.type)
        if schema is None:
            raise InvalidEvent(f"unknown event type {self.type!r}")
        if not self.id or not self.key:
            raise InvalidEvent("id and key are required")
        for name, typ in schema.items():
            if name not in self.data or not isinstance(self.data[name], typ) or isinstance(self.data[name], bool):
                raise InvalidEvent(f"{self.type}: field {name!r} missing or not {typ.__name__}")
        if self.type == TOPIC_MODE:
            if self.data["mode"] not in MODES:
                raise InvalidEvent(f"mode must be one of {sorted(MODES)}")
            if self.data["placement_target"] not in POOLS:
                raise InvalidEvent(f"placement_target must be one of {sorted(POOLS)}")
        if self.type == TOPIC_PRICE and self.data["new_observations"] < 1:
            raise InvalidEvent("new_observations must be at least 1")

    def to_bytes(self) -> bytes:
        return json.dumps(
            {"id": self.id, "type": self.type, "key": self.key, "occurred_at": self.occurred_at,
             "version": self.version, "data": self.data}, sort_keys=True).encode("utf-8")

    @staticmethod
    def from_bytes(raw: bytes) -> "Event":
        try:
            obj = json.loads(raw.decode("utf-8"))
            ev = Event(id=obj["id"], type=obj["type"], key=obj["key"], occurred_at=obj["occurred_at"],
                       data=obj["data"], version=obj.get("version", SCHEMA_VERSION))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise InvalidEvent(f"cannot parse event: {exc}") from exc
        ev.validate()
        return ev
