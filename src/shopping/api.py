"""REST API (WSGI) of docs/data-model-api.md. Pure standard library: `make_wsgi(app)` returns a WSGI callable.

Shopper endpoints need no account: a client-generated device id travels in the `X-Device-Id` header (watches and
alerts only). Operator endpoints (`/ops/*`, `/metrics`) require `Authorization: Bearer <token>`; with no token
configured they are disabled. Requests are serialised by the application lock (one shared database connection).
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import re
import time
from dataclasses import asdict, fields
from datetime import timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs

from .energy import iso
from .market import NOTICE, current_signals
from .policy import Policy, PolicyError, audit as write_audit
from .service import Application, NotFound

WEB = Path(__file__).parent / "web"
MAX_BODY = 64 * 1024
MAX_IMPORT_BODY = 5 * 1024 * 1024
HEADERS = [("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store")]
CSP = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"


class HttpError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def _num(v, name):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise HttpError(400, f"{name} must be a number")


def make_wsgi(app: Application) -> Callable:
    routes: list[tuple[str, re.Pattern, Callable, bool]] = []

    def route(method: str, pattern: str, ops: bool = False):
        def deco(fn):
            routes.append((method, re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$"), fn, ops))
            return fn
        return deco

    class Req:
        def __init__(self, environ, params):
            self.environ, self.params = environ, params
            self.query = {k: v[-1] for k, v in parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True).items()}
            self.device = environ.get("HTTP_X_DEVICE_ID", "")

        def raw(self, limit: int) -> bytes:
            n = int(self.environ.get("CONTENT_LENGTH") or 0)
            if n > limit:
                raise HttpError(413, "request body too large")
            return self.environ["wsgi.input"].read(n) if n else b""

        def json(self) -> dict:
            try:
                data = json.loads(self.raw(MAX_BODY) or b"{}")
            except ValueError:
                raise HttpError(400, "body must be valid JSON")
            if not isinstance(data, dict):
                raise HttpError(400, "body must be a JSON object")
            return data

    # ------------------------------------------------------------------ shopper
    @route("GET", "/products")
    def products(r):
        return app.service.list_products(r.query.get("q", ""), r.query.get("sort", "price"), _num(r.query.get("min_price"), "min_price"), _num(r.query.get("max_price"), "max_price"))

    @route("GET", "/products/compare")
    def compare(r):
        return app.service.compare([x for x in r.query.get("ids", "").split(",") if x])

    @route("GET", "/products/{id}/insights")
    def insights(r):
        brands = tuple(b for b in r.query.get("brands", "").split(",") if b)
        return app.service.insights(r.params["id"], _num(r.query.get("budget"), "budget"), brands)

    @route("POST", "/assistant/ask")
    def ask(r):
        b = r.json()
        pid, question = b.get("productId"), b.get("question", "")
        if not isinstance(pid, str) or not isinstance(question, str):
            raise HttpError(400, "productId and question must be strings")
        sid = str(b.get("sessionId") or "anonymous")[:64]
        payload = app.service.assistant_payload(pid, _num(b.get("budget"), "budget"), tuple(b.get("brands") or ()))
        return app.gateway.ask(question, payload, sid)

    @route("GET", "/status")
    def status(r):
        mode = app.mode_reader.current()[0]
        return {"mode": mode, "notice": "AI explanations are simplified to save energy." if mode == "RED" else None}

    @route("GET", "/watches")
    def watches(r):
        return app.watch.list_watches(r.device)

    @route("PUT", "/watches/{id}")
    def put_watch(r):
        b = r.json()
        w = app.watch.save_watch(r.device, r.params["id"], b.get("targetPrice"))
        if "enabled" in b:
            app.watch.set_enabled(r.device, r.params["id"], bool(b["enabled"]))
            w = app.watch.get_watch(r.device, r.params["id"])
        return w

    @route("DELETE", "/watches/{id}")
    def del_watch(r):
        app.watch.delete_watch(r.device, r.params["id"])
        return {"deleted": True}

    @route("GET", "/alerts")
    def alerts(r):
        return app.watch.list_alerts(r.device, unread_only=r.query.get("unread") in ("1", "true"))

    @route("POST", "/alerts/read")
    def alerts_read(r):
        ids = r.json().get("ids")
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise HttpError(400, "ids must be a list of integers")
        app.watch.mark_read(r.device, ids)
        return {"read": len(ids)}

    # ------------------------------------------------------------------ operator
    @route("GET", "/ops/mode", ops=True)
    def ops_mode(r):
        v, p = app.policy_store.current()
        return {**app.policy.state(), "signals": app.monitor.latest(), "policy": asdict(p)}

    @route("GET", "/ops/simulation", ops=True)
    def get_simulation(r):
        if app.simulation is None:
            return {"available": False, "reason": "start with SHOPPING_FEED=controlled to simulate signals"}
        return {"available": True, **app.simulation.state()}

    @route("PUT", "/ops/simulation", ops=True)
    def put_simulation(r):
        if app.simulation is None:
            raise HttpError(409, "the signal feed is not controllable (SHOPPING_FEED=controlled)")
        b = r.json()
        intensity, price = _num(b.get("intensity"), "intensity"), _num(b.get("price"), "price")
        if intensity is None and price is None:
            raise HttpError(400, "give intensity (gCO2e/kWh), price (EUR/kWh) or both")
        if (intensity is not None and not 0 <= intensity <= 2000) or (price is not None and not -1 <= price <= 10):
            raise HttpError(400, "values out of range")
        now = app.clock()
        with app.lock:
            state = app.simulation.set(intensity, price, bool(b.get("renewable", False)), "operator", now)
            with app.db:
                write_audit(app.db, "operator", "simulation.set", json.dumps({k: state.get(k) for k in ("intensity", "price", "renewable")}), now)
        return state

    @route("DELETE", "/ops/simulation", ops=True)
    def del_simulation(r):
        if app.simulation is None:
            raise HttpError(409, "the signal feed is not controllable (SHOPPING_FEED=controlled)")
        with app.lock:
            app.simulation.clear()
            with app.db:
                write_audit(app.db, "operator", "simulation.clear", "back to the simulated daily wave", app.clock())
        return app.simulation.state()

    @route("GET", "/ops/policy", ops=True)
    def get_policy(r):
        v, p = app.policy_store.current()
        return {"version": v, "policy": asdict(p), "history": app.policy_store.history()[:10]}

    @route("PUT", "/ops/policy", ops=True)
    def put_policy(r):
        b = r.json()
        known = {f.name for f in fields(Policy)}
        if set(b) - known:
            raise HttpError(400, f"unknown policy fields: {sorted(set(b) - known)}")
        merged = {**asdict(app.policy_store.current()[1]), **b}
        try:
            policy = Policy(**merged)
        except TypeError as exc:
            raise HttpError(400, str(exc))
        return {"version": app.policy_store.save(policy, "operator"), "policy": asdict(policy)}

    @route("PUT", "/ops/mode-override", ops=True)
    def put_override(r):
        b = r.json()
        return app.policy.set_override(str(b.get("mode", "")).upper(), _num(b.get("hours"), "hours") or 0, "operator")

    @route("DELETE", "/ops/mode-override", ops=True)
    def del_override(r):
        app.policy.clear_override("operator")
        return {"cleared": True}

    @route("GET", "/ops/imports", ops=True)
    def imports(r):
        return app.imports.reports()

    @route("POST", "/ops/imports", ops=True)
    def run_import(r):
        fmt, kind = r.query.get("format", "csv"), r.query.get("kind", "daily")
        if kind not in ("daily", "backfill"):
            raise HttpError(400, "kind must be daily or backfill")
        return app.imports.run(r.raw(MAX_IMPORT_BODY).decode("utf-8", "replace"), fmt, r.query.get("source", "upload")[:64], kind)

    @route("GET", "/ops/market", ops=True)
    def market(r):
        runs = [dict(zip(("run_at", "mode", "feeds", "failed", "headlines", "signals", "outcome", "detail"), x)) for x in app.db.execute(
            "SELECT run_at, mode, feeds, failed, headlines, signals, outcome, detail FROM market_scan_runs ORDER BY id DESC LIMIT 10")]
        return {"enabled": app.market is not None, "feeds": list(app.market.feeds) if app.market else [], "runs": runs,
                "signals": current_signals(app.db, app.clock()), "notice": NOTICE}

    @route("POST", "/ops/market-events", ops=True)
    def market_event(r):
        b = r.json()
        topic, category, note = str(b.get("topic", "")).strip(), str(b.get("category", "all")).strip() or "all", str(b.get("note", "")).strip()
        days = _num(b.get("valid_days", 7), "valid_days")
        if not 1 <= len(topic) <= 80 or len(category) > 40 or len(note) > 300 or days is None or not 0 < days <= 90:
            raise HttpError(400, "topic 1-80 characters, category up to 40, note up to 300, valid_days 1-90")
        now = app.clock()
        with app.lock, app.db:
            app.db.execute("INSERT INTO market_events (topic, category, note, valid_until, set_by, set_at) VALUES (?, ?, ?, ?, 'operator', ?)",
                           (topic, category, note, iso(now + timedelta(days=days)), iso(now)))
            write_audit(app.db, "operator", "market.event", json.dumps({"topic": topic, "category": category, "valid_days": days}), now)
        return {"stored": True, "signals": current_signals(app.db, now)}

    @route("GET", "/ops/review-queue", ops=True)
    def review(r):
        return app.gateway.review_queue()

    @route("POST", "/ops/review-queue/{id}/decision", ops=True)
    def review_decide(r):
        if not r.params["id"].isdigit():
            raise HttpError(400, "id must be an integer")
        if not app.gateway.review_decide(int(r.params["id"]), str(r.json().get("decision", ""))):
            raise HttpError(404, "no open review item with this id")
        return {"decided": True}

    @route("GET", "/ops/models", ops=True)
    def models(r):
        return app.registry.rows()

    @route("PUT", "/ops/model/active", ops=True)
    def set_model(r):
        b = r.json()
        app.registry.set_active(str(b.get("model_id", "")), bool(b.get("pinned", True)), "set by operator")
        return {"active": app.registry.active(), "pinned": app.registry.pinned()}

    @route("GET", "/ops/placement", ops=True)
    def placement(r):
        return {"target": app.policy.state()["placement_target"], "decisions": app.placement.decisions()}

    @route("GET", "/ops/drift", ops=True)
    def drift(r):
        return {"checks": app.evaluator.drift(), "models": app.registry.rows()}

    @route("GET", "/ops/jobs", ops=True)
    def jobs(r):
        return {"open": app.scheduler.open_jobs(), "log": app.scheduler.log()}

    @route("GET", "/ops/traces", ops=True)
    def traces(r):
        return app.gateway.traces()

    @route("GET", "/ops/audit", ops=True)
    def audit(r):
        return [dict(zip(("at", "actor", "action", "detail"), x)) for x in app.db.execute("SELECT at, actor, action, detail FROM ops_audit ORDER BY id DESC LIMIT 50")]

    @route("POST", "/ops/step", ops=True)
    def step(r):
        return app.step()

    # ------------------------------------------------------------------ operational
    @route("GET", "/health/live")
    def live(r):
        return {"status": "alive"}

    @route("GET", "/health/ready")
    def ready(r):
        h = app.health()
        if h["status"] != "ready":
            raise HttpError(503, "database unreachable")
        return h

    # ------------------------------------------------------------------ WSGI
    def authorised(environ) -> bool:
        if not app.ops_token:
            return False
        got = environ.get("HTTP_AUTHORIZATION", "")
        return got.startswith("Bearer ") and hmac.compare_digest(got[7:], app.ops_token)

    def respond(start, status: int, body: bytes, ctype: str, extra=()):
        start(f"{status} {_REASON.get(status, 'OK')}", [("Content-Type", ctype), ("Content-Length", str(len(body))), *HEADERS, *extra])
        return [body]

    def wsgi(environ, start_response):
        t0 = time.perf_counter()
        seen = {"status": 500, "route": "other"}
        inner = lambda s, h, *a: (seen.update(status=int(s.split()[0])), start_response(s, h, *a))[1]
        try:
            return handle(environ, inner, seen)
        finally:
            app.http.observe(seen["route"], seen["status"], time.perf_counter() - t0)

    def handle(environ, start_response, seen):
        method, path = environ["REQUEST_METHOD"], environ.get("PATH_INFO", "/")
        try:
            if method == "GET" and path == "/metrics":
                seen["route"] = "/metrics"
                if not authorised(environ):
                    raise HttpError(403, "metrics are internal: operator token required")
                return respond(start_response, 200, app.prometheus().encode(), "text/plain; version=0.0.4")
            if method == "GET" and (path in ("/", "/index.html") or path in ("/app.js", "/style.css")):
                seen["route"] = "static"
                f = WEB / ("index.html" if path in ("/", "/index.html") else path.lstrip("/"))
                return respond(start_response, 200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "text/plain", [("Content-Security-Policy", CSP)])
            allowed = []
            for m, pat, fn, ops in routes:
                match = pat.match(path)
                if not match:
                    continue
                allowed.append(m)
                seen["route"] = re.sub(r"\(\?P<(\w+)>\[\^/\]\+\)", r"{\1}", pat.pattern).strip("^$")
                if m != method:
                    continue
                if ops and not authorised(environ):
                    raise HttpError(403 if not app.ops_token else 401, "operator token required")
                with app.lock:
                    result = fn(Req(environ, match.groupdict()))
                return respond(start_response, 200, json.dumps(result, ensure_ascii=False).encode(), "application/json")
            if allowed:
                raise HttpError(405, "method not allowed")
            raise HttpError(404, "not found")
        except HttpError as exc:
            return respond(start_response, exc.status, json.dumps({"error": exc.message}).encode(), "application/json")
        except NotFound as exc:
            return respond(start_response, 404, json.dumps({"error": str(exc)}).encode(), "application/json")
        except (ValueError, PolicyError) as exc:
            return respond(start_response, 400, json.dumps({"error": str(exc)}).encode(), "application/json")
        except Exception:                                                  # never leak internals
            return respond(start_response, 500, json.dumps({"error": "internal error"}).encode(), "application/json")

    return wsgi


_REASON = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 413: "Payload Too Large",
           500: "Internal Server Error", 503: "Service Unavailable"}
