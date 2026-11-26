# TODO — Smart Shopping, final project

*Created 25 November 2026 from the state of the repository (revision 9). Deadline: **4 December 2026, 23:59** (Teams assignment "Final Project submission", one member submits). Status words: DONE (finished and checked), VERIFY (written, not yet checked in reality), IN PROGRESS, TODO, BLOCKED. Effort: S under 1 h, M 1–4 h, L over 4 h.*

## 1. Project Overview

Smart Shopping advises whether to buy or wait for a laptop (price history, present offers, seven-day forecast, rule-based advice, AI explanation) and adapts its own operation to simulated electricity signals (carbon intensity, price, renewable flag): it chooses an operating mode, defers work, changes the assistant's model and moves flexible workloads between a standard and an eco node pool. Expected final output: a running, deployable system on Kubernetes with CI/CD, monitoring, carbon metrics, demonstrated dynamic behaviour, a video of at most 5 minutes, and a file with the GitHub link; plus the course documents (specification, use cases, UML, ADRs, AI usage log).

## 2. Current Project Status

- **Code and tests are in good shape:** 204 tests pass on SQLite and 279 on PostgreSQL 16 (3 Kafka tests skipped).
- **Everything that needs a cluster, a registry or GitHub has never run:** deployment, eviction of the worker pod after a taint, RBAC, node labels, Prometheus scrape, Grafana dashboard, Ollama image and a real model, all four GitHub workflows. Only static checks exist (`kustomize`, `kubeconform`, `promtool`, `actionlint`, `yamllint`, `shellcheck`) plus a fake Kubernetes API for the controller.
- **The video is not recorded**, the work is not pushed, and nothing has been submitted.
- **Carbon claim is weak:** on the default simulator the adaptive scheduler is *worse* than immediate execution (renewable window on the carbon peak); better only on a coherent trace. All energy values are estimates.
- **Authors' own items are open:** reflections in the AI usage log, the three-version comparison table, the unnamed NASA standard, review of the tool's unconfirmed decisions.
- **Source conflicts:** see section 11 (design documents still describe CronJobs, Jobs, GitOps pull and Kafka in the cluster; the implementation differs). The official assignment (Teams screenshots) wins; the lecture PDFs in the project were not re-read for this plan.

## 3. Requirements Coverage

Source of requirements R1–R7: the Teams assignment "Final Project submission". C1–C6: the earlier course deliverables as recorded in `docs/submission-note.md`.

| ID | Requirement | Status | Evidence | Related Task |
|---|---|---|---|---|
| R1 | File with GitHub repository link | IN PROGRESS | `SUBMISSION.txt` has the URL; the revision is not pushed | T001, T006 |
| R2 | Running system (deployable and operable) | VERIFY | Image built and started on a local base; manifests build and validate; tests on two databases; never deployed on a cluster | T003, T004, T017 |
| R3 | CI/CD pipeline | VERIFY | `.github/workflows/ci-cd.yml`; `actionlint` clean; never ran on GitHub | T001, T002 |
| R4 | Observability and monitoring | VERIFY | `/metrics` (50 families), `deploy/k8s/monitoring` (10 rules, 16-panel dashboard); `promtool` and parser OK; never scraped live | T011 |
| R5 | Carbon metrics | VERIFY | Estimated energy/emissions in metrics; `docs/carbon-experiment.md` (reproducible); no measurement; weak result on default simulator | T012, T018 |
| R6a | Dynamic redeployment on Kubernetes | VERIFY | `KubernetesApiCluster` tested against a fake API; manifests: only worker and Ollama evictable; eviction never observed | T003, T004 |
| R6b | Dynamic model exchange | VERIFY | `ModelByMode` and router tested with injected transport; no live Ollama | T010 |
| R7 | Video ≤ 5 min proving the claims | TODO | `docs/video-script.md` written; no recording | T005 |
| C1 | Project specification | DONE | `docs/project-specification.md` | — |
| C2 | Significant use cases | DONE | `docs/significant-use-cases.md` | — |
| C3 | UML use-case, sequence, component models (PlantUML) | DONE (see T024) | 9 diagrams `docs/diagrams`; compile check of rev 7 | T024, T028 |
| C4 | Architecture decisions | DONE | ADR-001 to ADR-017; ADR-011, 013, 014, 017 still "proposed" | T013 |
| C5 | Documented AI use with prompt, model, reflection | IN PROGRESS | `docs/ai-usage-log.md`; reflections "Authors to complete" | T014 |
| C6 | Three-version comparison (no AI / AI / improved prompt) | TODO | Table empty | T015 |

## 4. Completed Tasks

- [x] **D01** Shopper path: REST API, frontend, advice rules, compare, watch and alerts (`tests/test_api.py`, `test_advice.py`, `test_watch_catalog.py`; frontend driven once in Chromium, revision 8).
- [x] **D02** Price import with validation and idempotence (`tests/test_importer.py`).
- [x] **D03** Carbon Monitor, Policy Engine with hysteresis, override, policy versions (`tests/test_policy_energy.py`).
- [x] **D04** Job Scheduler with leases, deadline that always wins, estimated kWh/gCO2e (`tests/test_forecast_scheduler.py`).
- [x] **D05** Forecast worker, evaluator, model registry with fallback and pin (same file).
- [x] **D06** LLM Gateway: guardrails, router, cache, memory, trace, review queue (`tests/test_llm_gateway.py`).
- [x] **D07** PostgreSQL and SQLite back ends; whole suite on both (279 passed on PostgreSQL 16).
- [x] **D08** Process roles `api|worker|controller|all`, three real processes on one PostgreSQL (`tests/test_roles_simulation.py`).
- [x] **D09** `KubernetesApiCluster` over real HTTP against `tests/fake_k8s.py` (test double, not Kubernetes).
- [x] **D10** Prometheus exposition parses with the official parser; rules and dashboard use only existing metrics (`tests/test_api.py`, `tests/test_k8s_manifests.py`).
- [x] **D11** Static validation: `kustomize` 5.4.3 + `kubeconform` 0.6.7 (K8s 1.31) on three overlays; `promtool`; `actionlint`; `yamllint`; `shellcheck`.
- [x] **D12** Carbon experiment is reproducible (run twice, diff empty; `tests/test_carbon_experiment.py`).
- [x] **D13** Container image builds and starts, non-root, SIGTERM exit 0 — **on a locally assembled Python 3.13 base only** (re-check on the real base in T026).

## 5. Critical Tasks — P0

### T001 — Push revision 9 to the GitHub repository
- [ ] **T001 completed**
- **Priority:** P0 · **Status:** TODO · **Effort:** S
- **Reason:** nothing downstream (CI, GHCR, submission link) works until the code is on GitHub.
- **Requirement:** R1, R3 · **Files:** whole repository, `SUBMISSION.txt`
- **Depends on:** none
- **Steps:** unzip `AACC_Smart_Shopping.zip` over the clone; `git status` and read the diff; commit (message prepared in the conversation); push to `main`.
- **Acceptance:** [ ] commit visible on https://github.com/anchelesr/AACC-Smart-Shopping; [ ] `Dockerfile`, `.github/workflows/ci-cd.yml`, `deploy/k8s`, `scripts/` present on `main`.
- **Verification:** open the repository in a browser; run `git log -1`.

### T002 — First green run of `ci-cd.yml`
- [ ] **T002 completed**
- **Priority:** P0 · **Status:** VERIFY · **Effort:** M (L if fixes are needed)
- **Reason:** CI/CD is a required deliverable and the workflow has never run.
- **Requirement:** R3 · **Files:** `.github/workflows/ci-cd.yml`, `app.yml`, `scripts/smoke.sh`
- **Depends on:** T001
- **Steps:** [ ] open Actions, watch jobs `lint`, `test`, `manifests`, `carbon-experiment`, `image`, `deploy-kind`; [ ] for each failure copy the log and fix (likely: GHCR permission on first push, action versions, runner timing, kind pulls); [ ] re-run until green.
- **Acceptance:** [ ] all six jobs green on `main`; [ ] image `ghcr.io/anchelesr/aacc-smart-shopping:<sha>` exists in Packages; [ ] artifact `smoke-output` shows `SMOKE TEST PASSED`.
- **Verification:** screenshot of the green run and the package page (also used in the video).

### T003 — Deploy to a real kind cluster and pass `scripts/smoke.sh`
- [ ] **T003 completed**
- **Priority:** P0 · **Status:** VERIFY · **Effort:** L
- **Reason:** "running system" and "dynamic redeployment" have no proof until a cluster runs them.
- **Requirement:** R2, R6a · **Files:** `scripts/demo-up.sh`, `smoke.sh`, `deploy/k8s/**`, `deploy/kind/kind-config.yaml`
- **Depends on:** a machine with Docker, kind, kubectl
- **Steps:** [ ] `scripts/demo-up.sh`; [ ] `scripts/smoke.sh`; [ ] on failure send the output (pods, events, logs) and fix; [ ] repeat from a deleted cluster once to prove it is reproducible.
- **Acceptance:** [ ] all deployments ready; [ ] smoke test ends with `SMOKE TEST PASSED`; [ ] the same on a second run from scratch.
- **Verification:** saved terminal output.

### T004 — Observe and record the eviction (taint → worker moves)
- [ ] **T004 completed**
- **Priority:** P0 · **Status:** VERIFY · **Effort:** M
- **Reason:** the central dynamic-behaviour claim.
- **Requirement:** R6a · **Files:** `src/shopping/placement.py`, `deploy/k8s/base/worker.yaml`, `rbac.yaml`
- **Depends on:** T003
- **Steps:** [ ] run `scripts/demo-scenario.sh --auto`; [ ] check `kubectl get nodes` taints, worker pod node before/after, controller logs, `GET /ops/placement`; [ ] check that system pods (CoreDNS, local-path provisioner) evicted by the taint do not break the demo; [ ] check RBAC (no `forbidden` in controller logs).
- **Acceptance:** [ ] worker pod changes pool on every pool change in the scenario; [ ] no `failed` placement decision; [ ] `shopping_forecast_jobs_overdue` stays 0; [ ] `demo-evidence.txt` saved.
- **Verification:** `demo-evidence.txt`, `kubectl get pods -o wide` captures.

### T005 — Record the video (≤ 5 min)
- [ ] **T005 completed**
- **Priority:** P0 · **Status:** TODO · **Effort:** M
- **Requirement:** R7 · **Files:** `docs/video-script.md`
- **Depends on:** T003, T004, T011 (dashboard), ideally T010
- **Steps:** rehearse once; record following the script; cut waiting but keep the clock visible; check length.
- **Acceptance:** [ ] length ≤ 5:00; [ ] every row of the "Claim and proof" table appears on screen; [ ] no claim of measured energy, real signals or a general saving; [ ] if the stand-in model answered it is not called a language model.
- **Verification:** both authors watch it against the "What not to say" list.

### T006 — Submit in Teams before 4 Dec 23:59
- [ ] **T006 completed**
- **Priority:** P0 · **Status:** TODO · **Effort:** S
- **Requirement:** R1, R7 · **Depends on:** T001, T005
- **Steps:** one member uploads the video and the file with the link (`SUBMISSION.txt` or the repository URL); submit early, multiple submissions are allowed.
- **Acceptance:** [ ] submission confirmation in Teams; [ ] link opens without login from another account.
- **Verification:** screenshot of the confirmation.

## 6. Mandatory Tasks — P1

### T010 — Build the Ollama image and verify real model exchange
- [ ] **T010 completed**
- **Status:** VERIFY · **Effort:** M · **Requirement:** R6b · **Files:** `deploy/ollama/Dockerfile`, `deploy/k8s/overlays/ollama`, `src/shopping/llm/providers.py`
- **Depends on:** T003
- **Steps:** [ ] `scripts/demo-up.sh --with-ollama` (needs internet and ~1.5 GB); [ ] confirm the base tag `ollama/ollama:0.9.6` exists, else change `OLLAMA_IMAGE`; [ ] ask the assistant in GREEN, AMBER, RED; [ ] read `/ops/traces`.
- **Acceptance:** [ ] trace shows `local:qwen2.5:1.5b` in GREEN and `local:qwen2.5:0.5b` in AMBER, `TEMPLATE` with no model in RED; [ ] answers pass the output guardrail or are flagged honestly; [ ] Ollama pod moves with the worker.
- **Verification:** trace output; if small models fail the guardrail often, record the rate (do not hide it).

### T011 — Verify Prometheus and Grafana on the live cluster
- [ ] **T011 completed**
- **Status:** VERIFY · **Effort:** M · **Requirement:** R4 · **Files:** `deploy/k8s/monitoring/**`
- **Depends on:** T003
- **Steps:** [ ] port-forward Prometheus: targets page shows api, worker, controller `UP`; [ ] rules page loads 10 rules; [ ] Grafana opens the dashboard without login; [ ] run the scenario and check every panel changes (mode, placement, worker node table, estimates).
- **Acceptance:** [ ] no panel is "No data" during the scenario (or the panel is fixed/removed); [ ] worker node table updates after eviction.
- **Verification:** screenshots; fix queries in `dashboards/shopping.json` and keep `tests/test_k8s_manifests.py` green.

### T012 — Decide and apply the simulator fix for the renewable window
- [ ] **T012 completed**
- **Status:** BLOCKED (needs authors' decision) · **Effort:** S · **Requirement:** R5 · **Files:** `src/shopping/energy.py` (`SimulatedFeed`), `scripts/carbon_experiment.py`, `tests/test_policy_energy.py`
- **Depends on:** authors' decision between (a) moving the default window to the intensity trough, (b) coupling intensity to the renewable flag, (c) leaving it and keeping both scenarios.
- **Steps:** apply the decision minimally; re-run `scripts/carbon_experiment.py`; update `docs/carbon-experiment.md`, `implementation.md` row 18 and the video script's numbers.
- **Acceptance:** [ ] full suite green; [ ] CI step `carbon-experiment` green (diff against committed file); [ ] docs and video quote the same numbers.
- **Verification:** `pytest`, experiment re-run.

### T013 — Review the tool's unconfirmed decisions
- [ ] **T013 completed**
- **Status:** TODO · **Effort:** S · **Requirement:** C4/C5 · **Files:** `docs/implementation.md` rows 17–22, `docs/ai-usage-log.md` Entry 5
- **Steps:** [ ] read rows 4–5, 9–11, 14–22; [ ] confirm or reject: Deployments instead of Jobs/CronJobs, Qwen model names, metrics derived from the database, controllable simulation, moved `postgres.yaml`, two-trace experiment; [ ] set ADR-011/013/014/017 to accepted or leave proposed.
- **Acceptance:** [ ] every row marked confirmed or changed; [ ] ADR statuses consistent with README table.
- **Verification:** diff of docs.

### T014 — Complete the AI usage log reflections
- [ ] **T014 completed**
- **Status:** TODO · **Effort:** M · **Requirement:** C5 · **Files:** `docs/ai-usage-log.md` (Entries 1–6)
- **Steps:** per entry write what AI did well and badly, what was corrected, what was done by hand; fill the tool/model of revision 1 if used; confirm the serving model name.
- **Acceptance:** [ ] no "Authors to complete" left; [ ] statements match what the authors actually did.
- **Verification:** `grep -n "Authors to complete" docs/ai-usage-log.md` returns nothing.

### T015 — Three-version comparison table
- [ ] **T015 completed**
- **Status:** TODO · **Effort:** M · **Requirement:** C6 · **Files:** `docs/ai-usage-log.md` Entry 2
- **Steps:** the authors fill versions 1–3 (without AI, with AI initial prompt, with improved prompt) for use-case model, sequence diagrams, component model, ADRs and write the comparison. The tool cannot supply version 1.
- **Acceptance:** [ ] all cells filled; [ ] comparison states differences in quality and effort.
- **Verification:** teacher's expectation re-read in the original assignment text.

### T016 — Name the NASA standard (or drop the question)
- [ ] **T016 completed**
- **Status:** BLOCKED (missing information) · **Effort:** S · **Files:** `docs/sync-report.md` (line "NASA standards"), `docs/references.md`
- **Steps:** ask which NASA recommendation the assignment means; add it or record that none applies.
- **Acceptance:** [ ] open question removed from the sync report or answered with a source.

### T017 — Fix what T002–T004 and T010–T011 reveal
- [ ] **T017 completed**
- **Status:** TODO (reserved buffer) · **Effort:** L
- **Steps:** each failure gets its own commit and, where behaviour changes, a regression test; keep tests green on SQLite and PostgreSQL.
- **Acceptance:** [ ] all tasks above reach their acceptance criteria; [ ] no new unverified claims in the docs.

### T018 — Replace "not verified" with evidence in the documents
- [ ] **T018 completed**
- **Status:** TODO · **Effort:** M · **Files:** `docs/implementation.md` ("Not verified", status table), `README.md` status paragraph, `docs/cicd.md`, `docs/observability.md`, `docs/sync-report.md`, `docs/verification-plan.md` (V-10, V-09)
- **Depends on:** T002–T004, T010–T011
- **Steps:** state only what was observed, with date and how; leave remaining gaps listed.
- **Acceptance:** [ ] every "never run" sentence is either true or replaced by evidence; [ ] counts of tests match the last run.

### T019 — Final rebuild of PDF and zip
- [ ] **T019 completed**
- **Status:** TODO · **Effort:** S · **Depends on:** T012, T018
- **Steps:** rebuild `Smart_Shopping_Assignment_1.pdf`; zip without `.git`, caches; check page count and tables.
- **Acceptance:** [ ] PDF matches the repository docs; [ ] repository `main` contains the same PDF.

## 7. Improvements — P2

- [ ] **T020 Drift detection shapes (FR-20, V-12)** — TODO · L. `forecast.py`, `drift_checks`; implement sudden/gradual/incremental/recurring detection or reword FR-20 as not implemented. Acceptance: synthetic series of each shape detected by tests.
- [ ] **T021 Golden set ≥ 30 cases (NFR-11, V-16) and router comparison (V-18)** — TODO · L. `tests/`, `llm/gateway.py`. Acceptance: groundedness rate reported; always-small vs always-large vs router compared on tokens, Wh, gCO2e, cost.
- [ ] **T022 Load test (NFR-01, V-05)** — TODO · M. 20 RPS replay, p95 ≤ 2 s report; note single DB connection lock as a likely bottleneck.
- [ ] **T023 Availability probe (NFR-17, V-14)** — TODO · M. Probe `/health/ready` and one insights call per minute; report measured availability and repair time after killing a pod.
- [ ] **T024 Redraw `deployment-kubernetes` and `cicd-pipeline` diagrams** — TODO · M. They show CronJobs/Jobs/Kafka and GitOps pull; the manifests have three Deployments, no Kafka, push-based CI deploy. Acceptance: diagrams compile and agree with `deploy/k8s` and `ci-cd.yml`.
- [ ] **T025 Automated browser test of the frontend** — TODO · M. Playwright, from the revision-8 manual run.
- [ ] **T026 Build the image on the real base and harden** — TODO · S. Confirm `python:3.12-slim` build in CI (done by T002); pin versions; add image scan if time.
- [ ] **T027 Run the Kafka integration tests (`events.yml`)** — TODO · S. Never run; either fix or mark the workflow optional.
- [ ] **T028 Re-run PlantUML syntax check (`docs-validate.yml`)** — TODO · S. Not run since revision 7.

## 8. Optional Tasks — P3

- [ ] **T030** Buttons for `/ops/simulation` in the operator console (S–M).
- [ ] **T031** Measured energy with Kepler/CodeCarbon instead of estimates (L; excluded by the authors' decision, only if time and a supporting environment exist).
- [ ] **T032** TLS, rate limiting, user management for operator endpoints (L).
- [ ] **T033** Persistent Prometheus storage, PostgreSQL backup, Grafana login (M).
- [ ] **T034** Test Electricity Maps adapter with a real token (S).
- [ ] **T035** Argo CD / GitOps pull as described in ADR-009, CronJobs for scheduler (L).
- [ ] **T036** Market signals from public news (optional extension, `docs/market-signals.md`). Status VERIFY: implemented and unit-tested without network (51 market tests; 255 passed on SQLite, 348 on PostgreSQL); six topics, titles plus feed tags, description and hashtags; never run against the real feeds. Remaining: run once with `SHOPPING_MARKET_SCAN=on` on a machine with internet and check `/ops/market`; check feed licences and the BBC and NPR 1019 URLs; authors review the six-topic dictionary and the rule that tags/description only confirm; add `SHOPPING_MARKET_SCAN` to the deployment only after the cluster has internet access (S).

## 9. Testing and Validation

| Check | Command or evidence | Status |
|---|---|---|
| Unit and API tests, SQLite | `python -m pytest -q` (expect 204 passed, 4 skipped; with `kustomize` on PATH) | DONE |
| Tests on PostgreSQL | `SHOPPING_TEST_POSTGRES=<throw-away db> python -m pytest -q` (279 passed, 3 skipped) | DONE |
| Manifests | `kustomize build deploy/k8s/overlays/ollama \| kubeconform -strict -kubernetes-version 1.31.0` | DONE |
| Prometheus files | `promtool check rules deploy/k8s/monitoring/rules.yml` | DONE |
| Workflow syntax | `actionlint .github/workflows/*.yml` | DONE |
| Real CI run | Actions tab | TODO (T002) |
| Cluster smoke test | `scripts/smoke.sh` | TODO (T003) |
| Eviction and RBAC | `scripts/demo-scenario.sh` + controller logs | TODO (T004) |
| Model exchange | `/ops/traces` in GREEN, AMBER, RED | TODO (T010) |
| Live monitoring | Prometheus targets, Grafana panels | TODO (T011) |
| Carbon experiment | `python scripts/carbon_experiment.py` + diff | DONE; decision open (T012) |
| Load, availability, drift, golden set | V-05, V-14, V-12, V-16/V-18 | TODO (P2) |

## 10. Documentation and Presentation

- [ ] Video script followed and video recorded (T005).
- [ ] README and `implementation.md` status updated with real evidence (T018).
- [ ] AI usage log reflections and three-version table (T014, T015).
- [ ] Deployment and CI diagrams redrawn (T024).
- [ ] PDF rebuilt (T019).
- [ ] Prepare to answer: why Deployments instead of CronJobs; why the adaptive scheduler is worse on the default simulator; what is estimated and what is measured; what happens if the Kubernetes API or the energy feed is down; why the deadline wins over the mode.
- [ ] Have ready screenshots of the green pipeline, the dashboard and the taint/eviction output.

## 11. Risks and Blockers

| Risk or blocker | Impact | Mitigation |
|---|---|---|
| Workflow or cluster fails in ways not visible in the sandbox (first real run) | Missed deadline | Start T001–T003 immediately; buffer T017 |
| Eviction does not behave as designed (system pods, PVC, timing) | Core claim unproven | T004 early; if needed adjust tolerations/probes |
| GHCR push or package visibility | `image` job fails | Job saves the image as artifact, so `deploy-kind` can still run; fix permissions |
| Ollama build needs internet and ~1.5 GB; base tag unchecked | Model exchange unproven | Fall back to stand-in model, say so in the video |
| Small models violate the output guardrail | Many flagged or templated answers | Report the rate; the router/guardrail design handles it |
| Default simulator makes the carbon result unfavourable | Weak R5 | T012 decision; report both traces honestly |
| Video over 5 minutes because evictions are slow | Penalty | Cut waits, keep the clock visible; rehearse |
| Authors' items cannot be done by the tool (reflections, version 1 of the comparison, NASA standard) | Incomplete course documentation | Do T014–T016 in parallel with technical work |
| **Source conflicts:** `docs/kubernetes-design.md`, `cicd.md`, the deployment and CI diagrams, ADR-005/009 describe CronJobs, Jobs, Kafka in the cluster and GitOps pull; `docs/submission-note.md` lists ADR statuses | Documents contradict the implementation | Differences are recorded in `implementation.md` rows 2, 12, 17, 22; resolve in T013, T024 |
| Unclear: exact grading criteria and whether the lecture material in the project is binding | Possible missed requirement | Re-read the original assignment text before T006 |

## 12. Recommended Execution Order

1. **T001** push → **T002** CI run (start fixing immediately).
2. In parallel: **T003** cluster smoke test → **T004** eviction evidence.
3. **T011** monitoring check and **T010** Ollama (after T003).
4. **T012** decision and fix (small, can be done any time before T019); authors start **T013–T016**.
5. **T017** fixes for everything found.
6. **T018** documents with real evidence → **T019** PDF and zip.
7. **T005** record the video (after T004, T011, ideally T010 and T012).
8. **T006** submit, at least a day before the deadline.
9. P2 tasks only if everything above is done: T024, T022/T023, T020/T021, T025–T028.

Suggested calendar: 26–27 Nov T001–T004; 28 Nov–1 Dec T010–T017; 2 Dec T018–T019 and recording; 3 Dec submit; 4 Dec spare.

## 13. Definition of Done

- [ ] Latest revision pushed to `main`; `ci-cd.yml` green on that commit (T001, T002).
- [ ] `scripts/smoke.sh` passed on a real kind cluster, twice (T003).
- [ ] Eviction of the worker pod after a pool change observed and recorded (T004).
- [ ] Prometheus targets up and Grafana dashboard shows live data (T011).
- [ ] Model exchange observed with a real local model, or the limitation stated plainly (T010).
- [ ] Carbon numbers in documents and video match `docs/carbon-experiment.md` and say "estimate" and "simulated" (T012).
- [ ] No document claims anything as verified that was not run (T018).
- [ ] AI usage log complete with reflections and the three-version comparison (T014, T015).
- [ ] Video ≤ 5:00 recorded, every claim shown, nothing misrepresented (T005).
- [ ] PDF and zip rebuilt from the final repository (T019).
- [ ] File with the GitHub link and the video submitted in Teams before 4 Dec 2026 23:59, confirmation saved (T006).
