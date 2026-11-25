# Sources and provenance

**Directly provided course sources (not web research):**
1. `course-overview.html`, slides "The final project", "Assignments and final submission", "Example projects", and "Grading components": architecture, ADRs and UML, no model training or fine-tuning, Kubernetes deployment, CI/CD, carbon signal, SLO and observability.
2. Svogor, I., *AI Architecture and Cloud Computing*, lecture notes v1.3, 26 September 2026, Ch. 13 "Operational Efficiency and Carbon Awareness": time-shifting, measurement and performance trade-offs.
3. `SE4AI_Architectural_Quality_V702.pdf`: cohesion and single responsibility, DRY, acyclic dependencies, software blood types (A and T), separating models from business logic, separating normal processing from exception handling, the environmental impact of architecture.
4. `SE4AI_The_Importance_of_Architecture_V703.pdf`: architecture as components plus the allowed-to-use specification, component diagrams with usage relationships.
5. `SE4AI_Architecture_of_Machine_Learning_Powered_Applications_V707.pdf`: training and inference phases, data pipeline stages (collection, integrity, cleaning, imputation, normalization, feature engineering), output guardrails.
6. `Se4AI_Architecture_of_LLM_Powered_Applications_V708.pdf`: the harness around the model call, model gateway, router and cascading, guardrails and loop engineering, memory, exact and semantic caching, logging, human in the loop, prompt architecture, challenges of the LLM interface.
7. `SE4AI_Introduction_V720.pdf`: the course rule to document AI use (prompt, model, comparison of versions) and that end-to-end responsibility stays with the authors.
8. `SE4AI_Requirements_Structuring_V720.pdf`: functional versus non-functional requirements.
9. `session-4.html`, "Kubernetes: Deployments and Services" and related virtualization materials.

10. Student lecture notes "Poznámky ACC", sessions 1 to 7 (67 pages, supplied by the authors in revision 3): energy awareness and placement, publish-subscribe and Kafka, Prometheus, Grafana and tracing, availability and consistency, data engineering, deployment of ML systems, LLM harness and routing, C4 and 4+1 views, CI practice. The notes are secondary material; they contain at least one numeric error (availability per year), which we corrected, and they name tools (Electricity Maps, Kepler, CodeCarbon, Kafka, Prometheus, Grafana, OpenTelemetry) that we cite only as named there. Their "group project" and "exam" parts were not included in the file.

**Works quoted in the course slides and used here only through them:**
- Huyen, C., *Building A Generative AI Platform*, 2024 (model gateway, router, caching, guardrails).
- Huyen, C., *AI Engineering: Building Applications with Foundation Models*, O'Reilly Media, 2025 (logging, routing).
- Kästner, C., *Machine Learning in Production: From Models to Products*, The MIT Press, 2025 (separating models from business logic, data integrity).
- Martin, R. C., *Clean Architecture*, Pearson, 2017 (definition of architecture).

**Notation:** Object Management Group, *Unified Modeling Language Specification*, version 2.5.1 (component, interface, assembly connector, sequence and activity notation). Diagrams are written in PlantUML.

**Design proposals, not stated by the course:** FastAPI, PostgreSQL and React as example technologies, the product category, 2 s p95 at 20 RPS, the 24-hour freshness window, the seven-day horizon, the operating-mode thresholds (300 and 450 gCO2e/kWh), hysteresis margin, sampling and evaluation intervals, cache lifetimes, worker concurrency per mode, advice-rule thresholds, the router rules, guardrail checks, the baseline and candidate-model approach, the pipeline stages, module and endpoint naming and the worker topology. They require verification during implementation.

**Not independently verified by us:** the content of `course-overview.html` and the lecture notes in items 1, 2, 9 and 10 is cited as supplied by the authors; this revision was prepared from the feedback text and from excerpts of the slides in items 3 to 7. Items 8 and 9 are cited as in revision 1 and were not re-read for revision 2.
