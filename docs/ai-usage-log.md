# AI usage log

The course expects every exercise to be done with documented AI use: the prompt, the model, and a reflection on what AI did well and badly. The end-to-end responsibility for the result rests with the authors. This log records the use of AI for the revision of the architecture documents. **Entries marked "authors to complete" cannot be filled in by the tool and must be completed by the authors before submission.**

## Entry 1 - Revision 2 of the architecture documents (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5`. The serving model may differ from the configured one, so the exact model should be confirmed by the authors. |
| Task | Revise the specification, use cases, diagrams, ADRs and PDF according to the course feedback on revision 1. |
| Initial prompt (summary) | The reviewer comments were pasted verbatim, with the request to update the repository archive, the architecture and the PDF accordingly and to propose further solutions for approval. |
| Follow-up prompt | The authors approved the proposal ("implement everything") after a written plan that listed decisions on the assistant and router, the forecast model, CI/CD depth, carbon behaviours and the document language. |
| What AI produced | Drafts of the revised specification and requirements, the four use cases and five sequences, the component model and interface catalogue, the carbon operating modes, the AI architecture, the CI/CD design, ADR-004 and ADR-007 to ADR-010, the traceability matrices and the PDF layout. |
| Checks done on the output | All PlantUML files of revision 2 (twelve at that time) compile and were rendered and inspected; message numbers quoted in the text were compared with the rendered sequences; identifiers (FR, NFR, ASUC, ADR) were cross-checked between documents; the documentation workflow logic was run locally on good and broken diagrams. |
| Corrections made during the work | A component-diagram layout that was unreadable was redrawn with assembly connectors; a clipped message in a sequence was fixed; an inconsistency between the deployment view and the component model for the evaluation job was resolved; a claim about dependency direction was corrected. |
| Checks the authors still need to do | Whether the thresholds, windows and intervals are acceptable; which candidate forecast model to use; whether the in-scope features fit the available time; whether the wording matches the authors' own understanding; whether every statement can be defended in the oral presentation. |
| Reflection (what suited AI, what did not) | Authors to complete. |

## Entry 1b - Revision 3: integration of the lecture notes (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5` (serving model to be confirmed by the authors). |
| Task | Take over the points of the lecture notes (67 pages) that matter for this project, plus the authors' own list: router decides whether to call a model, harness engineering, whether an agent is worth it, tracing to requirements, stakeholder importance, behaviour that follows electricity price and carbon. |
| Prompt (summary) | The authors listed the topics, attached the notes and asked to integrate what is important or mentioned about the project and makes sense. The request to take decisions together with the authors was explicitly postponed. |
| What AI produced | Three new documents (data engineering, observability, distribution and dependability), ADR-011 to ADR-015 with status "proposed", the Placement Controller, Event Bus and Local Model Runtime in the component model, ASUC-04c, two C4 views, new requirements FR-18 to FR-20 and NFR-17 to NFR-20, and changes in the existing documents. |
| Checks done on the output | Syntax check of all PlantUML files; identifiers and links compared across documents; message numbers in the text compared with the sequences; availability arithmetic recomputed (one claim in the notes was wrong and was corrected). |
| Open for the authors | Confirm or change ADR-011, ADR-013 and ADR-014; the price thresholds (0.20 and 0.30 EUR/kWh) are demonstration values; whether to keep the event bus and the eco-pool simulation within the available time; reflection on what worked. |
| Reflection (what suited AI, what did not) | Authors to complete. |

## Entry 1c - Revision 4: router, harness, agent, stakeholders, traceability (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5` (serving model to be confirmed by the authors). |
| Task | Carry out a prompt that the authors prepared from their topic list: router decision, harness, agent yes or no, tracing to requirements, stakeholder importance, behaviour from energy price and carbon. |
| Prompt and decisions | The authors' prompt asked for an audit first, then a list of decisions. The tool listed seven decisions with options and a recommendation; the authors replied "do the recommended steps", which we read as approval of options A for decisions 1 to 6; decision 7 (thresholds, Kafka against NATS) stayed a proposal. |
| What AI produced | Router rules with value score and cost estimate, harness map, ADR-015 (rewritten) and ADR-016, stakeholder table with priorities and conflict rules, test identifiers, the evidence table and the signal-change table, new metrics. |
| Checks done on the output | Syntax of the PlantUML files, links, identifier coverage (every requirement has a test), and consistency between documents. |
| Open for the authors | Check that the stakeholder priorities and the router numbers (value points, V of at least 1, 2 and 3, half of the budget for the large model) match your judgement; they are demonstration values. Reflection on what worked. |
| Reflection (what suited AI, what did not) | Authors to complete. |

## Entry 1d - Revision 5: a working event bus (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5` (serving model to be confirmed by the authors). |
| Task | Make the Kafka event bus of ADR-012 functional. |
| Prompt | "Include Kafka so that Kafka is functional" (translated from Slovak). We read it as: implement it, not only describe it; ADR-012 was therefore accepted. |
| What AI produced | The event code and tests in `src` and `tests`, the Kafka manifests, the docker-compose file, the workflow `events.yml` and the document `event-bus.md`. |
| Checks done on the output | 30 automated tests pass; the YAML files parse; a test compares the topics in the deployment files with those in the code. |
| What could not be checked | No container runtime and no access to the Kafka image in the environment, so nothing was run against a real broker. The environment variables of the broker follow the documented settings of the `apache/kafka` image and have to be confirmed by running it. |
| Open for the authors | Run the compose file, the demonstration and the integration tests; record the result in the verification plan (V-11). Decide whether a single broker is enough for the demonstration. Reflection. |
| Reflection (what suited AI, what did not) | Authors to complete. |

## Entry 1e - Revision 6: synchronisation with supplied diagrams (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5` (serving model to be confirmed by the authors). |
| Task | A prepared prompt (audit, plan, implementation, validation) to synchronise the project with a supplied use-case diagram and six sequence diagrams. |
| What AI produced | The audit and decisions in `sync-report.md`, ADR-017, advice, catalog and watch code with tests, two supplementary sequences, changes to six diagrams and to the documents. |
| Checks done on the output | 68 automated tests pass, all diagrams compile and were rendered and inspected, links and identifiers were cross-checked, message numbers were recomputed. |
| Decisions the tool made and the authors must confirm | Server-side watch (ADR-017); keeping the project's behaviour for an unavailable carbon signal; brand list as the only "preference"; no claim about NASA standards because none was identified. |
| Reflection (what suited AI, what did not) | Authors to complete. |

## Entry 1f - Revision 7: replacement of the diagrams (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5` (serving model to be confirmed by the authors). |
| Task | Draw the sequence diagrams in the style of the supplied zip with the project's components, add a communication diagram and a component diagram, redraw the supplied use-case figure so that it fits the project, replace the old diagrams in the repository, README and PDF, and move the comments below the images into the text. |
| What AI produced | The nine PlantUML diagrams `01` to `09`, the generator of the use-case figure, the edits of the documents and `sync-report.md` (section "Revision 7"). |
| Checks done on the output | Syntax check of all PlantUML files, rendering and visual inspection of the images, message numbers in the text recomputed from the sources, links checked. The use-case figure was inspected visually only. |
| Decisions the tool made and the authors must confirm | The three detailed carbon sequences are kept next to the new overview; the content of the new use-case figure (four use cases in four bands, two extensions of UC2); the new sequences are condensed and omit telemetry calls. |
| Reflection (what suited AI, what did not) | Authors to complete. |

## Entry 2 - Comparison required by the course

For each exercise the course asks for three versions and a comparison: (1) done without AI, (2) done with AI and an initial prompt, (3) done with AI and an improved prompt. The tool cannot supply version 1 or the authors' judgement.

| Exercise | Version 1: without AI | Version 2: initial prompt | Version 3: improved prompt | Quality differences and reflection |
| --- | --- | --- | --- | --- |
| Use-case model | Authors to complete | Authors to complete | Authors to complete | Authors to complete |
| Sequence diagrams | Authors to complete | Authors to complete | Authors to complete | Authors to complete |
| Component model | Authors to complete | Authors to complete | Authors to complete | Authors to complete |
| ADRs | Authors to complete | Authors to complete | Authors to complete | Authors to complete |

## Entry 3 - Revision 1

Authors to complete: the tool, model and prompts used for the first revision, if any.

## Entry 4 - Revision 8: implementation of the shopper path and the control loop (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5` (the serving model may differ; the authors should confirm). |
| Task | Implement the REST API and frontend, Carbon Monitor and Policy Engine, Job Scheduler, Forecast Worker and Model Evaluator, Placement Controller, LLM Gateway with router, guardrails and a local model, price import and PostgreSQL, with tests, and update the documents. |
| Prompt (summary) | The authors confirmed the recommended proposals and listed the six areas above. |
| What the tool produced | The modules and tests listed in [implementation status](implementation.md), the PostgreSQL manifest, a workflow, and the documentation changes of revision 8. |
| What was checked by running | The test suite on SQLite and on a real PostgreSQL 16 server, the application over HTTP, and the frontend once in Chromium. Not run: Kafka integration tests, manifests, GitHub workflows, the `kubectl` and model HTTP adapters against real systems. |
| Decisions the tool took (candidate, concurrency, stand-in model, in-process cache, operator token confirmed by the authors on 25 November 2026; the rest not yet reviewed) | The forecast candidate (damped Holt, [ADR-008](adr/ADR-008.md) addendum); concurrency as jobs started per tick; a deterministic stand-in instead of a language model as the default local model; in-process cache and memory; one static operator token; the sixteen differences in [implementation status](implementation.md). |
| Errors found and fixed during the work | A deferral clock of the optional backfill was reset by the mandatory daily import (found by a test, fixed); test expectations that assumed parallel job execution were corrected after the behaviour was reviewed; a repeated identical deferral flooded the job log (deduplicated). |
| Reflection | Authors to complete: what the tool did well and badly, what had to be corrected, and what was changed by hand. |

## Entry 5 - Revision 9: final project, deployment and operation (25 November 2026)

| Item | Record |
| --- | --- |
| Tool and model | Claude, configured as `claude-sonnet-5-5` (the serving model may differ; the authors should confirm). |
| Task | From the screenshots of the final-project assignment: make the system deployable and operable (container, Kubernetes, CI/CD, observability, carbon metrics, dynamic redeployment and model exchange) and prepare the video script. The authors first asked for a prompt for this work, then asked the tool to execute it phase by phase on the existing code. |
| Prompt (summary) | A phased prompt (environment check, running system, CI/CD, observability, carbon metrics, dynamic behaviour, video, close-out) written by the tool at the authors' request; the authors chose Kustomize, the Kubernetes REST API for the controller, Ollama with a small model and labelled estimates. |
| What the tool produced | The files listed in the [synchronisation report](sync-report.md) (revision 9). |
| What was checked by running | Tests on SQLite and PostgreSQL 16, three real processes, the container image on a local base, `kustomize`, `kubeconform`, `promtool`, `actionlint`, `yamllint`, `shellcheck`, the shell helpers against a live server, the carbon experiment twice. Not run: anything on a cluster, GitHub Actions, GHCR, Ollama. |
| Decisions the tool took without confirmation | Roles as separate Deployments instead of Jobs and CronJobs; the worker as the movable workload; metrics derived from the database at scrape time; a demonstration-only controllable signal; the model names `qwen2.5:1.5b` and `qwen2.5:0.5b`; moving `postgres.yaml`; reporting the experiment for two traces. The authors have not reviewed these. |
| Errors found and fixed during the work | See the sync report: a thread-bound event store (fixed), a shadowed function (fixed), an experiment that first compared different numbers of jobs and mixed the effect of timing with the assumed pool power (reported separately now), a start time of the experiment before the last seeded observation (fixed). |
| Finding that is unfavourable to the design | With the default simulator the adaptive scheduler emits about 11 % more per job than immediate execution (0.7 % higher carbon intensity at job start), because the renewable window lies on the carbon peak. It is reported, not hidden. |
| Reflection | Authors to complete: what the tool did well and badly, what had to be corrected, and what was changed by hand. |

