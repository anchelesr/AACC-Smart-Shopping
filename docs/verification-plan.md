# Verification checks

Each check has an identifier (V-nn) that the [traceability matrix](traceability.md) uses. Each check says what evidence we will collect once the application exists. Until then nothing below is a result.

| ID | Check | Requirements | Evidence to collect |
| --- | --- | --- | --- |
| V-01 | Data fixture | FR-01, FR-02 | At least 10 exact laptop variants, three sample retailers and 30+ days of labelled observations where the fixture supports them. |
| V-02 | Import integrity | FR-09, FR-10, NFR-05 | Import the same batch twice; inspect accepted and rejected counts and confirm there are no duplicates; confirm the forecast job deadline is not reset. |
| V-03 | Shopper flow | FR-01 to FR-07 | Search, filter, compare offers, reference and delta, missing and stale forecast handling, freshness and provenance display, price watch in the browser. |
| V-04 | Advice rules | FR-04 | Unit and table tests for every rule branch, including insufficient evidence and the no-forecast case. |
| V-05 | API load | NFR-01 | Replay 20 requests/s on seeded data; report p95 latency and error rate against the 2 s target. |
| V-06 | Energy sensing and decision | FR-11, FR-12, NFR-16 | Feed low, high, noisy and missing traces of intensity and price, with and without the renewable flag; inspect mode changes, the more-restrictive rule, hysteresis, the one-signal-missing case, the stale-signal fail-safe and the override with its expiry. |
| V-07 | Runtime reconfiguration | NFR-13 | Change a threshold through the operator endpoint and measure the time until the new behaviour appears; no redeployment. |
| V-08 | Adaptive behaviour | FR-13, FR-14, NFR-02, NFR-03 | Report the maximum and 95th-percentile forecast age against the 24-hour window under the replayed trace. In each mode check job decisions, worker concurrency, assistant routes, cache lifetime and optional batches; confirm the deadline override in every mode. |
| V-09 | Sustainability comparison | NFR-10 | Same jobs and questions under the immediate run, the adaptive run and the adaptive run with placement; record kWh, estimated gCO2e and cost, deferrals, evictions, forecast age and deadline errors, with the estimation method (estimated or measured). Run the same job on both pools and report time, energy and gCO2e. |
| V-10 | Placement | FR-18, NFR-20 | Switch the simulated mode and renewable flag; confirm that flexible pods move and the others do not, that taints change only on a decision change, that the dwell time and the last-node rule hold, and that skipped decisions are recorded. |
| V-11 | Events | FR-19, NFR-19 | Publish a duplicated `price.changed` (one job only), drop a `mode.changed` (the pull repairs it within 60 s), stop the broker (shopper path unaffected), watch consumer lag. Automated: 30 tests without a broker (`tests/`, listed in [event bus](event-bus.md)) pass; the three integration tests against a real broker, the demonstration and the workflow `events.yml` are still to be run, and their result recorded here. |
| V-12 | Drift and live quality | FR-20 | Inject a sudden and a recurring price change into the fixture; confirm the drift score and shape, the live error, the shadow comparison and the rollback of the active model. |
| V-13 | Cost control | NFR-18 | Exhaust the token budget; confirm that the router answers from templates and that the dashboard shows the cost. |
| V-14 | Availability probe | NFR-17 | A synthetic probe against the ready endpoint and one insights request every minute for the test period; report the measured availability and the repair time after a forced pod failure and a rollback. |
| V-15 | Forecast evaluation | FR-15, NFR-07, NFR-12 | Replace the forecast candidate and the model provider with a stub through their adapter interfaces without changing any other component; a CI check of the allowed-to-use rules in [architecture](architecture.md). Backtest results for baseline and candidate, the adoption decision, live error monitoring and the fallback to the baseline. |
| V-16 | Assistant groundedness | FR-08, NFR-11 | Golden set results: grounded numbers, label agreement, refusals, injection attempts, fallback rate. |
| V-17 | Assistant routing and trace | FR-17, FR-08, NFR-14 | Route shares by mode, trace records with tokens, latency and estimated energy, the review queue flow. |
| V-18 | Router value and cost | FR-21, NFR-18, NFR-10 | A table-driven test of every combination of value score, mode, budget and provider state; a golden routing set with the expected route; the same questions through always-small, always-large and the router, recording tokens, estimated Wh, gCO2e, cost and grounded share (run D in [carbon adaptation](carbon-adaptation.md)); every trace record carries route, reason, score and cost estimate. |
| V-19 | Fault tolerance | NFR-04 | Stop the worker, the model provider, the local model runtime, the energy feed and the broker in turn and confirm that stored prices remain visible. |
| V-20 | Kubernetes evidence | NFR-09 | Deployments, Services, CronJobs and Jobs, retry outcomes, logs and resource constraints. |
| V-21 | Monitoring | FR-16, NFR-08 | Dashboards for latency, failures, job age, forecast freshness, mode timeline, signals, placement and assistant routes; one trace id followed from a shopper request to the model call; the alerts fire on injected faults. |
| V-22 | CI/CD | NFR-15 | Workflow runs for the stages in [CI/CD](cicd.md), image tags, deployment sync, smoke tests and one rollback by reverting a commit. |
| V-23 | Security | NFR-06 | Secret scan result, TLS at the ingress, authentication on operator endpoints, an injection test in product text. |
| V-24 | Price watch and alerts | FR-06, NFR-05 | Automated: `tests/test_watch_catalog.py` (validation, device scoping, one alert per episode, no duplicate on repeated checks, stale data ignored, new episode after a rise or a new target, pause and resume, rollback of a duplicate alert, deletion). To do: the same flow through the real API and CronJob. |
| V-25 | Budget, brand constraints and alternatives | FR-22, FR-04 | Automated: `tests/test_advice.py` (every rule and boundary, stale or missing forecast, Buy Now withheld above the budget, brand mismatch) and the alternatives tests in `tests/test_watch_catalog.py` (budget, brand, order, limit). To do: the response of the real endpoint. |

## Evidence that exists after revision 9 (revision 8 evidence plus the following)

Revision 9 added, without changing the rows below except where noted: V-10 now also has `KubernetesApiCluster` tested against a fake Kubernetes API over HTTP (`tests/test_placement.py`, `tests/fake_k8s.py`) and manifests showing that only the worker and the local model can be evicted (`tests/test_k8s_manifests.py`); V-09 has a first, simulated answer in [carbon-experiment.md](carbon-experiment.md) (timing effect on a simulated trace, estimates, immediate against adaptive; no measured energy and no placement comparison); V-19 has no new evidence; the three-process test on PostgreSQL and the metrics tests are new automated evidence for the deployment. **The cluster-level checks of V-10 (pods moving, eviction) are implemented as `scripts/smoke.sh` and `scripts/demo-scenario.sh` and have not been run.**

## Evidence that exists after revision 8

The checks above were written before the application existed. This table says which of them now have automated evidence and what is still missing. "Tests" means the suite in `tests/` (173 passed and 3 skipped on SQLite; 238 passed and 3 skipped with PostgreSQL 16); the gaps are real gaps.

| Check | Evidence now | Still missing |
| --- | --- | --- |
| V-02 Import integrity | `tests/test_importer.py` (same batch twice, rejected rows with reasons, normalised timestamps, broken bus), `test_the_deadline_is_never_reset_by_later_price_changes` | None for the checks as written |
| V-03 Shopper flow | `tests/test_api.py` (search, sort, filter, insights, constraints, compare, watch and alert lifecycle); the frontend was driven once in Chromium | Automated browser test; missing and stale forecast display; other browsers |
| V-04 Advice rules | `tests/test_advice.py` and the evidence and forecast freshness tests | None for the checks as written |
| V-05 API load | None | The replay at 20 requests per second and the p95 report |
| V-06 Energy sensing and decision | `tests/test_policy_energy.py`: the documented thresholds and hysteresis, a single noisy sample, the more restrictive signal, renewable, stale or missing signal, one signal missing, invalid and failing feeds, one `mode.changed` per change | A replayed recorded trace; the live Electricity Maps feed |
| V-07 Runtime reconfiguration | Policy versions and validation, `PUT /ops/policy`, override with expiry | The measured time until a new threshold takes effect |
| V-08 Adaptive behaviour | `tests/test_forecast_scheduler.py`: GREEN, AMBER and RED job decisions, jobs per tick, deadline wins, lease recovery, back-off, optional evaluation with the 7-day limit, job log with estimated kWh and gCO2e; `tests/test_llm_gateway.py`: routes by mode | Forecast age p95 under a replayed trace; cache lifetime per mode is tested only for GREEN |
| V-10 Placement | `tests/test_placement.py` with a fake cluster, a faked `kubectl` runner and a fake Kubernetes API server: taints, dwell time, ready-node rules, recorded decisions, failures, conflicting writes | A real cluster: pods moving, tolerations, eviction (`scripts/smoke.sh` is written, never run) |
| V-11 Events | The 30 event bus tests, plus `test_control_loop_end_to_end_events_to_forecast_to_advice` and the lost-event repair in `test_import_survives_a_broken_bus` | Kafka integration tests (never run) |
| V-13 Cost control | `test_token_budget_exhaustion_and_unreadable_counter_fall_back` | The dashboard |
| V-15 Forecast adapter | The candidate and the baseline sit behind one function table and are replaced in a test (`MODELS`) | The CI check of the allowed-to-use rules |
| V-17 Assistant routing and trace | `tests/test_llm_gateway.py`: trace record, review queue flow, memory, cache | Route shares by mode over a question set |
| V-18 Router value and cost | Table-driven tests of value, mode, budget and provider state and the hard rules | Golden routing set; the comparison of always-small, always-large and the router with tokens, Wh, gCO2e, cost |
| V-09 Sustainability comparison | `scripts/carbon_experiment.py` and [carbon-experiment.md](carbon-experiment.md): immediate against adaptive on a simulated signal, estimated energy and emissions | Measured energy, the comparison with placement, real signals; the default simulator gives a worse result than immediate execution (open decision) |
| V-12 Drift, V-16 Groundedness (golden set), V-05, V-14, V-19 | None (V-16: only the guardrail unit tests) | All of it; FR-20 drift shapes are not implemented |

