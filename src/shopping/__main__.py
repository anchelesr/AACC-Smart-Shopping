"""Run the application:  python -m shopping --demo   (SQLite in memory, synthetic prices, simulated signals).

Roles (`--role`, default `all`): `api` serves the REST API and the page; `worker` runs the forecast jobs and the watch
check; `controller` senses the energy signals, decides the operating mode and places workloads (run ONE replica);
`all` does everything in one process (demonstration, tests). Roles share the database.

    SHOPPING_DATABASE_URL=postgresql://user:pw@host:5432/shopping python -m shopping --role api --port 8080
    SHOPPING_OPS_TOKEN=...            operator token (required for /ops and /metrics)
    SHOPPING_FEED=simulated|controlled  controlled: signals are set with PUT /ops/simulation (demonstration)
    SHOPPING_CLUSTER=fake|incluster|kubectl   how the controller reaches Kubernetes (incluster: REST API, service account)
    SHOPPING_INITIAL_POLICY={"dwell_minutes":0}   policy of version 1 when the database is empty (JSON)
    SHOPPING_MODE_CACHE_SECONDS=60    lifetime of the cached operating mode (default 60)
    SHOPPING_SEED_DEMO=1              load synthetic prices when the database has none (idempotent)
    KAFKA_BOOTSTRAP=host:9092         use Kafka instead of the in-memory bus
    SHOPPING_LOCAL_MODEL_URL=...      OpenAI-compatible local runtime (otherwise a deterministic stand-in answers)
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
from datetime import datetime, timezone
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .api import make_wsgi
from .policy import Policy
from .seed import synthetic_csv
from .service import Application

ROLES = ("api", "worker", "controller", "all")


class _Threading(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _Quiet(WSGIRequestHandler):
    def log_message(self, *a):
        pass


def build(demo: bool, seed: bool = False) -> Application:
    bus = None
    if os.environ.get("KAFKA_BOOTSTRAP"):
        from events.bus import KafkaBus, ensure_topics
        ensure_topics(os.environ["KAFKA_BOOTSTRAP"])
        bus = KafkaBus(os.environ["KAFKA_BOOTSTRAP"])
    token = os.environ.get("SHOPPING_OPS_TOKEN") or ("demo-ops-token" if demo else None)
    initial = Policy(**json.loads(os.environ["SHOPPING_INITIAL_POLICY"])).validate() if os.environ.get("SHOPPING_INITIAL_POLICY") else None
    app = Application(os.environ.get("SHOPPING_DATABASE_URL", "sqlite://:memory:"), bus=bus, ops_token=token,
                      feed_kind=os.environ.get("SHOPPING_FEED", "simulated"), initial_policy=initial,
                      mode_cache_seconds=float(os.environ.get("SHOPPING_MODE_CACHE_SECONDS", "60")))
    if demo or seed:
        with app.lock:
            have = app.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        if have == 0:                                      # idempotent: a second start finds the data
            report = app.imports.run(synthetic_csv(datetime.now(timezone.utc)), "csv", "synthetic-demo")
            print("demo data:", {k: v for k, v in report.items() if k != "problems"}, flush=True)
        app.step()
    return app


def run_loop(name: str, fn, interval: float, stop: threading.Event) -> threading.Thread:
    def loop():
        while not stop.wait(interval):
            try:
                fn()
            except Exception as exc:                          # the loop must survive a failing step
                print(f"{name} step failed:", type(exc).__name__, exc, flush=True)
    t = threading.Thread(target=loop, daemon=True, name=name)
    t.start()
    return t


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="shopping")
    ap.add_argument("--demo", action="store_true", help="load synthetic prices and use the demo operator token")
    ap.add_argument("--role", choices=ROLES, default=os.environ.get("SHOPPING_ROLE", "all"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--interval", type=float, default=float(os.environ.get("SHOPPING_INTERVAL", "30")), help="seconds between control-loop steps")
    a = ap.parse_args(argv)
    os.environ["SHOPPING_ROLE"] = a.role                                   # shown by the metrics (shopping_process_info)
    # only one role seeds the demonstration data, so that replicas do not import it twice
    app = build(a.demo, seed=os.environ.get("SHOPPING_SEED_DEMO") == "1" and a.role in ("all", "controller"))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())                  # Kubernetes sends SIGTERM when it evicts the pod
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if a.role == "all":
        run_loop("step", app.step, a.interval, stop)
    if a.role == "controller":
        run_loop("control", app.step_control, a.interval, stop)
    if a.role == "worker":
        run_loop("work", app.step_work, a.interval, stop)
    srv = make_server(a.host, a.port, make_wsgi(app), server_class=_Threading, handler_class=_Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"role={a.role} listening on http://{a.host}:{a.port}" + ("  (operator token: demo-ops-token)" if a.demo and not os.environ.get("SHOPPING_OPS_TOKEN") else ""), flush=True)
    stop.wait()
    print("stopping", flush=True)
    srv.shutdown()


if __name__ == "__main__":
    main()
