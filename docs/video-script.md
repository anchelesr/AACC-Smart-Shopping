# Video demonstration: script (target 4 min 45 s, limit 5 min)

The assignment asks for a video of at most five minutes that **proves** the claims about dynamic behaviour. Every claim below is tied to something visible on the screen; nothing is shown that was not run. Record only after `scripts/smoke.sh` has ended with `SMOKE TEST PASSED` on your machine.

## Before recording

1. `scripts/demo-up.sh --with-ollama` (the first run takes several minutes; do it before the recording). Without Ollama the assistant answers from the stand-in model; do not call that a language model in the video.
2. Open four windows: a terminal (large font), the shop at http://localhost:8080, Grafana at http://localhost:3000 (dashboard "Smart Shopping - energy-adaptive operation", refresh 10 s, last 15 minutes), and the GitHub Actions page of the repository with one finished run.
3. Port-forwards: `kubectl -n shopping port-forward svc/shopping-api 8080:80` and `svc/grafana 3000:3000` in two extra terminals.
4. Run `scripts/demo-scenario.sh --auto` once as a rehearsal; it prints how long each wait takes on your machine. Evictions can take 30 to 90 seconds. In the final recording you may cut the waiting, but keep the clock of the terminal visible and say "cut" on screen where you cut. Do not edit the output.
5. Reset with `scripts/demo-down.sh` and `scripts/demo-up.sh`, or just run the scenario again (it starts by clearing the simulated signal).

## Script

| Time | On screen | What to say (about) |
| --- | --- | --- |
| 0:00 to 0:25 | Title slide or the README figure, then the shop page | "Smart Shopping compares laptop prices, advises buy or wait, and explains the advice with an AI assistant. It adapts to the electricity grid: carbon intensity, price and renewable energy. All grid signals here are simulated; all energy numbers are estimates." |
| 0:25 to 0:55 | Terminal: `kubectl get nodes -L energy-pool` and `kubectl -n shopping get pods -o wide` | "This is the running system on Kubernetes: a standard node and an eco node, PostgreSQL, the API, a controller and a forecast worker. Only the worker and the local model have no toleration, so only they can be moved." |
| 0:55 to 1:20 | GitHub Actions: the finished run, jobs lint, test, manifests, image, deploy-kind; the package in GHCR | "Every commit goes through this pipeline: tests on two databases, manifest validation, an image pushed with the commit hash, and a deployment to a kind cluster with a smoke test that changes the energy signal and checks the node taints." |
| 1:20 to 1:50 | Grafana dashboard, point at: operating mode, placement target, where the worker runs, carbon intensity, overdue jobs 0, estimated emissions | "Observability: Prometheus scrapes every pod, ten alert rules, and this dashboard. Operating mode, placement target, the node of the worker pod, and estimated energy and emissions, labelled as estimates." |
| 1:50 to 2:35 | `scripts/demo-scenario.sh`, act 1 (AMBER): signal 350; the output shows the mode change, the taint on the standard node, the worker pod restarted on the eco node, and the assistant trace | "The grid gets dirtier. The Policy Engine moves to AMBER. The Placement Controller puts the taint energy-role NoExecute on the standard pool through the Kubernetes API. Kubernetes evicts the worker and starts it on the eco node. Same moment: the assistant now answers with the smaller model." |
| 2:35 to 3:10 | Act 2 (RED): signal 520; dashboard shows RED; assistant trace `route=TEMPLATE model=none`; job log shows deferred jobs and 0 overdue | "RED: the assistant stops calling a model and answers from a template. Forecast jobs wait, but the 24 hour deadline still wins: overdue jobs stay at zero." |
| 3:10 to 3:50 | Act 3 and 4: renewable window (GREEN on the eco pool, larger model), then signal normal: eco pool tainted, worker moves back | "Renewable energy: GREEN again, on the eco pool. When the signal returns to normal the worker moves back. The model changes with the mode: qwen2.5 1.5b in GREEN, 0.5b in AMBER, none in RED." |
| 3:50 to 4:30 | `docs/carbon-experiment.md` (scenario B table) and the dashboard estimates | "How much does this save? In a simulation with a coherent signal, the carbon intensity at job start was 9.5 percent lower, with a longest wait of 13 hours and no missed deadline. With our default simulator it was slightly worse, because its renewable window lies on the carbon peak. That is a defect of the simulated data, which we report. These are estimates from configured power values, not measurements." |
| 4:30 to 4:50 | Terminal: `demo-evidence.txt`, then the README | "Everything is in the repository: code, manifests, pipeline, the scripts that produced this run and its evidence file. Limits: simulated signals, estimated energy, one database instance, no load test." |

## Claim and proof

| Claim made in the video | Proof on screen | Where it comes from |
| --- | --- | --- |
| The system runs on Kubernetes with two node pools | `kubectl get nodes -L energy-pool`, `get pods -o wide` | `deploy/kind/kind-config.yaml`, `deploy/k8s` |
| A signal change moves the workload | Terminal lines "taint energy-role=blocked:NoExecute on the standard pool" and "worker was evicted and restarted on the eco pool" with node names and clock | `scripts/demo-scenario.sh`, `placement.py` |
| The deadline wins | Dashboard stat "Overdue forecast jobs" stays 0 in RED | `scheduler.py`, metric `shopping_forecast_jobs_overdue` |
| The model is exchanged by mode | `trace: route=SMALL model=local:qwen2.5:1.5b mode=GREEN`, then `...0.5b mode=AMBER`, then `route=TEMPLATE model=none mode=RED` | `llm/providers.py` (`ModelByMode`), `llm/gateway.py` |
| CI/CD exists and works | A green GitHub Actions run and an image tagged with the commit | `.github/workflows/ci-cd.yml` |
| Monitoring exists | Grafana dashboard with live data, Prometheus rules page | `deploy/k8s/monitoring` |
| Carbon effect | The table of `docs/carbon-experiment.md` and its caveats | `scripts/carbon_experiment.py` |

## What not to say

- Do not say the emissions or energy are measured. They are estimates from configured power values and an assumed job length.
- Do not say the grid signals are real. They are set by the script (`SHOPPING_FEED=controlled`).
- Do not say the saving is general. It is one simulated trace; with the default simulator the result was worse.
- If the stand-in model answered (no Ollama), do not say a language model answered.
- If something fails on camera, keep the take or say what failed; do not show an earlier successful take as the live one.
