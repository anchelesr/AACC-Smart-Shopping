# Synchronisation of the supplied diagrams with the project (revision 6)

The authors supplied a detailed shopper use-case diagram and six sequence diagrams (import, compare, analysis, recommendation, monitoring, carbon) and asked for a two-way synchronisation: add what the diagrams contain and the project lacks, keep what the project does better and redraw the diagram, and decide conflicts on technical merit. This report follows the phases of that request: audit, plan, implementation, validation. Nothing here is a measured result.

## Phase 1: audit

| Component or functionality | State in the project | State in the supplied diagrams | Difference | Resolution |
| --- | --- | --- | --- | --- |
| Use-case model | Four use cases (find and compare, assess and advise, maintain data, adapt to energy), extension: AI explanation | Four shopper use cases (Discovery, Analysis, Decision support, Monitoring) with 16 included sub-use-cases; shopper only; no data maintenance, no energy use case | Different decomposition. The included sub-use-cases (search, filter, compare, view history) are the trivial ones the course feedback asked us to merge. Monitoring is missing as a use case | Rule C: keep our model, which follows the course feedback; add the extension "watch a price" to UC2 and map every element of the supplied diagram to a requirement (below) |
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
