"""Placement Controller: moves flexible workloads between the standard and the eco node pool with taints.

The pool that is NOT the target gets the taint `energy-role=blocked:NoExecute`; the target pool loses it. Pods
without a toleration (forecast and evaluation Jobs, the local model runtime) are evicted by Kubernetes and
rescheduled on the target pool. Safety rules: change only when the decision changed, keep a dwell time between
changes, require a ready node in both pools, never leave zero schedulable nodes, record every decision.

Cluster access sits behind `Cluster`: `FakeCluster` (tests, demonstration), `KubernetesApiCluster` (the REST API
with the pod's service account, used in the cluster; tested against a fake API server, not yet against a real
cluster) and `KubectlCluster` (kubectl CLI).
"""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

from events.consumer import Metrics

from .energy import iso

TAINT_KEY, TAINT_VALUE, TAINT_EFFECT = "energy-role", "blocked", "NoExecute"
POOL_LABEL = "energy-pool"


@dataclass
class Node:
    name: str
    pool: str
    ready: bool = True
    blocked: bool = False


class Cluster(Protocol):
    def nodes(self) -> list[Node]: ...
    def set_blocked(self, node: str, blocked: bool) -> None: ...


class FakeCluster:
    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = {n.name: n for n in nodes}
        self.calls: list[tuple[str, bool]] = []

    def nodes(self) -> list[Node]:
        return [Node(n.name, n.pool, n.ready, n.blocked) for n in self._nodes.values()]

    def set_blocked(self, node: str, blocked: bool) -> None:
        self._nodes[node].blocked = blocked
        self.calls.append((node, blocked))


class KubectlCluster:
    """Uses `kubectl get nodes -o json` and `kubectl taint nodes`. The controller's service account needs the
    verbs get, list and patch on nodes (deploy/k8s)."""

    def __init__(self, run: Callable[..., subprocess.CompletedProcess] = subprocess.run, kubectl: str = "kubectl") -> None:
        self.run, self.kubectl = run, kubectl

    def nodes(self) -> list[Node]:
        proc = self.run([self.kubectl, "get", "nodes", "-o", "json"], capture_output=True, text=True, timeout=15, check=True)
        out = []
        for item in json.loads(proc.stdout)["items"]:
            node = _node_from_item(item)
            if node:
                out.append(node)
        return out

    def set_blocked(self, node: str, blocked: bool) -> None:
        cmd = ([self.kubectl, "taint", "nodes", node, f"{TAINT_KEY}={TAINT_VALUE}:{TAINT_EFFECT}", "--overwrite"] if blocked
               else [self.kubectl, "taint", "nodes", node, f"{TAINT_KEY}:{TAINT_EFFECT}-"])
        self.run(cmd, capture_output=True, text=True, timeout=15, check=True)


SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"


def _node_from_item(item: dict) -> Optional[Node]:
    pool = item["metadata"].get("labels", {}).get(POOL_LABEL)
    if pool not in ("standard", "eco"):
        return None
    ready = any(c["type"] == "Ready" and c["status"] == "True" for c in item.get("status", {}).get("conditions", []))
    blocked = any(t.get("key") == TAINT_KEY and t.get("effect") == TAINT_EFFECT for t in item.get("spec", {}).get("taints") or [])
    return Node(item["metadata"]["name"], pool, ready, blocked)


class KubernetesApiCluster:
    """Talks to the Kubernetes REST API directly (no kubectl in the image). Inside a pod the address, the token and
    the CA come from the service account; the controller needs the verbs get, list and patch on `nodes`.

    `set_blocked` reads the node, changes only the `energy-role` taint in the list and sends a JSON merge patch
    with the node's `resourceVersion`: a concurrent change makes the API answer 409 and nothing is overwritten.
    `transport(method, path, body, content_type) -> (status, json)` can be injected for tests."""

    def __init__(self, transport: Optional[Callable[..., tuple[int, dict]]] = None, base_url: Optional[str] = None,
                 token_file: str = f"{SA_DIR}/token", ca_file: str = f"{SA_DIR}/ca.crt", timeout: float = 15) -> None:
        host, port = os.environ.get("KUBERNETES_SERVICE_HOST"), os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        self.base_url = (base_url or (f"https://{host}:{port}" if host else "")).rstrip("/")
        self.token_file, self.ca_file, self.timeout = token_file, ca_file, timeout
        self.transport = transport or self._http

    def _http(self, method: str, path: str, body: Optional[dict] = None, content_type: str = "application/json") -> tuple[int, dict]:
        if not self.base_url:
            raise OSError("no Kubernetes API address (not running in a cluster)")
        headers = {"Accept": "application/json", "Content-Type": content_type}
        if os.path.exists(self.token_file):                       # re-read on every call: the token is rotated
            headers["Authorization"] = "Bearer " + open(self.token_file).read().strip()
        ctx = ssl.create_default_context(cafile=self.ca_file) if self.base_url.startswith("https") and os.path.exists(self.ca_file) else None
        req = urllib.request.Request(self.base_url + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read() or b"{}")
            except ValueError:
                return exc.code, {}

    def _call(self, method: str, path: str, body: Optional[dict] = None, content_type: str = "application/json") -> dict:
        status, data = self.transport(method, path, body, content_type)
        if status >= 400:
            raise OSError(f"Kubernetes API {method} {path} answered {status}: {data.get('message', '')}")
        return data

    def nodes(self) -> list[Node]:
        return [n for n in (_node_from_item(i) for i in self._call("GET", "/api/v1/nodes").get("items", [])) if n]

    def set_blocked(self, node: str, blocked: bool) -> None:
        item = self._call("GET", f"/api/v1/nodes/{node}")
        taints = [t for t in item.get("spec", {}).get("taints") or [] if t.get("key") != TAINT_KEY]
        if blocked:
            taints.append({"key": TAINT_KEY, "value": TAINT_VALUE, "effect": TAINT_EFFECT})
        patch = {"metadata": {"resourceVersion": item["metadata"].get("resourceVersion")}, "spec": {"taints": taints or None}}
        self._call("PATCH", f"/api/v1/nodes/{node}", patch, "application/merge-patch+json")


class PlacementController:
    def __init__(self, db, cluster: Cluster, policy_source, metrics: Optional[Metrics] = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.db, self.cluster, self.policy_source = db, cluster, policy_source
        self.metrics = metrics if metrics is not None else Metrics()
        self.clock = clock

    def reconcile(self) -> dict:
        now = self.clock()
        mode, target = self.db.execute("SELECT mode, placement_target FROM operating_mode_state WHERE id=1").fetchone()
        try:
            nodes = self.cluster.nodes()
        except Exception as exc:                                        # API unreachable: change nothing
            return self._record(now, mode, target, "skipped", f"cluster unreachable: {exc}")
        other = "standard" if target == "eco" else "eco"
        want = {n.name: (n.pool == other) for n in nodes}              # the non-target pool is blocked
        to_change = [n for n in nodes if n.blocked != want[n.name]]
        if not to_change:
            return self._record(now, mode, target, "unchanged", f"pool {target} is already the target")
        if not any(n.ready and n.pool == target for n in nodes):
            return self._record(now, mode, target, "skipped", f"no ready node in the {target} pool")
        if not any(n.ready and n.pool == other for n in nodes) and any(n.pool == other for n in nodes):
            return self._record(now, mode, target, "skipped", f"no ready node in the {other} pool (never leave one pool without a ready node)")
        dwell = timedelta(minutes=self.policy_source().dwell_minutes)
        last = self.db.execute("SELECT MAX(decided_at) FROM placement_decisions WHERE outcome='applied'").fetchone()[0]
        if last and now - datetime.fromisoformat(last) < dwell:
            return self._record(now, mode, target, "skipped", f"dwell time of {int(dwell.total_seconds() // 60)} minutes not over")
        done = []
        try:
            for n in to_change:
                self.cluster.set_blocked(n.name, want[n.name])
                done.append(n.name)
        except Exception as exc:
            return self._record(now, mode, target, "failed", f"changed {done}, then failed: {exc}")
        return self._record(now, mode, target, "applied", f"tainted {[n.name for n in to_change if want[n.name]]}, released {[n.name for n in to_change if not want[n.name]]}")

    def _record(self, now, mode, target, outcome, reason) -> dict:
        row = {"decided_at": iso(now), "mode": mode, "target_pool": target, "outcome": outcome, "reason": reason}
        last = self.db.execute("SELECT outcome, reason, target_pool FROM placement_decisions ORDER BY id DESC LIMIT 1").fetchone()
        last = tuple(last) if last else None
        if last != (outcome, reason, target):                            # an unchanged repeat is counted, not stored again
            with self.db:
                self.db.execute("INSERT INTO placement_decisions (decided_at, mode, target_pool, outcome, reason) VALUES (?, ?, ?, ?, ?)",
                                (row["decided_at"], mode, target, outcome, reason))
        self.metrics[f"placement_decisions_{outcome}"] += 1
        return row

    def decisions(self, limit: int = 20) -> list[dict]:
        return [dict(zip(("decided_at", "mode", "target_pool", "outcome", "reason"), r)) for r in self.db.execute(
            "SELECT decided_at, mode, target_pool, outcome, reason FROM placement_decisions ORDER BY id DESC LIMIT ?", (limit,))]
