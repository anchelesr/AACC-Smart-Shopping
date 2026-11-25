"""The Kubernetes manifests, the monitoring files and the code must describe the same system.

These are static checks (no cluster). If the `kustomize` binary is on the PATH the overlays are also built.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

from shopping.policy import Policy

ROOT = pathlib.Path(__file__).resolve().parents[1]
K8S = ROOT / "deploy" / "k8s"
SRC = ROOT / "src"


def load(path):
    return list(yaml.safe_load_all(path.read_text()))


def deployment(name):
    for d in load(K8S / "base" / f"{name}.yaml"):
        if d["kind"] == "Deployment":
            return d


def pod(name):
    return deployment(name)["spec"]["template"]["spec"]


def tolerates_energy_taint(spec):
    return any(t.get("key") == "energy-role" and t.get("effect") == "NoExecute" for t in spec.get("tolerations", []))


def test_only_the_flexible_workload_can_be_evicted():
    """The point of the taint: the worker has no toleration and no node selector, everything that must stay up has one."""
    worker = pod("worker")
    assert not tolerates_energy_taint(worker) and "nodeSelector" not in worker and "affinity" not in worker
    assert tolerates_energy_taint(pod("api")) and pod("api")["nodeSelector"] == {"energy-pool": "standard"}
    assert tolerates_energy_taint(pod("controller"))
    sts = next(d for d in load(K8S / "base" / "postgres.yaml") if d["kind"] == "StatefulSet")
    assert tolerates_energy_taint(sts["spec"]["template"]["spec"])
    for f in ("prometheus.yaml", "grafana.yaml"):
        d = next(x for x in load(K8S / "monitoring" / f) if x["kind"] == "Deployment")
        assert tolerates_energy_taint(d["spec"]["template"]["spec"]), f
    ollama = next(x for x in load(K8S / "overlays" / "ollama" / "ollama.yaml") if x["kind"] == "Deployment")
    assert not tolerates_energy_taint(ollama["spec"]["template"]["spec"]) and "nodeSelector" not in ollama["spec"]["template"]["spec"]


def test_taint_in_the_code_matches_the_manifests():
    from shopping.placement import POOL_LABEL, TAINT_EFFECT, TAINT_KEY
    assert (TAINT_KEY, TAINT_EFFECT, POOL_LABEL) == ("energy-role", "NoExecute", "energy-pool")
    kind = yaml.safe_load((ROOT / "deploy" / "kind" / "kind-config.yaml").read_text())
    labels = [re.search(r'node-labels: "([^"]+)"', p).group(1) for n in kind["nodes"] if n["role"] == "worker" for p in n["kubeadmConfigPatches"]]
    assert sorted(labels) == ["energy-pool=eco", "energy-pool=standard"]


def test_controller_has_least_privilege_rbac_and_the_others_have_none():
    docs = load(K8S / "base" / "rbac.yaml")
    role = next(d for d in docs if d["kind"] == "ClusterRole")
    assert role["rules"] == [{"apiGroups": [""], "resources": ["nodes"], "verbs": ["get", "list", "patch"]}]
    binding = next(d for d in docs if d["kind"] == "ClusterRoleBinding")
    assert binding["subjects"] == [{"kind": "ServiceAccount", "name": "shopping-controller", "namespace": "shopping"}]
    assert pod("controller")["serviceAccountName"] == "shopping-controller"
    assert "serviceAccountName" not in pod("api") and "serviceAccountName" not in pod("worker")
    assert deployment("controller")["spec"]["replicas"] == 1 and deployment("controller")["spec"]["strategy"]["type"] == "Recreate"


def test_every_container_is_hardened_and_has_resources():
    for name in ("api", "worker", "controller"):
        spec = pod(name)
        assert spec["securityContext"]["runAsNonRoot"] is True
        for c in spec["containers"] + spec["initContainers"]:
            assert c["securityContext"]["allowPrivilegeEscalation"] is False and c["securityContext"]["readOnlyRootFilesystem"] is True
            assert c["securityContext"]["capabilities"] == {"drop": ["ALL"]}
            assert "requests" in c["resources"] and "limits" in c["resources"]


def test_container_arguments_and_probes_match_the_application():
    api_src = (SRC / "shopping" / "api.py").read_text()
    for name, role in (("api", "api"), ("worker", "worker"), ("controller", "controller")):
        c = pod(name)["containers"][0]
        assert c["args"][:2] == ["--role", role] and "--port" in c["args"]
        assert c["readinessProbe"]["httpGet"]["path"] == "/health/ready" and c["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert '"/health/ready"' in api_src and '"/health/live"' in api_src
    from shopping.__main__ import ROLES
    assert {"api", "worker", "controller"} <= set(ROLES)


def test_environment_variables_are_known_to_the_code_and_valid():
    code = "\n".join(p.read_text() for p in SRC.rglob("*.py"))
    cfg = yaml.safe_load((K8S / "base" / "config.yaml").read_text())["data"]
    for key in cfg:
        assert key in code, f"{key} is set by the manifests but never read by the code"
    assert cfg["SHOPPING_CLUSTER"] in ("fake", "incluster", "kubectl") and cfg["SHOPPING_FEED"] in ("simulated", "controlled")
    for name in ("api", "worker", "controller"):
        env = {e["name"] for e in pod(name)["containers"][0]["env"]}
        for key in env:
            assert key in code or key in ("POSTGRES_PASSWORD", "NODE_NAME", "POD_NAME"), key
    overlay = yaml.safe_load((K8S / "overlays" / "kind" / "kustomization.yaml").read_text())
    patch = next(p for p in overlay["patches"] if p["target"].get("name") == "shopping-config")["patch"]
    ops = {o["path"].rsplit("/", 1)[1]: o["value"] for o in yaml.safe_load(patch)}
    Policy(**json.loads(ops["SHOPPING_INITIAL_POLICY"])).validate()          # the demonstration policy is a valid policy
    assert ops["SHOPPING_FEED"] == "controlled"
    for key in ("SHOPPING_LOCAL_MODEL_URL", "SHOPPING_LOCAL_MODEL", "SHOPPING_LOCAL_MODEL_AMBER"):
        assert key in code


def test_secrets_are_referenced_not_written_in_the_base():
    text = "\n".join(p.read_text() for p in (K8S / "base").glob("*.yaml"))
    assert "kind: Secret" not in text and "demo-" not in text
    refs = set(re.findall(r"secretKeyRef: \{name: ([\w-]+), key: ([\w-]+)\}", text))
    assert refs == {("postgres", "password"), ("shopping-ops", "token")}
    overlay = yaml.safe_load((K8S / "overlays" / "kind" / "kustomization.yaml").read_text())
    generated = {g["name"] for g in overlay["secretGenerator"]}
    assert {"postgres", "shopping-ops", "grafana-admin"} <= generated


def test_prometheus_scrape_matches_pod_labels_and_ports():
    cfg = yaml.safe_load((K8S / "monitoring" / "prometheus.yml").read_text())
    job = cfg["scrape_configs"][0]
    assert job["metrics_path"] == "/metrics" and job["authorization"]["type"] == "Bearer"
    keep = {r["source_labels"][0]: r["regex"] for r in job["relabel_configs"] if r.get("action") == "keep"}
    assert keep["__meta_kubernetes_pod_label_app_kubernetes_io_part_of"] == "shopping" and keep["__meta_kubernetes_pod_container_port_name"] == "http"
    for name in ("api", "worker", "controller"):
        d = deployment(name)
        assert d["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/part-of"] == "shopping"
        assert pod(name)["containers"][0]["ports"][0]["name"] == "http"
        assert d["spec"]["template"]["metadata"]["labels"]["shopping/role"] == name
    mount = next(d for d in load(K8S / "monitoring" / "prometheus.yaml") if d["kind"] == "Deployment")["spec"]["template"]["spec"]
    assert mount["volumes"][1]["secret"]["secretName"] == "shopping-ops"


def _exposed_metric_names():
    """Every metric family the running application really exposes (after one step on seeded data)."""
    from datetime import datetime, timezone
    from shopping.seed import synthetic_csv
    from shopping.service import Application
    app = Application("sqlite://:memory:", ops_token="x")
    app.imports.run(synthetic_csv(datetime.now(timezone.utc)), "csv", "t")
    app.step()
    app.gateway.ask("Should I buy?", app.service.assistant_payload("lap-001"), "s")
    app.http.observe("/products", 200, 0.01)
    return {m.group(1) for m in re.finditer(r"^# TYPE (\w+) ", app.prometheus(), re.M)}


def test_alert_rules_and_dashboard_only_use_metrics_that_exist():
    exposed = _exposed_metric_names()
    used = set()
    for text in ((K8S / "monitoring" / "rules.yml").read_text(), (K8S / "monitoring" / "dashboards" / "shopping.json").read_text()):
        used |= set(re.findall(r"\bshopping_[a-z0-9_]+", text))
    missing = {re.sub(r"_(bucket|count|sum)$", "", u) for u in used} - exposed
    assert not missing, f"used in rules or dashboard but not exposed: {sorted(missing)}"
    dash = json.loads((K8S / "monitoring" / "dashboards" / "shopping.json").read_text())
    assert dash["uid"] == "shopping-energy" and len(dash["panels"]) >= 12
    assert all(t["datasource"]["uid"] == "prometheus" for p in dash["panels"] for t in p["targets"])
    rules = yaml.safe_load((K8S / "monitoring" / "rules.yml").read_text())
    for g in rules["groups"]:
        for r in g["rules"]:
            assert r["alert"] and r["expr"] and r["labels"]["severity"] and r["annotations"]["summary"]


def test_image_arguments_and_names_are_consistent():
    docker = (ROOT / "Dockerfile").read_text()
    assert "USER 10001" in docker and "ENTRYPOINT" in docker and "ARG BASE_IMAGE" in docker
    base = yaml.safe_load((K8S / "base" / "kustomization.yaml").read_text())
    overlay = yaml.safe_load((K8S / "overlays" / "kind" / "kustomization.yaml").read_text())
    assert base["images"][0]["name"] == overlay["images"][0]["name"] == "ghcr.io/anchelesr/aacc-smart-shopping"
    runtime = [l for l in (ROOT / "requirements.txt").read_text().splitlines() if l and not l.startswith("pytest")]
    assert runtime and "pytest" not in "\n".join(runtime)


@pytest.mark.skipif(shutil.which("kustomize") is None, reason="kustomize is not installed")
@pytest.mark.parametrize("overlay", ["base", "overlays/kind", "overlays/ollama"])
def test_overlays_build_with_kustomize(overlay):
    out = subprocess.run(["kustomize", "build", str(K8S / overlay)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    kinds = [d["kind"] for d in yaml.safe_load_all(out.stdout) if d]
    assert kinds.count("Deployment") >= 3 and "ClusterRoleBinding" in kinds
