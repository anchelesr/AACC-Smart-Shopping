"""The deployment files and the code must describe the same topics."""
import pathlib
import re

import yaml

from events.bus import TOPIC_CONFIG

ROOT = pathlib.Path(__file__).resolve().parents[1] / "deploy"


def layout_from_commands(text):
    found = {}
    for m in re.finditer(r"--topic (\S+)\s+--partitions (\d+).*?retention\.ms=(\d+)", text):
        found[m.group(1)] = {"partitions": int(m.group(2)), "retention_ms": int(m.group(3))}
    return found


def test_topics_job_matches_the_code():
    job = yaml.safe_load((ROOT / "kafka" / "topics-job.yaml").read_text())
    script = job["spec"]["template"]["spec"]["containers"][0]["args"][0]
    assert layout_from_commands(script) == TOPIC_CONFIG


def test_compose_matches_the_code():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    script = compose["services"]["topics"]["command"][0]
    assert layout_from_commands(script) == TOPIC_CONFIG


def test_broker_statefulset_is_safe_for_the_demo():
    docs = list(yaml.safe_load_all((ROOT / "kafka" / "kafka.yaml").read_text()))
    sts = next(d for d in docs if d["kind"] == "StatefulSet")
    pod = sts["spec"]["template"]["spec"]
    env = {e["name"]: e.get("value") for e in pod["containers"][0]["env"]}
    assert sts["spec"]["replicas"] == 1 and sts["spec"]["serviceName"] == "kafka"
    assert env["KAFKA_PROCESS_ROLES"] == "broker,controller"           # KRaft, no ZooKeeper
    assert env["KAFKA_AUTO_CREATE_TOPICS_ENABLE"] == "false"
    assert env["KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR"] == "1"        # one broker: a higher value would never become ready
    assert any(t["key"] == "energy-role" for t in pod["tolerations"])  # never evicted by the Placement Controller
    res = pod["containers"][0]["resources"]
    assert "requests" in res and "limits" in res


def test_postgres_manifest_and_compose_are_consistent_and_safe():
    docs = list(yaml.safe_load_all((ROOT / "k8s" / "base" / "postgres.yaml").read_text()))
    sts = next(d for d in docs if d["kind"] == "StatefulSet")
    pod = sts["spec"]["template"]["spec"]
    env = {e["name"]: e for e in pod["containers"][0]["env"]}
    assert sts["spec"]["replicas"] == 1 and sts["spec"]["serviceName"] == "postgres"
    assert "secretKeyRef" in env["POSTGRES_PASSWORD"]["valueFrom"] and "value" not in env["POSTGRES_PASSWORD"]   # no password in the manifest
    assert any(t["key"] == "energy-role" for t in pod["tolerations"])                                          # never evicted by the Placement Controller
    assert pod["nodeSelector"] == {"energy-pool": "standard"}
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert compose["services"]["postgres"]["environment"]["POSTGRES_DB"] == env["POSTGRES_DB"]["value"] == "shopping"
