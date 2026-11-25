# Deployment

Everything here is for a **local demonstration cluster** (kind) and a CI deployment. It is not a production setup: one PostgreSQL instance without backup, public demonstration secrets, anonymous read-only Grafana.

## What runs where

| Component | Kubernetes object | Node pool | Evicted by the energy taint? |
| --- | --- | --- | --- |
| Shopper API and page (2 replicas) | Deployment `shopping-api` | standard | no (tolerates `energy-role`) |
| Carbon Monitor, Policy Engine, Placement Controller (1 replica) | Deployment `shopping-controller` + ServiceAccount | any | no (tolerates the taint it sets) |
| Forecast worker | Deployment `shopping-worker` | **either** | **yes**: no toleration, no node selector |
| Local model runtime (optional) | Deployment `ollama` | **either** | **yes** |
| PostgreSQL | StatefulSet `postgres` | standard | no |
| Prometheus, Grafana | Deployments | standard | no |

The controller decides the operating mode from the energy signals and puts the taint `energy-role=blocked:NoExecute` on the node pool that is **not** the target. Pods without a toleration on that pool are evicted by Kubernetes and started on the other pool. The pools are the node label `energy-pool=standard|eco`.

## Run it locally

Needs Docker, [kind](https://kind.sigs.k8s.io/) and kubectl.

```
scripts/demo-up.sh                 # image, two-pool kind cluster, everything deployed
scripts/demo-up.sh --with-ollama   # additionally a real local model runtime (downloads about 1.5 GB of model weights once)
scripts/smoke.sh                   # automated check, ends with SMOKE TEST PASSED
scripts/demo-scenario.sh           # the demonstration for the video
scripts/demo-down.sh
```

Open the shop and the operator console with `kubectl -n shopping port-forward svc/shopping-api 8080:80` (operator token `demo-ops-token`), Grafana with `port-forward svc/grafana 3000:3000`, Prometheus with `port-forward svc/prometheus 9090:9090`.

## Layout

```
Dockerfile                          application image (one image, role chosen by arguments)
deploy/k8s/base                     API, worker, controller, PostgreSQL, RBAC, configuration (no secrets)
deploy/k8s/monitoring               Prometheus (configuration, alert rules), Grafana (provisioned dashboard)
deploy/k8s/overlays/kind            demonstration values: controlled signal, short intervals, generated demo secrets
deploy/k8s/overlays/ollama          kind overlay + Ollama and the model settings
deploy/kind/kind-config.yaml        control plane + one standard and one eco worker
deploy/ollama/Dockerfile            Ollama with the models baked in
deploy/kafka, docker-compose.yml    optional Kafka event bus (not part of the Kubernetes demonstration)
scripts/                            demo-up, demo-down, smoke, demo-scenario, carbon_experiment
```

## Your own cluster

Create the secrets yourself and apply the base: `kubectl create namespace shopping`, `kubectl -n shopping create secret generic postgres --from-literal=password=...`, `kubectl -n shopping create secret generic shopping-ops --from-literal=token=...`, then `kubectl apply -k deploy/k8s/base`. Label two or more nodes with `energy-pool=standard` or `eco`. Set the image with `kustomize edit set image ghcr.io/anchelesr/aacc-smart-shopping=<your image>`.

## Status

Checked in the sandbox: the manifests build with kustomize and validate with kubeconform against the Kubernetes 1.31 schemas, the Prometheus files pass `promtool`, the image builds and starts, and the scripts pass `shellcheck`. **Not checked: a deployment on a real cluster.** See [docs/implementation.md](../docs/implementation.md).
