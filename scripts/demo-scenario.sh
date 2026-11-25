#!/usr/bin/env bash
# The scripted demonstration for the video: the energy signal changes, the system adapts, and every step prints proof.
# Usage: scripts/demo-scenario.sh [--auto]      (without --auto it waits for Enter before each act, so the narration can keep pace)
# Output is also written to demo-evidence.txt.
set -uo pipefail
cd "$(dirname "$0")" || exit 1; . ./demo-lib.sh
need kubectl; need curl
AUTO=0; [ "${1:-}" = "--auto" ] && AUTO=1
exec > >(tee -a "$(pwd)/../demo-evidence.txt") 2>&1
act() { log "$*"; [ "$AUTO" = 1 ] || read -r -p "  (Enter to run) " _ </dev/tty; }
ask() {   # ask "<question>" : prints which model/route answered and in which mode
  curl -s --max-time 120 -X POST "http://127.0.0.1:$API_PORT/assistant/ask" -H 'Content-Type: application/json' \
    -d "{\"productId\": \"lap-001\", \"question\": \"$1\", \"sessionId\": \"demo-$RANDOM\"}"
}
last_trace() { ops_get /ops/traces | sed 's/}.*//' | sed -e 's/"model": null/"model": "none"/' | sed -n 's/.*"route": *"\([A-Z]*\)".*"model": *"\([^"]*\)".*"mode": *"\([A-Z]*\)".*/route=\1 model=\2 mode=\3/p'; }

forward shopping-api "$API_PORT" 80
ops_del /ops/simulation >/dev/null

act "ACT 0 - starting point: normal signal, GREEN mode, standard pool is the target"
ops_put /ops/simulation '{"intensity": 200, "price": 0.10}' >/dev/null
wait_for "mode GREEN, target standard" 90 is_target standard
wait_for "worker on the standard pool" 120 worker_on_pool standard
show_cluster
echo "  assistant (GREEN):"; ask "Should I buy this laptop now?" | head -c 300; echo; echo "  trace: $(last_trace)"

act "ACT 1 - the grid gets dirtier: 350 gCO2e/kWh (AMBER): a smaller model answers and the flexible workload moves to the eco pool"
ops_put /ops/simulation '{"intensity": 350, "price": 0.12}' >/dev/null
wait_for "mode AMBER" 60 is_mode AMBER
wait_for "taint energy-role=blocked:NoExecute on the standard pool" 60 pool_blocked standard
wait_for "worker was evicted and restarted on the eco pool" 180 worker_on_pool eco
show_cluster
echo "  assistant (AMBER):"; ask "Is this a good price?" | head -c 300; echo; echo "  trace: $(last_trace)"

act "ACT 2 - the grid becomes dirty and expensive: 520 gCO2e/kWh, 0.35 EUR/kWh (RED): the assistant stops calling a model, new work waits"
ops_put /ops/simulation '{"intensity": 520, "price": 0.35}' >/dev/null
wait_for "mode RED" 60 is_mode RED
wait_for "worker stays on the eco pool" 60 worker_on_pool eco
show_cluster
echo "  assistant (RED): answers from a template, no model is called"; ask "Should I buy this laptop now?" | head -c 300; echo; echo "  trace: $(last_trace)"
echo "  job log (new price data is deferred, the 24 h deadline still wins):"
NOW="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
curl -s -X POST -H "Authorization: Bearer $OPS_TOKEN" --data-binary $'laptop_id,brand,model,retailer,observed_at,price,currency\n'"lap-001,Acme,AirBook 14,shop-a,$NOW,849.00,EUR" "http://127.0.0.1:$API_PORT/ops/imports?kind=daily&source=demo" | head -c 160; echo
sleep 12; ops_get /ops/jobs | head -c 600; echo

act "ACT 3 - renewable energy becomes available: GREEN again, but on the eco pool"
ops_put /ops/simulation '{"intensity": 80, "price": 0.08, "renewable": true}' >/dev/null
wait_for "mode GREEN" 90 is_mode GREEN
wait_for "target pool eco (renewable window)" 60 is_target eco
show_cluster
echo "  assistant (GREEN, eco pool): $(ask 'Is this a good price?' | head -c 200)"; echo; echo "  trace: $(last_trace)"

act "ACT 4 - the signal returns to normal: the worker moves back"
ops_put /ops/simulation '{"intensity": 200, "price": 0.10}' >/dev/null
wait_for "target pool standard" 90 is_target standard
wait_for "eco pool is blocked again" 90 pool_blocked eco
wait_for "worker back on the standard pool" 180 worker_on_pool standard
show_cluster

act "ACT 5 - the evidence: decisions, audit trail and Prometheus"
echo "  placement decisions:"; ops_get /ops/placement | head -c 900; echo
echo "  operator audit trail:"; ops_get /ops/audit | head -c 700; echo
echo "  key metrics:"; ops_get /metrics | grep -E '^shopping_(operating_mode\{|placement_target\{|forecast_jobs_overdue|job_estimated_(energy_kwh|emissions_gco2e)_total|assistant_by_model_total)' | sed 's/^/    /'
ops_del /ops/simulation >/dev/null
log "DEMONSTRATION FINISHED (evidence in demo-evidence.txt)"
