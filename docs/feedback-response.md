# Response to the course feedback (revisions 2 to 4)

This note maps each comment on revision 1 to the change we made in revision 2 and where to find it. The sections after it describe revision 3 (lecture material) and revision 4 (decisions approved by the authors).

| # | Feedback | What we changed | Where |
| --- | --- | --- | --- |
| 1 | Some use cases are trivial; searching and filtering should be merged, and so should the 30-day history and the discount evidence; the diagram could have 3-4 use cases. | Eleven use cases became four: UC1 find and compare offers, UC2 assess price and get advice, UC3 maintain price data, UC4 adapt operation to carbon conditions. | [use-case.puml](diagrams/use-case.puml), [specification](project-specification.md) |
| 2 | The feature set should be expanded. | Seventeen functional requirements with MoSCoW priorities and a stakeholder table. New: side-by-side comparison, shortlist and price watch, freshness and provenance display, AI assistant, import report, model evaluation, review queue, runtime policy. | [specification](project-specification.md) |
| 3 | The sequence diagrams go too far into the solution space (we do not need to know it is a React UI). | All sequences use role names; technologies appear only in the deployment view and the ADRs. | [sequence diagrams](diagrams/) |
| 4 | The selected use cases (except carbon) are trivial, and all significant use cases should have a sequence. | Four significant use cases (ASUC-01 to ASUC-04), five sequences. UC1 is explicitly classified as not significant, with the reason. | [significant use cases](significant-use-cases.md) |
| 5 | Notation: messages should be numbered; internal processing (self-calls) should be shown. | Every sequence is auto-numbered and shows self-calls (derive reference, validate, classify, decide, grounding check) and alt, loop and opt fragments. The text refers to the message numbers. | [sequence diagrams](diagrams/) |
| 6 | Carbon: the signal is read and jobs are deferred, but how else is the application aware of carbon, and how does it change its configuration and behaviour? | A sense, decide, act and feedback loop with operating modes, hysteresis, a stale-signal fail-safe, an operator override and a runtime policy stored with an audit trail. Forecast jobs, worker concurrency, assistant routing, cache lifetime and optional batches follow the mode. Two sequences cover the use case. | [carbon adaptation](carbon-adaptation.md), [ADR-004](adr/ADR-004.md), [ASUC-04a](diagrams/sequence-carbon-decide.puml), [ASUC-04b](diagrams/sequence-carbon-act.puml) |
| 7 | The component model does not follow UML notation; the arrows are unclear; it is static, so it should show how components communicate; there is nothing about interfaces. | UML 2 components with provided and required interfaces and assembly connectors, no plain arrows; interface and component catalogues; an allowed-to-use specification; the LLM Gateway structure as a second view. Communication over time is in the sequences. | [component model](diagrams/component-model.puml), [architecture](architecture.md), [ADR-010](adr/ADR-010.md) |
| 8 | Good: meaningful description and separation of concerns; significant use cases identified; Kubernetes and monitoring envisioned. | Kept and extended: workloads by lifecycle, probes, resource limits, monitoring of modes, routes and energy. | [Kubernetes design](kubernetes-design.md) |
| 9 | Improve: more detail on carbon behaviour (a better use case). | See row 6. | [carbon adaptation](carbon-adaptation.md) |
| 10 | Improve: the AI part is currently thin. | AI components by type, forecast lifecycle, baseline and evaluation gate, LLM gateway with router, guardrails, memory, cache, tracing and human review, golden-set evaluation, risks. | [AI architecture](ai-architecture.md), [ADR-007](adr/ADR-007.md), [ADR-008](adr/ADR-008.md) |
| 11 | Improve: CI/CD needs to be envisioned. | Pipeline with eight stages and gates (including AI gates), environments, GitOps delivery and rollback, a pipeline diagram and a working documentation check. | [CI/CD](cicd.md), [ADR-009](adr/ADR-009.md), [diagram](diagrams/cicd-pipeline.puml) |
| 12 | Given the allowed use of AI, expectations are higher. | A traceability matrix, explicit evaluation plans, honest limits, ADRs with alternatives, and a log of how AI was used in this revision. | [traceability](traceability.md), [AI usage log](ai-usage-log.md) |

## Identifier changes

| Before | After |
| --- | --- |
| FR-01, FR-02, FR-03 | FR-01 |
| FR-04, FR-05 | FR-02 |
| FR-06 | FR-03 |
| FR-07 | FR-04 |
| FR-08 | FR-09 |
| FR-09 | FR-11 to FR-14 |
| FR-10 | FR-16 |
| ASUC-01 import | ASUC-03 |
| ASUC-02 view evidence | ASUC-01 |
| ASUC-03 explain advice | ASUC-01 (rules) and ASUC-02 (AI explanation) |
| ASUC-04 refresh forecasts | ASUC-04 (now 04a and 04b) |
| NFR-01 to NFR-10 | unchanged; NFR-11 to NFR-16 added in revision 2, NFR-17 to NFR-20 in revision 3 |
| FR-01 to FR-17 | unchanged in revision 3; FR-18 to FR-20 added in revision 3 and FR-21 in revision 4; FR-11 and FR-12 widened from carbon to energy signals |
| ASUC-04 (04a, 04b) | ASUC-04c (placement) added in revision 3 |
| ADR-001 to ADR-006 | unchanged numbers; ADR-004 rewritten, others extended; ADR-007 to ADR-010 added; ADR-011 to ADR-015 added in revision 3, ADR-016 in revision 4 (ADR-015 retitled and made specific) |
| Carbon Monitor, Carbon Signal Provider, ICarbonFeed | Energy Monitor, Energy Signal Provider, IEnergyFeed (revision 3) |

## Revision 3: integration of the lecture material

After revision 2 we went through the lecture notes (sessions 1 to 7, as supplied by the authors) and took over what applies to this project. We did not add topics that do not fit, such as training our own models.

| Topic from the lectures | What we changed | Where |
| --- | --- | --- |
| Energy awareness has two layers: the application changes its behaviour, and the application is moved to cheaper or greener places | The signal now has intensity, price and a renewable flag; modes follow the more restrictive signal. A Placement Controller moves flexible workloads between a standard and an eco node pool with taints and tolerations. | [carbon adaptation](carbon-adaptation.md), [ADR-013](adr/ADR-013.md), [ASUC-04c](diagrams/sequence-carbon-place.puml) |
| Publish-subscribe and Kafka | An event bus carries `price.changed` and `mode.changed`; the database stays the source of truth. | [ADR-012](adr/ADR-012.md), [component model](diagrams/component-model.puml) |
| Monitoring versus observability, Prometheus, Grafana, tracing, measuring energy | Metric catalogue, dashboards per audience, alerts, traces, estimated versus measured energy. | [observability](observability.md), [ADR-014](adr/ADR-014.md) |
| Availability arithmetic, fault, error and failure, CAP, consistency | Availability target with worked numbers, a fault table, consistency per data type. | [distribution and dependability](distribution-and-dependability.md), NFR-17 |
| Data engineering (sources, layers, leakage, framing) | Raw, validated and derived layers; leakage rules; framing of the forecast. | [data engineering](data-engineering.md) |
| Deployment of ML systems (serving patterns, drift, shadow, rollback) | Batch prediction for forecasts, model as a service for the assistant; drift checks, live error, shadow runs and rollback. | [ADR-011](adr/ADR-011.md), [AI architecture](ai-architecture.md), FR-20 |
| LLM harness, routing, tokens as budget | Router decides whether a call is worth it, local small model and external large model, no agent, token budget. | [ADR-015](adr/ADR-015.md), NFR-18 |
| C4 and 4+1 views | Context and container views added, plus a table of views. | [architecture](architecture.md), [c4-context](diagrams/c4-context.puml), [c4-container](diagrams/c4-container.puml) |
| Business alignment and stakeholders | Product owner and cluster platform added as stakeholders; a framing section. | [specification](project-specification.md) |

ADR-011, ADR-013 and ADR-014 are **proposed**; they take effect once the authors confirm them (ADR-015 and ADR-016 were accepted in revision 4). Two points in the lecture notes were not adopted as written: the figure for "99.9 % availability" per year in the notes is wrong (it is about 8.8 hours, not 1.5 days), and we use the corrected value; and we did not use the group-project and exam tabs, which were not part of the supplied file.

## Revision 4: decisions approved by the authors

The authors approved the recommended option for each of six decisions. Seven topics were worked through; the table says what changed.

| Topic | Decision | What we changed | Where |
| --- | --- | --- | --- |
| Router: call a model or not | Rules with a value score compared with an estimated cost (option A) | Four-step router (hard rules, value score, cost estimate, required value by mode), examples, metrics and a three-way routing experiment (run D); new FR-21 | [AI architecture](ai-architecture.md), [ADR-015](adr/ADR-015.md) |
| Harness engineering | Documented as one map | A table of every harness part with component, requirements, ADR, test and metric | [AI architecture](ai-architecture.md) |
| Agent yes or no | No agent; compare with a fixed workflow and an agent (option A) | New ADR with a criteria table and the triggers for a later review | [ADR-016](adr/ADR-016.md) |
| Tracing to requirements | Stakeholder to metric chain (option A) | Test identifiers V-01 to V-23, an evidence table for all 41 requirements, gaps found and closed (NFR-02, NFR-07, router, review queue, cache, probe) | [Traceability](traceability.md), [verification plan](verification-plan.md) |
| Stakeholder importance | Influence, interest, priority and conflict rules (option A) | Identifiers S-01 to S-09, priorities P1 to P3, rules R1 to R3 and a conflict table | [Specification](project-specification.md) |
| Behaviour from price and CO2 | Table of changes per signal (option A) | One table that follows each signal change through modes, router, jobs, placement and metrics | [Carbon adaptation](carbon-adaptation.md) |
| Demonstration thresholds | Left as proposals | No change | [Carbon adaptation](carbon-adaptation.md) |

## Revision 5: a working event bus

The authors asked for Kafka to be functional. ADR-012 is now accepted and the event bus is implemented: three topics with keys, partitions and retention; events with a validated schema; a producer with `acks=all` and idempotence; consumers with manual commit, idempotent handlers, a processed-events table, retry and a dead-letter topic; a pull path that repairs lost events; Kubernetes manifests, a docker-compose file and a GitHub workflow. 30 tests pass without a broker. The tests against a real broker, the demonstration on Kafka and the manifests on a cluster could not be run in our environment and remain to be run. See [event-bus.md](event-bus.md).

## Revision 6: synchronisation with the supplied diagrams

The authors supplied a use-case diagram and six sequence diagrams and asked for a two-way synchronisation with the project. The audit, the decisions and the results are in [sync-report.md](sync-report.md). In short: the project already contained more detailed versions of import, analysis and the carbon behaviour and was kept; the missing budget and brand constraints with alternatives (FR-22) and the server-side price watch with in-app alerts (FR-06, ADR-017, proposed) were implemented in code, diagrams and documents; two supplementary sequences (SQ-01, SQ-02) were added; one conflict (unavailable carbon signal) is left to the authors. 68 automated tests pass without a broker.

## What remains open

The application, the deployment, the pipeline beyond the documentation check, and all measurements are still future work. Thresholds, the candidate forecast model and the energy estimation method are proposals that the implementation and the evaluation must confirm.
