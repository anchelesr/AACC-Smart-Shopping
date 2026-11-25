"""Multi-process deployment pieces: operator-controlled signal, split control loop, entry point, environment."""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from shopping.policy import Policy
from shopping.service import Application


def call(app, method, path, body=None, token="tok"):
    from shopping.api import make_wsgi
    import io
    data = json.dumps(body).encode() if body is not None else b""
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "", "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data),
           "HTTP_AUTHORIZATION": f"Bearer {token}" if token else ""}
    out = {}
    body_out = b"".join(make_wsgi(app)(env, lambda s, h: out.update(status=int(s.split()[0]))))
    return out["status"], json.loads(body_out or b"{}")


def test_controlled_signal_drives_the_mode_through_the_api(make_app):
    app, clock = make_app(feed_kind="controlled")
    app.policy_store.save(Policy(dwell_minutes=0, consecutive=1), "test")
    assert call(app, "GET", "/ops/simulation")[1]["active"] is False
    st, body = call(app, "PUT", "/ops/simulation", {"intensity": 520, "price": 0.35})
    assert st == 200 and body["active"] and body["intensity"] == 520
    for _ in range(3):
        clock.advance(minutes=1); app.step_control()
    assert app.policy.state()["mode"] == "RED"
    call(app, "PUT", "/ops/simulation", {"intensity": 80, "price": 0.08, "renewable": True})
    for _ in range(3):
        clock.advance(minutes=20); app.step_control()
    assert app.policy.state()["mode"] == "GREEN" and app.policy.state()["placement_target"] == "eco"
    assert call(app, "DELETE", "/ops/simulation")[1]["active"] is False
    actions = [r[0] for r in app.db.execute("SELECT action FROM ops_audit")]
    assert "simulation.set" in actions and "simulation.clear" in actions


def test_simulation_endpoints_are_protected_validated_and_optional(make_app):
    app, _ = make_app(feed_kind="controlled")
    assert call(app, "PUT", "/ops/simulation", {"intensity": 100}, token=None)[0] in (401, 403)
    assert call(app, "PUT", "/ops/simulation", {})[0] == 400
    assert call(app, "PUT", "/ops/simulation", {"intensity": 99999})[0] == 400
    assert call(app, "PUT", "/ops/simulation", {"intensity": "abc"})[0] == 400
    plain, _ = make_app()
    assert call(plain, "GET", "/ops/simulation")[1]["available"] is False
    assert call(plain, "PUT", "/ops/simulation", {"intensity": 100})[0] == 409


def test_control_and_work_steps_are_independent(seeded):
    app, clock = seeded
    c = app.step_control()
    assert set(c) == {"sample", "decision", "placement"}
    w = app.step_work()
    assert set(w) == {"reconciled", "jobs", "watches"}
    assert set(app.step()) == {"sample", "decision", "placement", "reconciled", "jobs", "watches"}


def test_initial_policy_and_mode_cache_are_configurable(make_app):
    app, _ = make_app(initial_policy=Policy(dwell_minutes=0), mode_cache_seconds=1.5)
    assert app.policy_store.current()[1].dwell_minutes == 0 and app.mode_reader.pull_seconds == 1.5


def test_two_processes_seeding_the_policy_at_once_do_not_fail(make_app):
    app, _ = make_app()
    from shopping.policy import PolicyStore
    other = PolicyStore(app.db, initial=Policy(dwell_minutes=1))
    assert other.current()[0] == 1                                    # version 1 exists already: read it, do not fail


def test_cluster_is_chosen_by_environment(monkeypatch):
    from shopping.placement import FakeCluster, KubectlCluster, KubernetesApiCluster
    for kind, cls in (("fake", FakeCluster), ("kubectl", KubectlCluster), ("incluster", KubernetesApiCluster)):
        monkeypatch.setenv("SHOPPING_CLUSTER", kind)
        assert isinstance(Application._default_cluster(), cls)


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def _run(role, port, extra_env=None, db=None):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "SHOPPING_OPS_TOKEN": "t", "SHOPPING_INTERVAL": "1",
           "SHOPPING_DATABASE_URL": f"sqlite://{db}", "SHOPPING_FEED": "controlled", **(extra_env or {})}
    return subprocess.Popen([sys.executable, "-m", "shopping", "--role", role, "--port", str(port)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _wait(url, secs=15):
    end = time.time() + secs
    while time.time() < end:
        try:
            return urllib.request.urlopen(url, timeout=1).read()
        except OSError:
            time.sleep(0.2)
    raise AssertionError(f"{url} did not answer")


def test_entry_point_roles_share_one_database_and_stop_on_sigterm(tmp_path):
    db, p_api, p_ctl = tmp_path / "s.db", _free_port(), _free_port()
    api = _run("api", p_api, {"SHOPPING_SEED_DEMO": "1"}, db)
    try:
        assert json.loads(_wait(f"http://127.0.0.1:{p_api}/health/ready"))["status"] == "ready"
        ctl = _run("controller", p_ctl, db=db)
        try:
            _wait(f"http://127.0.0.1:{p_ctl}/health/live")
            req = urllib.request.Request(f"http://127.0.0.1:{p_api}/ops/simulation", method="PUT", data=b'{"intensity": 90, "price": 0.1, "renewable": true}',
                                         headers={"Authorization": "Bearer t", "Content-Type": "application/json"})
            assert json.loads(urllib.request.urlopen(req).read())["active"]
            time.sleep(2.5)                                       # the controller runs a step every second and reads the same database
            mode = json.loads(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{p_api}/ops/mode", headers={"Authorization": "Bearer t"})).read())
            assert mode["signals"]["intensity"] == 90 and mode["signals"]["renewable"] is True
        finally:
            ctl.send_signal(signal.SIGTERM)
            assert ctl.wait(timeout=10) == 0
    finally:
        api.send_signal(signal.SIGTERM)
        assert api.wait(timeout=10) == 0


def test_control_loop_thread_can_handle_events_created_on_the_main_thread(make_app):
    """Regression: the in-memory processed-events store was bound to the creating thread, so the first mode.changed
    event handled by the loop thread failed with a ProgrammingError."""
    import threading
    app, clock = make_app(feed_kind="controlled")
    app.policy_store.save(Policy(dwell_minutes=0, consecutive=1), "test")
    call(app, "PUT", "/ops/simulation", {"intensity": 520, "price": 0.35})
    errors = []
    def loop():
        try:
            clock.advance(minutes=1); app.step_control(); app.step_work()
        except Exception as exc:
            errors.append(exc)
    t = threading.Thread(target=loop); t.start(); t.join()
    assert errors == [] and app.policy.state()["mode"] == "RED"


@pytest.mark.skipif(not os.environ.get("SHOPPING_TEST_POSTGRES"), reason="needs SHOPPING_TEST_POSTGRES")
def test_three_roles_start_together_on_postgres_and_share_the_signal():
    """What the Kubernetes deployment does: api, worker and controller start at the same moment on an empty database
    (schema creation and policy seeding race), and a signal set through the api is acted on by the controller."""
    from conftest import reset
    url = os.environ["SHOPPING_TEST_POSTGRES"]
    reset(url)
    env = {"SHOPPING_DATABASE_URL": url, "SHOPPING_MODE_CACHE_SECONDS": "1", "SHOPPING_INITIAL_POLICY": '{"dwell_minutes": 0, "consecutive": 1}', "SHOPPING_SEED_DEMO": "1"}
    ports = {r: _free_port() for r in ("api", "worker", "controller")}
    procs = {r: _run(r, p, env, db="unused") for r, p in ports.items()}
    try:
        for r, p in ports.items():
            assert json.loads(_wait(f"http://127.0.0.1:{p}/health/ready", 30))["status"] == "ready", r
        api = f"http://127.0.0.1:{ports['api']}"
        head = {"Authorization": "Bearer t", "Content-Type": "application/json"}
        urllib.request.urlopen(urllib.request.Request(f"{api}/ops/simulation", method="PUT", data=b'{"intensity": 520, "price": 0.35}', headers=head))
        deadline, seen = time.time() + 30, None
        while time.time() < deadline and seen != "RED":
            seen = json.loads(urllib.request.urlopen(f"{api}/status").read())["mode"]
            time.sleep(0.5)
        assert seen == "RED"                                   # decided by the controller process, read by the api process
        metrics = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{ports['worker']}/metrics", headers=head)).read().decode()
        assert 'shopping_operating_mode{mode="RED"} 1.0' in metrics and 'role="worker"' in metrics     # the worker sees the same state
    finally:
        for p in procs.values():
            p.send_signal(signal.SIGTERM)
        for r, p in procs.items():
            assert p.wait(timeout=15) == 0, r
