#!/usr/bin/env bash
# Shared helpers of smoke.sh and demo-scenario.sh. Needs: kubectl, curl. No jq, no python.
NS="${NS:-shopping}"
API_PORT="${API_PORT:-18080}"
OPS_TOKEN="${OPS_TOKEN:-demo-ops-token}"
PF_PIDS=()

log()  { printf '\n\033[1m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*"; }
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "missing tool: $1"; }
cleanup() { for p in "${PF_PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done; }
trap cleanup EXIT

forward() {   # forward <service> <local-port> <service-port>
  kubectl -n "$NS" port-forward "svc/$1" "$2:$3" >/dev/null 2>&1 &
  PF_PIDS+=($!)
  for _ in $(seq 1 30); do curl -s -o /dev/null "http://127.0.0.1:$2/" && return 0; sleep 1; done
  fail "port-forward to $1 did not come up"
}

api()     { curl -s --max-time 10 "http://127.0.0.1:$API_PORT$1"; }
ops_get() { curl -s --max-time 10 -H "Authorization: Bearer $OPS_TOKEN" "http://127.0.0.1:$API_PORT$1"; }
ops_put() { curl -s --max-time 10 -X PUT -H "Authorization: Bearer $OPS_TOKEN" -H 'Content-Type: application/json' -d "$2" "http://127.0.0.1:$API_PORT$1"; }
ops_del() { curl -s --max-time 10 -X DELETE -H "Authorization: Bearer $OPS_TOKEN" "http://127.0.0.1:$API_PORT$1"; }

mode()         { api /status | sed -n 's/.*"mode": *"\([A-Z]*\)".*/\1/p'; }
target_pool()  { ops_get /ops/placement | sed -n 's/.*"target": *"\([a-z]*\)".*/\1/p'; }
worker_node()  { kubectl -n "$NS" get pod -l shopping/role=worker --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null; }
pool_of()      { kubectl get node "$1" -o jsonpath='{.metadata.labels.energy-pool}' 2>/dev/null; }
taint_of()     { kubectl get node "$1" -o jsonpath='{range .spec.taints[*]}{.key}={.value}:{.effect}{" "}{end}' 2>/dev/null; }
node_of_pool() { kubectl get nodes -l "energy-pool=$1" -o jsonpath='{.items[0].metadata.name}'; }

wait_for() {   # wait_for "<description>" <timeout-seconds> <command...>   (the command must succeed)
  local what="$1" limit="$2"; shift 2
  local end=$((SECONDS + limit))
  while [ $SECONDS -lt $end ]; do
    if "$@" >/dev/null 2>&1; then ok "$what"; return 0; fi
    sleep 2
  done
  fail "timed out after ${limit}s: $what"
}

is_mode()        { [ "$(mode)" = "$1" ]; }
is_target()      { [ "$(target_pool)" = "$1" ]; }
worker_on_pool() { local n; n="$(worker_node)"; [ -n "$n" ] && [ "$(pool_of "$n")" = "$1" ]; }
pool_blocked()   { taint_of "$(node_of_pool "$1")" | grep -q 'energy-role=blocked:NoExecute'; }
pool_open()      { ! pool_blocked "$1"; }

show_cluster() {
  echo "  nodes (pool, taints):"
  for n in $(kubectl get nodes -l energy-pool -o jsonpath='{.items[*].metadata.name}'); do
    printf '    %-22s pool=%-9s taints=%s\n' "$n" "$(pool_of "$n")" "$(taint_of "$n")"
  done
  echo "  pods:"
  kubectl -n "$NS" get pods -o wide --no-headers 2>/dev/null | awk '{printf "    %-44s %-10s %s\n", $1, $3, $7}'
}
