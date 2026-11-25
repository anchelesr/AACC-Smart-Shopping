#!/usr/bin/env bash
# Builds the images, creates a local kind cluster with two node pools and deploys the whole system.
# Usage: scripts/demo-up.sh [--with-ollama]     (needs docker, kind, kubectl; about 5-10 minutes the first time)
set -euo pipefail
cd "$(dirname "$0")/.."
OLLAMA=0; [ "${1:-}" = "--with-ollama" ] && OLLAMA=1
for t in docker kind kubectl; do command -v "$t" >/dev/null || { echo "missing tool: $t"; exit 1; }; done

echo "== building the application image"
docker build -t shopping:dev .
if [ "$OLLAMA" = 1 ]; then
  echo "== building the Ollama image with the models (downloads the weights once)"
  docker build -t shopping-ollama:dev deploy/ollama
fi

echo "== creating the kind cluster (control plane + one standard and one eco worker)"
kind get clusters | grep -qx shopping || kind create cluster --config deploy/kind/kind-config.yaml
kubectl config use-context kind-shopping >/dev/null

echo "== loading the images into the cluster"
kind load docker-image shopping:dev --name shopping
[ "$OLLAMA" = 1 ] && kind load docker-image shopping-ollama:dev --name shopping

echo "== deploying"
if [ "$OLLAMA" = 1 ]; then kubectl apply -k deploy/k8s/overlays/ollama; else kubectl apply -k deploy/k8s/overlays/kind; fi
kubectl -n shopping rollout status statefulset/postgres --timeout=300s
for d in shopping-api shopping-worker shopping-controller prometheus grafana; do kubectl -n shopping rollout status "deploy/$d" --timeout=300s; done
[ "$OLLAMA" = 1 ] && kubectl -n shopping rollout status deploy/ollama --timeout=600s

cat <<'MSG'

The system is running.
  Shop and operator console:  kubectl -n shopping port-forward svc/shopping-api 8080:80      -> http://localhost:8080   (operator token: demo-ops-token)
  Grafana dashboard:          kubectl -n shopping port-forward svc/grafana 3000:3000          -> http://localhost:3000
  Prometheus:                 kubectl -n shopping port-forward svc/prometheus 9090:9090       -> http://localhost:9090
  Verify:                     scripts/smoke.sh
  Demonstration:              scripts/demo-scenario.sh
MSG
