#!/usr/bin/env bash
# Smoke test of the deployed system, used by CI (kind) and by hand. It proves, with real Kubernetes objects:
#   the system is up, the API answers, metrics exist, and an energy signal change moves the flexible workload.
# Usage: scripts/smoke.sh        (kubectl must point at the cluster; the kind overlay must be applied)
set -uo pipefail
cd "$(dirname "$0")" || exit 1; . ./demo-lib.sh
need kubectl; need curl

log "1/5 all deployments are rolled out"
for d in $(kubectl -n "$NS" get deploy -o jsonpath='{.items[*].metadata.name}'); do
  kubectl -n "$NS" rollout status "deploy/$d" --timeout=300s >/dev/null 2>&1 && ok "$d" || { kubectl -n "$NS" get pods -o wide; fail "$d did not become ready"; }
done
kubectl -n "$NS" rollout status statefulset/postgres --timeout=300s >/dev/null 2>&1 && ok "postgres" || fail "postgres did not become ready"

log "2/5 shopper API"
forward shopping-api "$API_PORT" 80
wait_for "GET /health/ready" 60 sh -c "curl -sf http://127.0.0.1:$API_PORT/health/ready"
wait_for "6 products are listed (demo data loaded)" 90 sh -c "curl -sf http://127.0.0.1:$API_PORT/products | grep -o '\"id\"' | wc -l | grep -qx 6"
api /products/lap-001/insights | grep -q '"action"' && ok "insights with a recommendation" || fail "no insights"

log "3/5 metrics are protected and exposed"
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$API_PORT/metrics")" = "403" ] && ok "/metrics refuses requests without the operator token" || fail "/metrics is open"
ops_get /metrics | grep -q '^shopping_operating_mode{mode="GREEN"}' && ok "shopping_operating_mode present" || fail "metrics missing"

log "4/5 the energy signal moves the flexible workload (real taints, real eviction)"
ops_del /ops/simulation >/dev/null
wait_for "mode GREEN and target pool standard at the start" 90 is_target standard
wait_for "worker runs on the standard pool" 120 worker_on_pool standard
echo "  signal -> 520 gCO2e/kWh, 0.35 EUR/kWh (simulated)"
ops_put /ops/simulation '{"intensity": 520, "price": 0.35}' >/dev/null
wait_for "mode RED" 60 is_mode RED
wait_for "target pool eco" 60 is_target eco
wait_for "standard pool carries the energy-role taint" 60 pool_blocked standard
wait_for "worker was evicted and runs on the eco pool" 180 worker_on_pool eco
show_cluster
echo "  signal back to normal"
ops_put /ops/simulation '{"intensity": 200, "price": 0.10}' >/dev/null
wait_for "mode GREEN" 120 is_mode GREEN
wait_for "eco pool carries the taint again" 90 pool_blocked eco
wait_for "worker moved back to the standard pool" 180 worker_on_pool standard
ops_del /ops/simulation >/dev/null

log "5/5 Prometheus scrapes the system"
if kubectl -n "$NS" get svc prometheus >/dev/null 2>&1; then
  forward prometheus 19090 9090
  wait_for "Prometheus has the metric shopping_operating_mode" 90 sh -c "curl -s 'http://127.0.0.1:19090/api/v1/query?query=shopping_operating_mode' | grep -q '\"result\":\[{'"
else
  echo "  (monitoring not deployed, skipped)"
fi
log "SMOKE TEST PASSED"
