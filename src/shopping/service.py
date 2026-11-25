"""Shopping service: the read side of the shopper API (products, insights, compare, assistant payload) and the
application wiring (`Application`) with one `step()` that runs the control loop once."""
from __future__ import annotations

import os
import statistics
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from events.bus import EventBus, InMemoryBus
from events.consumer import Metrics, ProcessedStore, drain
from events.model import TOPIC_MODE, TOPIC_PRICE

from .advice import Constraints, advise
from .catalog import current_offers, find_alternatives, lowest_offer
from .core import ModeReader
from .db import open_database
from .energy import CarbonMonitor, ControlledFeed, EnergyFeed, SimulatedFeed, age_minutes, iso
from .forecast import FORECAST_MAX_AGE, ForecastWorker, ModelEvaluator, ModelRegistry, daily_series, evidence_for, forecast_for
from .importer import ImportService
from .metrics import Histogram
from .llm.gateway import LlmGateway
from .llm.providers import LlmProvider, ModelByMode, OpenAICompatibleProvider, StandInLocalModel
from .placement import Cluster, FakeCluster, KubectlCluster, KubernetesApiCluster, Node, PlacementController
from .policy import Policy, PolicyEngine, PolicyStore
from .scheduler import Scheduler
from .watch import WatchService


class NotFound(LookupError):
    pass


class ShoppingService:
    def __init__(self, db, clock: Callable[[], datetime]) -> None:
        self.db, self.clock = db, clock

    def _product(self, laptop_id: str) -> dict:
        row = self.db.execute("SELECT laptop_id, brand, model FROM products WHERE laptop_id=?", (laptop_id,)).fetchone()
        if row is None:
            raise NotFound("unknown laptop")
        return {"id": row[0], "brand": row[1], "model": row[2]}

    def list_products(self, q: str = "", sort: str = "price", min_price: Optional[float] = None, max_price: Optional[float] = None) -> list[dict]:
        out = []
        for lid, brand, model in self.db.execute("SELECT laptop_id, brand, model FROM products ORDER BY laptop_id"):
            if q and q.lower() not in f"{lid} {brand} {model}".lower():
                continue
            offers = current_offers(self.db, lid)
            best = offers[0] if offers else None
            if best is not None and ((min_price is not None and best["price"] < min_price) or (max_price is not None and best["price"] > max_price)):
                continue
            if best is None and (min_price is not None or max_price is not None):
                continue
            out.append({"id": lid, "brand": brand, "model": model, "best_offer": best, "retailers": len(offers)})
        keys = {"price": lambda p: (p["best_offer"] is None, p["best_offer"]["price"] if p["best_offer"] else 0, p["id"]),
                "price_desc": lambda p: (p["best_offer"] is None, -(p["best_offer"]["price"] if p["best_offer"] else 0), p["id"]),
                "name": lambda p: ((p["brand"] or ""), (p["model"] or ""), p["id"])}
        if sort not in keys:
            raise ValueError("sort must be price, price_desc or name")
        return sorted(out, key=keys[sort])

    def insights(self, laptop_id: str, budget: Optional[float] = None, brands: tuple = ()) -> dict:
        prod = self._product(laptop_id)
        now = self.clock()
        constraints = Constraints(budget, tuple(brands))
        offers = current_offers(self.db, laptop_id)
        best = offers[0] if offers else None
        if best:
            age = now - datetime.fromisoformat(best["observed_at"]).replace(tzinfo=datetime.fromisoformat(best["observed_at"]).tzinfo or timezone.utc)
            best = {**best, "currency": "EUR", "freshness": "FRESH" if age <= FORECAST_MAX_AGE else "STALE"}
        series = daily_series(self.db, laptop_id, now)
        ev = evidence_for(self.db, laptop_id, now)
        fc, fc_detail = forecast_for(self.db, laptop_id, now)
        adv = advise(ev, fc, constraints)
        ref = statistics.median(p for _, p in series) if len(series) >= 1 else None
        rec = {"action": adv.action, "reasons": list(adv.reasons), "caveats": list(adv.caveats)}
        if budget is not None or brands:
            rec["within_budget"] = adv.within_budget
            rec["alternatives"] = find_alternatives(self.db, constraints, laptop_id) if adv.needs_alternatives else []
        return {"product": prod,
                "present": {"best_offer": best, "offers": offers},
                "past": {"reference_30d": ref, "reference_method": "median_of_daily_lowest_valid_offer", "observation_days": len(series),
                         "sufficient": ev.sufficient, "discount_delta_pct": None if ev.delta is None else round(ev.delta * 100, 2),
                         "history": [{"date": d.isoformat(), "price": p} for d, p in series]},
                "future": fc_detail, "recommendation": rec, "generated_at": iso(now)}

    def compare(self, ids: list[str]) -> list[dict]:
        if not 2 <= len(ids) <= 3:
            raise ValueError("compare needs two or three laptop ids")
        rows = []
        for lid in ids:
            ins = self.insights(lid)
            rows.append({"product": ins["product"], "best_offer": ins["present"]["best_offer"], "retailers": len(ins["present"]["offers"]),
                         "reference_30d": ins["past"]["reference_30d"], "discount_delta_pct": ins["past"]["discount_delta_pct"],
                         "action": ins["recommendation"]["action"], "forecast_status": ins["future"]["status"]})
        return rows

    def assistant_payload(self, laptop_id: str, budget: Optional[float] = None, brands: tuple = ()) -> dict:
        ins = self.insights(laptop_id, budget, brands)
        rec, fut = ins["recommendation"], ins["future"]
        best = ins["present"]["best_offer"]
        return {"laptop": ins["product"], "action": rec["action"], "reasons": rec["reasons"], "caveats": rec["caveats"],
                "best_offer": None if best is None else {"retailer": best["retailer"], "price": best["price"], "observed_at": best["observed_at"]},
                "reference_30d": ins["past"]["reference_30d"], "delta_pct": ins["past"]["discount_delta_pct"],
                "forecast": {"status": fut["status"], "change_pct": None if fut.get("change") is None else round(fut["change"] * 100, 2)},
                "budget": budget, "within_budget": rec.get("within_budget"),
                "alternatives": [{"id": a["laptop_id"], "model": a["model"], "price": a["price"]} for a in rec.get("alternatives", [])]}


class Application:
    """Composition root: every component of docs/architecture.md that is implemented, wired together."""

    def __init__(self, db_url: str = "sqlite://:memory:", bus: Optional[EventBus] = None, clock: Optional[Callable[[], datetime]] = None,
                 feed: Optional[EnergyFeed] = None, cluster: Optional[Cluster] = None, small: Optional[LlmProvider] = None,
                 large: Optional[LlmProvider] = None, ops_token: Optional[str] = None, feed_kind: str = "simulated",
                 initial_policy: Optional[Policy] = None, mode_cache_seconds: float = 60.0) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = threading.RLock()
        self.db = open_database(db_url)
        self.bus = bus or InMemoryBus()
        self.metrics, self.store = Metrics(), ProcessedStore()
        self.ops_token = ops_token
        self.http = Histogram()
        self.mode_reader = ModeReader(self.db, pull_seconds=mode_cache_seconds)
        if feed is None:
            feed = ControlledFeed(self.db) if feed_kind == "controlled" else SimulatedFeed()
        self.simulation = feed if isinstance(feed, ControlledFeed) else None     # operator-controlled signal (demonstration)
        self.monitor = CarbonMonitor(self.db, feed, self.metrics, self.clock)
        self.policy_store = PolicyStore(self.db, self.clock, initial_policy)
        self.policy_store.current()                                        # seeds version 1
        self.policy = PolicyEngine(self.db, self.bus, self.metrics, self.monitor, self.policy_store, self.clock)
        self.registry = ModelRegistry(self.db)
        self.worker = ForecastWorker(self.db, self.registry)
        self.evaluator = ModelEvaluator(self.db, self.registry)
        self.scheduler = Scheduler(self.db, self.worker, self.evaluator, lambda: self.policy_store.current()[1], self.mode_reader,
                                   self.monitor.latest, self.metrics, self.clock,
                                   assumed_duration_s=float(os.environ["SHOPPING_JOB_ASSUMED_SECONDS"]) if os.environ.get("SHOPPING_JOB_ASSUMED_SECONDS") else None)
        self.cluster = cluster or self._default_cluster()
        self.placement = PlacementController(self.db, self.cluster, lambda: self.policy_store.current()[1], self.metrics, self.clock)
        self.imports = ImportService(self.db, self.bus, self.metrics, self.mode_reader, self.clock)
        self.watch = WatchService(self.db, self.metrics)
        self.service = ShoppingService(self.db, self.clock)
        self.gateway = LlmGateway(self.db, small or self._default_small(self.mode_reader), large or self._default_large(), self.mode_reader, self.monitor.latest, self.metrics, clock=self.clock)
        self._price_c = self.bus.subscribe(TOPIC_PRICE, "job-scheduler")
        self._mode_c = self.bus.subscribe(TOPIC_MODE, "app-mode-cache")

    @staticmethod
    def _default_cluster() -> Cluster:
        kind = os.environ.get("SHOPPING_CLUSTER", "fake")                  # fake | incluster | kubectl
        if kind == "incluster":
            return KubernetesApiCluster(base_url=os.environ.get("SHOPPING_K8S_API_URL"))
        if kind == "kubectl":
            return KubectlCluster()
        return FakeCluster([Node("standard-1", "standard"), Node("eco-1", "eco")])

    @staticmethod
    def _default_small(mode_reader=None) -> LlmProvider:
        url = os.environ.get("SHOPPING_LOCAL_MODEL_URL")                   # e.g. http://ollama:11434/v1 (Ollama) or a llama.cpp server
        if not url:
            return StandInLocalModel()
        green = OpenAICompatibleProvider(url, os.environ.get("SHOPPING_LOCAL_MODEL", "local"), "local", json_mode=True,
                                         timeout=float(os.environ.get("SHOPPING_LOCAL_MODEL_TIMEOUT", "60")))
        amber_name = os.environ.get("SHOPPING_LOCAL_MODEL_AMBER")           # dynamic model exchange: a smaller model in AMBER
        if amber_name and mode_reader is not None:
            amber = OpenAICompatibleProvider(url, amber_name, "local", json_mode=True, timeout=green.timeout)
            return ModelByMode({"GREEN": green, "AMBER": amber}, mode_reader)
        return green

    @staticmethod
    def _default_large() -> Optional[LlmProvider]:
        url, key = os.environ.get("SHOPPING_LARGE_MODEL_URL"), os.environ.get("SHOPPING_LARGE_MODEL_KEY")
        return OpenAICompatibleProvider(url, os.environ.get("SHOPPING_LARGE_MODEL", "large"), "external", key) if url else None

    def step_control(self) -> dict:
        """Sense -> decide -> place. Run by the controller role (one replica)."""
        with self.lock:
            sample = self.monitor.collect()
            decision = self.policy.evaluate()
            if decision["changed"]:
                self.mode_reader.on_mode_changed(None)
            drain(self._mode_c, "app-mode-cache", self.mode_reader.on_mode_changed, self.store, self.bus, self.metrics)
            placement = self.placement.reconcile()
            return {"sample": sample, "decision": decision, "placement": placement}

    def step_work(self) -> dict:
        """Price events -> jobs -> run due jobs -> watches. Run by the worker role (replicas may differ in node pool)."""
        with self.lock:
            drain(self._price_c, "job-scheduler", self.scheduler.on_price_changed, self.store, self.bus, self.metrics)
            reconciled = self.scheduler.reconcile()
            jobs = self.scheduler.tick()
            watches = self.watch.run_check(self.clock())
            return {"reconciled": reconciled, "jobs": jobs, "watches": watches}

    def step(self) -> dict:
        """One pass of the whole control loop (single-process mode and `POST /ops/step`)."""
        return {**self.step_control(), **self.step_work()}

    def health(self) -> dict:
        try:
            with self.lock:
                self.db.execute("SELECT 1").fetchone()
            return {"status": "ready"}
        except Exception as exc:
            return {"status": "not ready", "error": type(exc).__name__}

    def prometheus(self) -> str:
        from .metrics import render
        return render(self, self.http)
