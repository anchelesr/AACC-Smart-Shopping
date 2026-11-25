import json
import subprocess
from datetime import timedelta

import pytest

from conftest import Clock
from shopping.placement import FakeCluster, KubectlCluster, Node, PlacementController
from shopping.policy import Policy


def make(db, nodes, clock):
    cluster = FakeCluster(nodes)
    return PlacementController(db, cluster, lambda: Policy(), clock=clock), cluster


def set_target(db, mode, target):
    db.execute("UPDATE operating_mode_state SET mode=?, placement_target=? WHERE id=1", (mode, target)); db.commit()


def blocked(cluster):
    return {n.name: n.blocked for n in cluster.nodes()}


def test_taints_the_non_target_pool_and_releases_the_target(make_app):
    app, clock = make_app()
    pc, cluster = make(app.db, [Node("s1", "standard"), Node("e1", "eco")], clock)
    assert pc.reconcile()["outcome"] == "applied" and blocked(cluster) == {"s1": False, "e1": True}
    clock.advance(minutes=16); set_target(app.db, "AMBER", "eco")
    assert pc.reconcile()["outcome"] == "applied" and blocked(cluster) == {"s1": True, "e1": False}


def test_dwell_time_prevents_flapping_and_unchanged_is_not_spammed(make_app):
    app, clock = make_app()
    pc, cluster = make(app.db, [Node("s1", "standard"), Node("e1", "eco")], clock)
    pc.reconcile(); set_target(app.db, "AMBER", "eco"); clock.advance(minutes=5)
    r = pc.reconcile()
    assert r["outcome"] == "skipped" and "dwell" in r["reason"] and blocked(cluster)["e1"] is True
    clock.advance(minutes=11); pc.reconcile()
    before = app.db.execute("SELECT COUNT(*) FROM placement_decisions").fetchone()[0]
    for _ in range(5):
        pc.reconcile()
    assert app.db.execute("SELECT COUNT(*) FROM placement_decisions").fetchone()[0] == before + 1     # one "unchanged" row, then silence


def test_never_moves_to_a_pool_without_a_ready_node(make_app):
    app, clock = make_app()
    pc, cluster = make(app.db, [Node("s1", "standard"), Node("e1", "eco", ready=False)], clock)
    set_target(app.db, "AMBER", "eco")
    r = pc.reconcile()
    assert r["outcome"] == "skipped" and "no ready node in the eco pool" in r["reason"] and not any(blocked(cluster).values())


def test_does_not_strand_the_other_pool_when_it_has_no_ready_node(make_app):
    app, clock = make_app()
    pc, cluster = make(app.db, [Node("s1", "standard", ready=False), Node("e1", "eco")], clock)
    assert pc.reconcile()["outcome"] == "skipped" and not any(blocked(cluster).values())


def test_unreachable_cluster_changes_nothing_and_is_recorded(make_app):
    app, clock = make_app()
    class Down:
        def nodes(self): raise OSError("api down")
        def set_blocked(self, *a): raise AssertionError("must not be called")
    pc = PlacementController(app.db, Down(), lambda: Policy(), clock=clock)
    assert pc.reconcile()["outcome"] == "skipped" and pc.decisions()[0]["reason"].startswith("cluster unreachable")


def test_a_failure_while_tainting_is_recorded(make_app):
    app, clock = make_app()
    pc, cluster = make(app.db, [Node("s1", "standard"), Node("e1", "eco")], clock)
    cluster.set_blocked = lambda *a: (_ for _ in ()).throw(OSError("forbidden"))
    assert pc.reconcile()["outcome"] == "failed"


def test_full_loop_mode_change_moves_placement(make_app):
    from shopping.energy import Reading, StaticFeed
    feed = StaticFeed(Reading(100, 0.1))
    app, clock = make_app(feed=feed)
    app.step(); assert blocked(app.cluster)["eco-1"] is True
    feed.reading = Reading(350, 0.1)
    app.step(); clock.advance(minutes=16); app.step()
    assert app.policy.state()["mode"] == "AMBER" and blocked(app.cluster) == {"standard-1": True, "eco-1": False}


def test_kubectl_adapter_builds_the_right_commands():
    calls = []
    nodes = {"items": [{"metadata": {"name": "n1", "labels": {"energy-pool": "eco"}}, "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                        "spec": {"taints": [{"key": "energy-role", "value": "blocked", "effect": "NoExecute"}]}},
                       {"metadata": {"name": "ctl", "labels": {}}, "status": {"conditions": []}, "spec": {}}]}
    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(nodes), stderr="")
    k = KubectlCluster(run)
    assert [(n.name, n.pool, n.ready, n.blocked) for n in k.nodes()] == [("n1", "eco", True, True)]
    k.set_blocked("n1", True); k.set_blocked("n1", False)
    assert calls[1][-2:] == ["energy-role=blocked:NoExecute", "--overwrite"] and calls[2][-1] == "energy-role:NoExecute-"


# ---- KubernetesApiCluster against a fake Kubernetes API server (real HTTP, no real cluster)
@pytest.fixture
def k8s(tmp_path):
    from fake_k8s import FakeK8s, node
    srv = FakeK8s([node("s1", "standard"), node("e1", "eco"), {"metadata": {"name": "cp", "labels": {}, "resourceVersion": "1"}, "spec": {}, "status": {}}]).start()
    tok = tmp_path / "token"; tok.write_text("test-token\n")
    from shopping.placement import KubernetesApiCluster
    yield srv, KubernetesApiCluster(base_url=srv.url, token_file=str(tok), ca_file=str(tmp_path / "none"))
    srv.stop()


def test_api_cluster_lists_only_labelled_pool_nodes(k8s):
    srv, cluster = k8s
    assert {(n.name, n.pool, n.ready, n.blocked) for n in cluster.nodes()} == {("s1", "standard", True, False), ("e1", "eco", True, False)}


def test_api_cluster_sets_and_removes_only_its_own_taint(k8s):
    srv, cluster = k8s
    srv.nodes["e1"]["spec"]["taints"] = [{"key": "other", "value": "x", "effect": "NoSchedule"}]
    cluster.set_blocked("e1", True)
    assert {"key": "energy-role", "value": "blocked", "effect": "NoExecute"} in srv.taints("e1") and len(srv.taints("e1")) == 2
    assert [r for r in srv.requests if r[0] == "PATCH"][0][3] == "application/merge-patch+json"
    assert next(n for n in cluster.nodes() if n.name == "e1").blocked is True
    cluster.set_blocked("e1", False)
    assert srv.taints("e1") == [{"key": "other", "value": "x", "effect": "NoSchedule"}]
    cluster.set_blocked("s1", True); cluster.set_blocked("s1", False)
    assert not srv.taints("s1")


def test_api_cluster_refuses_a_stale_resource_version_and_a_bad_token(k8s, tmp_path):
    from shopping.placement import KubernetesApiCluster
    srv, cluster = k8s
    real = cluster.transport
    def racing(method, path, body=None, ct="application/json"):          # another writer changes the node between GET and PATCH
        if method == "PATCH":
            srv.nodes["e1"]["metadata"]["resourceVersion"] = "99"
        return real(method, path, body, ct)
    cluster.transport = racing
    with pytest.raises(OSError, match="409"):
        cluster.set_blocked("e1", True)
    assert not srv.taints("e1")
    bad = tmp_path / "bad"; bad.write_text("wrong")
    with pytest.raises(OSError, match="401"):
        KubernetesApiCluster(base_url=srv.url, token_file=str(bad)).nodes()


def test_controller_with_api_cluster_moves_the_taint_over_http(make_app, k8s):
    srv, cluster = k8s
    app, clock = make_app()
    pc = PlacementController(app.db, cluster, lambda: Policy(), clock=clock)
    assert pc.reconcile()["outcome"] == "applied" and srv.taints("e1") and not srv.taints("s1")
    clock.advance(minutes=16); set_target(app.db, "AMBER", "eco")
    assert pc.reconcile()["outcome"] == "applied" and srv.taints("s1") and not srv.taints("e1")
    srv.fail_next_patch = 1; clock.advance(minutes=16); set_target(app.db, "GREEN", "standard")
    assert pc.reconcile()["outcome"] == "failed"


def test_api_cluster_outside_a_cluster_fails_clearly(monkeypatch):
    from shopping.placement import KubernetesApiCluster
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    with pytest.raises(OSError, match="not running in a cluster"):
        KubernetesApiCluster().nodes()
