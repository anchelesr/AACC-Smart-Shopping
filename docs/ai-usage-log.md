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
