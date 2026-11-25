# Synchronisation of the supplied diagrams with the project (revisions 6 to 8)

The authors supplied a detailed shopper use-case diagram and six sequence diagrams (import, compare, analysis, recommendation, monitoring, carbon) and asked for a two-way synchronisation: add what the diagrams contain and the project lacks, keep what the project does better and redraw the diagram, and decide conflicts on technical merit. This report follows the phases of that request: audit, plan, implementation, validation. Nothing here is a measured result.

## Phase 1: audit

| Component or functionality | State in the project | State in the supplied diagrams | Difference | Resolution |
| --- | --- | --- | --- | --- |
| Use-case model (revision 6 audit) | Four use cases (find and compare, assess and advise, maintain data, adapt to energy), extension: AI explanation | Four shopper use cases (Discovery, Analysis, Decision support, Monitoring) with 16 included sub-use-cases; shopper only; no data maintenance, no energy use case | Different decomposition. The included sub-use-cases (search, filter, compare, view history) are the trivial ones the course feedback asked us to merge. Monitoring is missing as a use case | Rule C: keep our model, which follows the course feedback; add the extension "watch a price" to UC2 and map every element of the supplied diagram to a requirement (below) |
| Import | ASUC-03: raw layer, validation, idempotent upsert, report, event, forecast job; a failure keeps stored data and retries | Fetch, normalise, validate, upsert, record counts; a failure schedules a retry and leaves stored data intact | The project is more detailed | Rule B: no change |
| Compare | UC1 has no sequence (not significant); FR-05 comparison | Search, group exact variants, rank, flag stale offers, side-by-side, empty result with suggested filter changes | No sequence; the hint for an empty result was missing | Added the supplementary sequence SQ-01 with our component names; the comparison uses Price Evidence and Advice Engine per laptop (FR-05) |
| Analysis | ASUC-01: median reference, delta, evidence states, stored forecast with status | Evidence, forecast or absent, "interactive requests never start forecast computation" | Equivalent; the project is more precise | No change (the rule is already in the note of ASUC-01 and ADR-006) |
| Recommendation | Advice rules in the specification; no budget, no preferences, no alternatives | Constraints, alternatives, Buy Now only within constraints | Constraints and alternatives are missing | Rule A: implemented as FR-22 (`advice.py`, `catalog.py`, tests), added to ASUC-01 (messages 22 to 28), the specification, the API and the interface catalogue |
| Monitoring | FR-06: the watch lived in the browser; no component, no sequence | Server-side watchlist under a device id, scheduled check, alert with deduplication key persisted atomically, in-app list | Conflict: browser against server. The browser-only design misses a dip between two visits and cannot record or deduplicate | Rule C: server-side, device-scoped (ADR-017, proposed); Watch Monitor component, CronJob, tables, endpoints, SQ-02, code and tests |
| Carbon-aware execution | ASUC-04a to 04c: carbon, price and renewable signals, hysteresis, three modes, placement, events, runtime policy | Three intensity levels, smaller batch in the medium level, deadline override, an unavailable signal defers non-urgent jobs, "low threshold TBD" | The project is more complete, with one conflict: unavailable signal | Rule B for everything else; the conflict is an open question (see below); our behaviour is kept for now |
| Participant names | Component names of the component model | Service names (Catalog Service, Price Analysis Service, ...) | Naming | Our names are used everywhere; the mapping is below |
| Class model, deployment, C4 | No watch entities, no watch job | Implied by the monitoring sequence | Missing | Added `Watch`, `Alert`, `WatchCheck`; the CronJob `watch-check`; Watch Monitor in the containers |
| Event bus | Implemented (code, manifests, tests) | Not in the supplied diagrams | Not applicable | Unchanged |

### Names in the supplied sequences and in the project

| Supplied participant | Project component |
| --- | --- |
| Import Service, Kubernetes Scheduler | Price Importer, Time Trigger |
| Approved Price Data Source | Price Data Provider |
| Price Repository, Forecast Repository, Watchlist Repository, Job & Forecast Repository | Data Store |
| Job & Metrics Service, Metrics Service | Job Scheduler, Telemetry |
| User Interface | Shopper Client |
| Catalog Service | Catalog Query |
| Price Analysis Service | Price Evidence |
| Recommendation Service | Advice Engine (called by the Shopping API) |
| Monitoring Service | Watch Monitor |
| Forecast Controller | Job Scheduler |
| Carbon Policy Service | Policy Engine |
| Simulated Carbon Signal | Energy Signal Provider |
| Forecast Worker | Forecast Worker |

### Elements of the supplied use-case diagram and where they are

| Supplied element | Requirement and design |
| --- | --- |
| Search laptops, Filter and sort results | FR-01, UC1 |
| Compare products, Compare retailer offers | FR-05, FR-02, UC1 and SQ-01 |
| View 30-day price history, Inspect discount evidence | FR-02, UC2, ASUC-01 |
| View stored 7-day forecast | FR-03, FR-07, ASUC-01 |
| Check price trend | FR-04 (delta and forecast trend in the advice rules) |
| Set budget, Set preferences | FR-22 (budget and preferred brands only; see assumptions) |
| Get Buy Now or Wait advice, View explanation | FR-04, FR-08, ASUC-01 and ASUC-02 |
| Add to watchlist, Set target price | FR-06, SQ-02 |
| Manage alert preferences | FR-06: pause, resume, change or delete a watch; no email or push preferences exist |
| Receive price alerts | FR-06: in-app alert list (SQ-02) |
| Includes between the four use cases | Not drawn; the project merges them into UC2 as the course feedback asked |

## Phase 2: plan

| Category | Change | Priority | Depends on |
| --- | --- | --- | --- |
| Source code | `advice.py` (rules and constraints), `catalog.py` (current offers, alternatives), `watch.py` (watch and alerts), tables in `core.py`, tests | 1 | none |
| Diagrams and source | ASUC-01 sequence, new SQ-01 and SQ-02, component model, class model, use-case model, deployment, C4 container | 1 | the code design |
| Documents | Specification (FR-06, FR-22), ADR-017, architecture catalogues, data model and API, Kubernetes design, observability, verification plan, traceability, significant use cases, README | 2 | diagrams |
| No change needed | Import, AI explanation, carbon decide, act and place sequences, C4 context, activity and pipeline diagrams, event bus | n/a | n/a |
| Open decisions | Unavailable carbon signal, server-side watch (ADR-017), meaning of "preferences", which NASA recommendation is meant | see below | the authors |

## Phase 3: what was done

- **Advice with constraints (FR-22).** Pure rules identical to the specification; above the budget Buy Now becomes Wait with a reason; a brand mismatch adds a caveat; alternatives come from Catalog Query through the Shopping API so that the rules stay free of data access.
- **Price watch (FR-06, ADR-017).** Watches are stored per device; the check takes the lowest latest offer per laptop, ignores observations older than 48 hours, and stores one alert per episode in one transaction with its deduplication key; an episode ends when a fresh price rises above the target; stale data never creates or resets an alert.
- **Diagrams.** ASUC-01 now has 32 messages (the constraints are applied in message 22, alternatives in 24 to 28); SQ-01 has 18 and SQ-02 has 30 numbered messages.
- **Files.** Created: `docs/adr/ADR-017.md`, `docs/sync-report.md`, `docs/diagrams/sequence-compare.puml`, `docs/diagrams/sequence-watch.puml` and their two images, `src/shopping/advice.py`, `src/shopping/catalog.py`, `src/shopping/watch.py`, `tests/test_advice.py`, `tests/test_watch_catalog.py`. Modified: `README.md`, `docs/architecture.md`, `docs/data-model-api.md`, `docs/distribution-and-dependability.md`, `docs/event-bus.md`, `docs/feedback-response.md`, `docs/ai-usage-log.md`, `docs/submission-note.md`, `docs/kubernetes-design.md`, `docs/observability.md`, `docs/project-specification.md`, `docs/significant-use-cases.md`, `docs/traceability.md`, `docs/verification-plan.md`, `src/shopping/core.py` (new tables), the diagrams `use-case`, `component-model`, `class-model`, `deployment-kubernetes`, `c4-container`, `sequence-assess-price` and their images, and the build script of the PDF. Removed: nothing.

## Phase 4: validation

| Check | Result |
| --- | --- |
| Automated tests | 68 passed and 3 skipped (the three integration tests need a Kafka broker); the 30 event bus tests still pass, so the earlier functionality is not broken |
| PlantUML syntax | All 17 diagram sources compile; all images were rendered again |
| Visual check | The new sequences, the use-case model and the component model were inspected; the component model is dense but has no overlapping text |
| Links and identifiers | No broken link in the Markdown files; every FR (01 to 22) and NFR (01 to 20) appears in the specification and the traceability matrix and has at least one test; every ADR (001 to 017) appears in the matrix |
| Message numbers | The numbers quoted for ASUC-01 were recomputed from the new source |
| Diagrams against code | The advice rules, alternatives and watch behaviour in the diagrams match `advice.py`, `catalog.py` and `watch.py`, which are covered by tests; the other diagrams describe a design that has no code yet |

**Not verified:** the integration tests, the demonstration and the Kubernetes manifests against a real Kafka broker or cluster (no container runtime was available); the GitHub workflows (they have not run on GitHub); the watch and advice code behind a real REST API, PostgreSQL and a CronJob (none exists yet: `watch-check` is shown in the diagram and described, but there is no manifest or entry point); the retention of inactive device identifiers (proposed, not implemented).

## Open points and assumptions

1. **Unavailable carbon signal.** The supplied sequence defers non-urgent jobs when the signal is unavailable. The project (ADR-004) runs as GREEN with the reason `signal_stale`, so that a sensor failure does not degrade service. Both keep the 24-hour deadline. We kept the project's behaviour; the authors should confirm, because the supplied option is the more cautious one for carbon.
2. **Server-side watch (ADR-017)** is proposed, not accepted: it stores a pseudonymous device identifier on the server, which revision 2 had avoided.
3. **"Set preferences"** is not defined in the supplied diagrams. We implemented preferred brands only and did not invent further preferences.
4. **NASA standards.** We found no NASA standard for UML use-case, sequence or component diagrams in the supplied materials and do not claim compliance with one. The diagrams follow OMG UML 2.5.1 and the course rules. If a specific NASA document is meant, it must be named.
5. The 30-minute check interval, the 48-hour freshness limit and the limit of 20 watches per device are demonstration values.

## Result by diagram

| Diagram | Original problem | Change | Agreement with the implementation | Validation |
| --- | --- | --- | --- | --- |
| use-case | No monitoring use case; constraints not visible | Extension "watch a price"; legend names constraints and SQ-02 | Matches FR-06 and FR-22 | Compiles, rendered and inspected |
| component-model | No component for the watch | Watch Monitor with `IWatchlist`, `IWatchCheck`, `ICatalog` | Matches `watch.py` and the interface catalogue | Compiles, rendered and inspected |
| class-model | No watch entities | `Watch`, `Alert`, `WatchCheck` | Matches the tables in `core.py` | Compiles, rendered |
| deployment-kubernetes | No watch job | CronJob `watch-check`, Watch Monitor in the backend, topic list | Design only (no manifest for the watch job) | Compiles, rendered |
| c4-container | Watch missing | Watch Monitor in backend and controllers; tables | Design only | Compiles, rendered |
| sequence-assess-price (ASUC-01) | No constraints, no alternatives | Constraints, `findAlternatives`, 32 messages | Matches `advice.py` and `catalog.py` | Compiles, rendered, numbers rechecked |
| sequence-compare (SQ-01, new) | No sequence for UC1 | Search, comparison, empty result | Design only | Compiles, rendered |
| sequence-watch (SQ-02, new) | No sequence for the watch | Save, check, alert, read | Matches `watch.py` | Compiles, rendered and inspected |
| sequence-import, sequence-ai-explanation, sequence-carbon-decide, sequence-carbon-act, sequence-carbon-place | None found | Unchanged | Design; the event parts match `src/events` | Compile |
| c4-context, carbon-policy-activity, cicd-pipeline | None found | Unchanged | Design | Compile |

## Revision 7: the supplied diagrams are now the project's diagrams

The authors supplied the diagrams again, in the form of one set (`01-import` to `09-component`) and a use-case figure, and asked that every old diagram be replaced by the new one everywhere (README, documents, PDF), that the comments in a separate frame below a diagram be moved from the image to the text under it, and that the component keep the name **Carbon Monitor**.

| Diagram | Replaced by | Change in the text |
| --- | --- | --- |
| sequence-import (ASUC-03) | `01-import` | Message numbers of ASUC-03 in `significant-use-cases.md` recomputed (20 messages became 18). |
| sequence-compare (SQ-01) | `02-compare` | Linked from the supplementary table. |
| sequence-assess-price (ASUC-01) | `03-analysis` and `04-recommendation` | The normal flow of ASUC-01 now names the diagram and the message range of each step (18 and 19 messages). |
| sequence-watch (SQ-02) | `05-monitoring` | Linked from the supplementary table. |
| sequence-carbon-decide, -act, -place (ASUC-04a to c) | `06-carbon` as the overview; the three detailed sequences are kept in `docs/diagrams/detail` | ASUC-04 describes the overview (28 messages) and keeps the numbered details. |
| sequence-ai-explanation (ASUC-02) | `07-ai-explanation` | Message numbers recomputed (35 messages became 26); storing the answer and the session turn is described in `ai-architecture.md`. |
| component-model | `09-component` | Legend text moved below the image in `architecture.md` and the README. |
| (new) | `08-communication` | Communication diagram of ASUC-01 added to `architecture.md`. |
| use-case | New figure `use-case.png` and `use-case.svg` in the colour scheme of the supplied figure | See below. |

**Use-case figure.** The supplied figure (Discovery, Analysis, Decision Support, Monitoring) does not match the project: it has no price-data maintenance and no energy adaptation, and the course feedback asked us to merge the use cases. The figure keeps its structure (coloured bands with a pill label, a main use case on the left, four included steps on the right, the shopper on the left) and its colours, and changes the content: Discovery is UC1; the Analysis band is UC2 with the evidence and advice steps and the two extensions (AI explanation, price watch); a new green band is UC3 (maintain price data) and a new purple band is UC4 (adapt to carbon and energy-price conditions); the operator, the time trigger and the two external providers were added as actors. "Set budget" and "Set preferences" are part of the advice step (FR-22).

**Names.** The component that senses the signals is called **Carbon Monitor** in all diagrams and documents (the diagrams `06-carbon` and `09-component`, `architecture.md`, `carbon-adaptation.md`, ADR-004, the traceability matrix and the C4 and deployment diagrams). The signal provider is still called Energy Signal Provider and its interfaces IEnergyFeed and IEnergySignal.

**Differences the authors should know about.** The new sequences are condensed: they do not show the telemetry calls, the operator configuration of the policy, the AI routing and the placement safety checks, which are kept in the detailed carbon sequences and in the text. They use plain automatic numbering (1, 2, 3, ...) instead of the two-digit form. Alternatives are drawn as `alt` blocks, so the messages of all branches are numbered one after the other; a number therefore stands for a message, not for one run through the diagram.

**Validation (revision 7).** All 18 PlantUML sources compile (the old jar 1.2019.06 was used for the new diagrams; CI uses 1.2024.7); the images of the nine diagrams were rendered and inspected; message numbers in `significant-use-cases.md` were recomputed from the new sources; no stale links to removed files remain. The 68 tests were not affected (no code changed). The use-case figure is a hand-built SVG; it is not checked by a tool.

## Revision 8: implementation

The authors confirmed the recommended proposals and asked for code for the REST API and frontend, the Policy Engine and Carbon Monitor, the Job Scheduler, Forecast Worker and Model Evaluator, the Placement Controller, the LLM Gateway with router, guardrails and a local model, and the price import on PostgreSQL. What exists, how it was checked and the sixteen places where the code differs from the design are in [implementation.md](implementation.md). No diagram was changed in this revision.

**Files created.** `src/shopping/`: `schema.py`, `db.py`, `energy.py`, `policy.py`, `importer.py`, `seed.py`, `forecast.py`, `scheduler.py`, `placement.py`, `service.py`, `api.py`, `__main__.py`, `llm/__init__.py`, `llm/gateway.py`, `llm/providers.py`, `web/index.html`, `web/app.js`, `web/style.css`; `tests/`: `conftest.py`, `test_policy_energy.py`, `test_importer.py`, `test_forecast_scheduler.py`, `test_placement.py`, `test_llm_gateway.py`, `test_api.py`; `deploy/postgres/postgres.yaml`; `.github/workflows/app.yml`; `docs/implementation.md`.
**Files modified.** `src/shopping/core.py` (schema moved to `schema.py`, explicit column list in the observation insert), `tests/test_watch_catalog.py` (explicit column lists), `tests/test_deploy.py` (PostgreSQL manifest), `requirements.txt` (`psycopg[binary]`), `deploy/docker-compose.yml`, `README.md`, `docs/architecture.md`, `docs/data-model-api.md`, `docs/cicd.md`, `docs/kubernetes-design.md`, `docs/verification-plan.md`, `docs/traceability.md`, `docs/adr/ADR-008.md`, `docs/ai-usage-log.md`, this report.

**Sync rules applied.** Missing functionality was implemented from the documents (rule A); the existing advice, watch, catalog and event code was kept unchanged except for the schema location and explicit column lists, which a new column made necessary (rule B, minimal change); conflicts between documents and a working implementation were resolved technically and are listed with their reasons in implementation.md (rule C); the open decisions (candidate model, concurrency meaning, stand-in model, authentication level) were put to the authors (rule D) and confirmed by them on 25 November 2026; drift shapes and the golden set stay open.

| Check | Result |
| --- | --- |
| Tests on SQLite | 173 passed, 3 skipped (Kafka integration) |
| Tests on PostgreSQL 16 | 238 passed, 3 skipped (the same suite plus 65 PostgreSQL cases), against a real local server |
| Earlier functionality | The 68 earlier tests pass unchanged apart from explicit column lists in the test data |
| Running application | Started with `--demo`, queried over HTTP, frontend driven in Chromium without console or policy errors |
| Not verified | Kafka integration tests, Kubernetes manifests, `docker-compose.yml`, GitHub workflows, `kubectl` and model HTTP adapters against real systems, load, availability and energy measurements, other browsers and accessibility tools |

| Diagram | Original problem | Change | Agreement with implementation | Validation status |
| --- | --- | --- | --- | --- |
| use-case | None found | Unchanged | UC1 to UC4 are implemented; the operator console is minimal | Compiles as of revision 7 (not re-run in this revision) |
| 01-import | None found | Unchanged | Matches `importer.py` and `core.py` (raw batch, validation, idempotent insert, event, job); the report is stored in `import_runs` | As above |
| 02-compare, 03-analysis, 04-recommendation | None found | Unchanged | Match `service.py`, `forecast.py`, `advice.py`, `catalog.py`; ids are text | As above |
| 05-monitoring | None found | Unchanged | Matches `watch.py` and the endpoints; the check runs inside the control loop, not as a CronJob | As above |
| 06-carbon and the three detailed sequences | None found | Unchanged | Matches `energy.py`, `policy.py`, `scheduler.py`, `placement.py`; the controller is one process instead of CronJobs; concurrency means jobs per tick | As above |
| 07-ai-explanation | None found | Unchanged | Matches `llm/gateway.py`; cache and memory are in process | As above |
| 08-communication, 09-component | None found | Unchanged | Components exist as modules inside one process; the interfaces are Python calls, not the drawn interface objects, and the allowed-to-use rules are not checked automatically | As above |
| deployment-kubernetes, c4-container, cicd-pipeline | None found | Unchanged | Design only; PostgreSQL manifest and one new workflow exist, no application Deployment or CronJob | As above |

## Revision 9: final project (deployment, observability, carbon metrics, dynamic behaviour)

The authors asked for a system that is deployable and operable for the final project submission (running system, CI/CD, observability, carbon metrics, dynamic behaviour, video) and decided: Kustomize, the Placement Controller through the Kubernetes REST API with a service account, Ollama with a small model, carbon values as labelled estimates.

**Files created.** `Dockerfile`, `.dockerignore`, `.yamllint.yml`, `SUBMISSION.txt`; `src/shopping/metrics.py`; `deploy/k8s/base/*` (namespace, RBAC, configuration, API, worker, controller; `postgres.yaml` moved here from `deploy/postgres/`), `deploy/k8s/monitoring/*`, `deploy/k8s/overlays/kind`, `deploy/k8s/overlays/ollama`, `deploy/kind/kind-config.yaml`, `deploy/ollama/Dockerfile`, `deploy/README.md`; `scripts/demo-lib.sh`, `smoke.sh`, `demo-up.sh`, `demo-down.sh`, `demo-scenario.sh`, `carbon_experiment.py`; `.github/workflows/ci-cd.yml`; `tests/fake_k8s.py`, `test_roles_simulation.py`, `test_k8s_manifests.py`, `test_carbon_experiment.py`; `docs/carbon-experiment.md`, `docs/video-script.md`.
**Files modified.** `src/shopping/placement.py` (`KubernetesApiCluster`), `energy.py` (`ControlledFeed`), `service.py` (feed, cluster, policy and cache configuration; `step` split into `step_control` and `step_work`; Prometheus rendering moved to `metrics.py`), `api.py` (`/ops/simulation`, latency histogram), `__main__.py` (roles, SIGTERM, environment), `scheduler.py` (assumed job duration, immediate baseline for the experiment), `core.py` and `policy.py` (configurable cache lifetime and initial policy, tolerance of a concurrent first start), `db.py` and `schema.py` (advisory lock, `simulation_signal`), `llm/providers.py` (JSON mode, `ModelByMode`), `src/events/consumer.py` (one line: the store is used from the loop thread), `.github/workflows/app.yml` (reusable), `tests/conftest.py`, `tests/test_api.py`, `test_placement.py`, `test_llm_gateway.py`, `test_deploy.py` (path of the PostgreSQL manifest), `README.md`, `docs/implementation.md`, `cicd.md`, `observability.md`, `kubernetes-design.md`, `verification-plan.md`, `ai-usage-log.md`, `submission-note.md`, `traceability.md`.

**Defects found during the work.** The processed-event store of the event bus was bound to the thread that created it, so the first `mode.changed` event handled by the control-loop thread failed (found by running the real server; fixed, with a regression test that fails without the fix). A local helper function in `api.py` shadowed the audit function that the new endpoint imported (found by a test). The default signal simulator makes the adaptive scheduler worse than immediate execution because its renewable window lies on the carbon peak (found by the experiment; **not changed**, recorded as an open decision).

| Check | Result |
| --- | --- |
| Tests on SQLite | 204 passed, 4 skipped (three Kafka integration tests, one PostgreSQL-only test) |
| Tests on PostgreSQL 16 | 279 passed, 3 skipped, including three processes started together on an empty database |
| Manifests | `kustomize build` and `kubeconform -strict` (Kubernetes 1.31.0) accept `base`, `overlays/kind` and `overlays/ollama` (11, 24, 26 resources) |
| Monitoring files | `promtool` accepts the rules and the configuration; the exposition parses with the Prometheus parser |
| Workflows and scripts | `actionlint`, `yamllint`, `shellcheck`: no findings. No workflow has run on GitHub |
| Image | Built and started on a locally assembled Python 3.13 base (the sandbox cannot pull images); not built on `python:3.12-slim` |
| Not verified | Any deployment on a real cluster (eviction, RBAC, node labels, scraping, dashboard), the Ollama image and a real model, GitHub Actions, GHCR, Kafka, load and energy measurement |

| Diagram | Original problem | Change | Agreement with implementation | Validation status |
| --- | --- | --- | --- | --- |
| use-case, 01 to 05, 07, 08, 09 | None found | Unchanged | As in revision 8 | Not re-run in this revision |
| 06-carbon and the three detailed sequences | None found | Unchanged | Now also implemented with separate processes: the controller senses, decides and places; the worker runs the jobs; the mode is shared through the database | Not re-run |
| deployment-kubernetes, c4-container | Showed CronJobs, Jobs and Kafka for the application | Unchanged (the drawing is the target design) | The manifests differ: three Deployments (api, worker, controller), no CronJobs or Jobs, no Kafka in the cluster, Prometheus and Grafana added | The difference is recorded in implementation.md (rows 17 and 22); not re-drawn |
| cicd-pipeline | Showed GitOps with a pull model | Unchanged | The workflow deploys push-based into a kind cluster; Argo CD is not implemented | Difference recorded in cicd.md; not re-drawn |

