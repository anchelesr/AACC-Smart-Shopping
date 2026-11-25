# Traceability

The matrices connect stakeholders and requirements to use cases, components, decisions and checks. They are meant to be checked in review: every requirement should have at least one component, and every ADR should be driven by at least one requirement.

## Requirements to design

| Requirement | Priority | Use case | Significant use case | Main components | ADR |
| --- | --- | --- | --- | --- | --- |
| FR-01 Find and compare offers | Must | UC1 | - | Catalog Query, Shopping API | 001, 010 |
| FR-02 Price evidence | Must | UC2 | ASUC-01 | Price Evidence | 002, 010 |
| FR-03 Stored forecast | Must | UC2 | ASUC-01 | Forecast Service | 003, 006, 008 |
| FR-04 Explainable advice | Must | UC2 | ASUC-01 | Advice Engine | 006 |
| FR-05 Side-by-side comparison | Should | UC1 | - | Shopping API, Catalog Query, Price Evidence | 001 |
| FR-06 Shortlist and price watch | Should | UC1, UC2 ext. | - | Shopper Client, Watch Monitor, Shopping API | 017 |
| FR-07 Freshness and provenance | Must | UC2 | ASUC-01 | Shopping API, Forecast Service | 002, 006 |
| FR-08 Assistant explanation | Should | UC2 ext. | ASUC-02 | Assistant Service, LLM Gateway | 007, 016 |
| FR-09 Import and validation | Must | UC3 | ASUC-03 | Price Importer | 002, 005 |
| FR-10 Import report | Should | UC3 | ASUC-03 | Price Importer, Operator Console | 002 |
| FR-11 Energy signal monitoring | Must | UC4 | ASUC-04a | Energy Monitor | 004, 014 |
| FR-12 Operating mode and policy | Must | UC4 | ASUC-04a | Policy Engine, Operator Console | 004 |
| FR-13 Carbon-adaptive behaviour | Must | UC4 | ASUC-04b | Job Scheduler, Model Router, Price Importer, Model Evaluator | 004, 005, 007, 015 |
| FR-14 Refresh under a deadline | Must | UC4 | ASUC-04b | Job Scheduler, Forecast Worker | 004, 005, 008 |
| FR-15 Model evaluation | Should | UC4 | ASUC-04b | Model Evaluator, Forecast Model Adapter | 003, 008 |
| FR-16 Metrics and dashboards | Must | UC4 | ASUC-04b | Telemetry | 005, 014 |
| FR-17 Review queue | Could | UC2 ext. | ASUC-02 | LLM Gateway, Operator Console | 007 |
| FR-18 Energy-aware placement | Should | UC4 | ASUC-04c | Placement Controller, Policy Engine | 013, 005 |
| FR-19 Change notification | Should | UC3, UC4 | ASUC-03, 04b, 04c | Event Bus, Price Importer, Policy Engine, Job Scheduler | 012 |
| FR-20 Drift and live quality | Should | UC4 | ASUC-04b | Model Evaluator, Forecast Worker, Forecast Model Adapter | 008, 011, 014 |
| FR-21 Value- and cost-aware routing | Should | UC2 ext. | ASUC-02 | Model Router, Policy Engine, Trace Log | 007, 015, 016 |
| FR-22 Budget and brand constraints | Should | UC2 | ASUC-01 | Advice Engine, Catalog Query, Shopping API | 006, 010 |
| NFR-01 Performance | - | UC2 | ASUC-01 | Shopping API, Price Evidence, Advice Engine | 001, 006 |
| NFR-02 Freshness | - | UC4 | ASUC-04 | Job Scheduler, Forecast Worker | 004, 006 |
| NFR-03 Deadline | - | UC4 | ASUC-04 | Job Scheduler, Data Store | 002, 004 |
| NFR-04 Fault tolerance | - | UC2 | ASUC-01, 02 | Forecast Service, LLM Gateway | 006, 007 |
| NFR-05 Data integrity | - | UC3 | ASUC-03 | Price Importer, Data Store | 002 |
| NFR-06 Security | - | all | - | Shopping API, LLM Gateway, Policy Engine | 007 |
| NFR-07 Modifiability | - | UC2 | ASUC-01, 02 | Forecast Model Adapter, LLM Gateway | 003, 007, 010 |
| NFR-08 Observability | - | UC4 | ASUC-03, 04 | Telemetry | 005, 014 |
| NFR-09 Scaling | - | - | - | Backend and worker workloads | 001, 005 |
| NFR-10 Sustainability evidence | - | UC4 | ASUC-04 | Job Scheduler, Telemetry, Placement Controller | 004, 013, 014 |
| NFR-11 Assistant groundedness | - | UC2 ext. | ASUC-02 | Output Guardrail | 007 |
| NFR-12 Forecast quality | - | UC4 | ASUC-04b | Model Evaluator | 008 |
| NFR-13 Runtime reconfigurability | - | UC4 | ASUC-04a | Policy Engine, Data Store | 004 |
| NFR-14 AI traceability | - | UC2 ext. | ASUC-02 | Trace Log | 007 |
| NFR-15 Deployability | - | - | - | Pipeline | 009 |
| NFR-16 Mode stability | - | UC4 | ASUC-04a | Policy Engine | 004 |
| NFR-17 Availability | - | UC2 | ASUC-01 | Shopping API, Data Store, Kubernetes workloads | 001, 005, 014 |
| NFR-18 Cost control | - | UC2 ext. | ASUC-02 | LLM Gateway (router) | 007, 015, 016 |
| NFR-19 Event delivery | - | UC3, UC4 | ASUC-03, 04b | Event Bus, consumers | 012 |
| NFR-20 Placement safety | - | UC4 | ASUC-04c | Placement Controller | 013 |

## Requirements to evidence

The full chain is stakeholder (S-nn, see the [specification](project-specification.md)) → requirement → use case → component → ADR (table above) → test (V-nn, see the [verification plan](verification-plan.md)) → metric ([observability](observability.md)). Requirements that have no runtime metric say so; their evidence is a test result or a scan.

| Requirement | Stakeholders | Tests | Metric or other evidence |
| --- | --- | --- | --- |
| FR-01 Find and compare offers | S-01 | V-01, V-03 | `http_request_duration_seconds` |
| FR-02 Price evidence | S-01, S-03 | V-01, V-03 | `http_request_duration_seconds` |
| FR-03 Stored forecast | S-01, S-03 | V-03 | `forecast_age_seconds` |
| FR-04 Explainable advice | S-01, S-03 | V-03, V-04, V-25 | none at runtime (deterministic rules; unit tests V-04) |
| FR-05 Side-by-side comparison | S-01 | V-03 | `http_request_duration_seconds` |
| FR-06 Shortlist and price watch | S-01 | V-03, V-24 | `watch_checks_total` (outcome) |
| FR-07 Freshness and provenance | S-01, S-05 | V-03 | `forecast_age_seconds` |
| FR-08 Assistant explanation | S-01, S-07 | V-16, V-17 | `assistant_calls_total` (guardrail outcome) |
| FR-09 Import and validation | S-05, S-02 | V-02 | `import_records_total` |
| FR-10 Import report | S-02, S-05 | V-02 | `import_records_total` |
| FR-11 Energy signal monitoring | S-02, S-06 | V-06 | `energy_intensity_gco2e_per_kwh`, `electricity_price_eur_per_kwh`, `signal_status` |
| FR-12 Operating mode and policy | S-02 | V-06 | `operating_mode`, `mode_changes_total` |
| FR-13 Carbon-adaptive behaviour | S-02, S-03, S-04 | V-08 | `forecast_jobs_total`, `router_decisions_total` |
| FR-14 Refresh under a deadline | S-01, S-02, S-09 | V-08 | `forecast_jobs_total` (decision), `forecast_age_seconds` |
| FR-15 Model evaluation | S-03, S-01 | V-15 | `forecast_abs_error` |
| FR-16 Metrics and dashboards | S-02 | V-21 | dashboard check: every metric of the catalogue is on a dashboard |
| FR-17 Review queue | S-02 | V-17 | `review_queue_open` |
| FR-18 Energy-aware placement | S-02, S-03, S-08 | V-10 | `placement_decisions_total`, `forecast_job_duration_seconds` (pool) |
| FR-19 Change notification | S-02 | V-11 | `event_consumer_lag` |
| FR-20 Drift and live quality | S-02, S-03 | V-12 | `data_drift_score`, `forecast_abs_error` |
| FR-21 Value- and cost-aware routing | S-02, S-04, S-01 | V-18 | `router_decisions_total`, `router_value_score`, `assistant_estimated_cost_eur_total`, `assistant_estimated_gco2e_total` |
| FR-22 Budget and brand constraints | S-01, S-04 | V-25 | none at runtime (rule tests, V-25) |
| NFR-01 Performance | S-01 | V-05 | `http_request_duration_seconds` |
| NFR-02 Freshness | S-01 | V-08 | `forecast_age_seconds` |
| NFR-03 Deadline | S-01, S-02 | V-08 | `forecast_jobs_total` (decision = deadline) |
| NFR-04 Fault tolerance | S-01, S-02 | V-19 | `assistant_calls_total` (route), readiness probe |
| NFR-05 Data integrity | S-05, S-01 | V-02, V-24 | `import_records_total` |
| NFR-06 Security | S-01, S-02, S-07 | V-23 | none at runtime (scan result, authentication and injection tests) |
| NFR-07 Modifiability | S-03, S-04 | V-15 | none at runtime (stub swap test, dependency check in CI) |
| NFR-08 Observability | S-02 | V-21 | the metric catalogue, trace identifiers |
| NFR-09 Scaling | S-02 | V-20 | replica count from Kubernetes |
| NFR-10 Sustainability evidence | S-03, S-04 | V-09, V-18 | `job_energy_kwh_total`, `job_estimated_gco2e_total`, `assistant_estimated_energy_wh_total`, `assistant_estimated_gco2e_total` |
| NFR-11 Assistant groundedness | S-01, S-03 | V-16 | `assistant_calls_total` (guardrail outcome) |
| NFR-12 Forecast quality | S-03, S-01 | V-15 | `forecast_abs_error` |
| NFR-13 Runtime reconfigurability | S-02 | V-07 | `mode_changes_total`, time-to-effect measured in the test |
| NFR-14 AI traceability | S-02, S-03 | V-17 | `assistant_tokens_total`, trace records |
| NFR-15 Deployability | S-03, S-02 | V-22 | none at runtime (workflow run results) |
| NFR-16 Mode stability | S-02 | V-06 | `mode_changes_total` |
| NFR-17 Availability | S-01, S-04 | V-14 | `availability_probe_success` |
| NFR-18 Cost control | S-04, S-02 | V-13, V-18 | `assistant_token_budget_remaining`, `assistant_tokens_total`, `assistant_estimated_cost_eur_total` |
| NFR-19 Event delivery | S-02 | V-11 | `event_consumer_lag` |
| NFR-20 Placement safety | S-02, S-08 | V-10 | `placement_decisions_total` (outcome) |

### Gaps found and how they were closed

| Gap | Closed by |
| --- | --- |
| NFR-02 (freshness) and NFR-07 (modifiability) had no explicit check | NFR-02 was added to the adaptive-behaviour check (V-08) and NFR-07 to the forecast-evaluation check, with a stub swap and a dependency check |
| The router had no check of its own and no metrics | New check "Router value and cost" and the metrics `router_decisions_total`, `router_value_score`, `assistant_estimated_cost_eur_total`, `assistant_estimated_gco2e_total`, `assistant_token_budget_remaining` |
| The review queue, the cache and the availability probe had no metric | `review_queue_open`, `assistant_cache_total`, `availability_probe_success` added to the catalogue |
| The old "Check" column named only a check type, not a test or metric | Replaced by this table |

Remaining honest limits: five requirements (FR-04, FR-22, NFR-06, NFR-07, NFR-15) have a test but no runtime metric by nature. No requirement has measured evidence yet.

## Stakeholders to requirements

The identifiers and priorities are defined in the [specification](project-specification.md); the list below is generated from the evidence table above.

| Stakeholder | Priority | Requirements they need |
| --- | --- | --- |
| S-01 Shopper | P1 | FR-01, FR-02, FR-03, FR-04, FR-05, FR-06, FR-07, FR-08, FR-14, FR-15, FR-21, FR-22, NFR-01, NFR-02, NFR-03, NFR-04, NFR-05, NFR-06, NFR-11, NFR-12, NFR-17 |
| S-02 System operator | P1 | FR-09, FR-10, FR-11, FR-12, FR-13, FR-14, FR-16, FR-17, FR-18, FR-19, FR-20, FR-21, NFR-03, NFR-04, NFR-06, NFR-08, NFR-09, NFR-13, NFR-14, NFR-15, NFR-16, NFR-18, NFR-19, NFR-20 |
| S-03 Course evaluator | P1 | FR-02, FR-03, FR-04, FR-13, FR-15, FR-18, FR-20, NFR-07, NFR-10, NFR-11, NFR-12, NFR-14, NFR-15 |
| S-04 Product owner | P2 | FR-13, FR-21, FR-22, NFR-07, NFR-10, NFR-17, NFR-18 |
| S-05 Price data provider | P2 | FR-07, FR-09, FR-10, NFR-05 |
| S-06 Energy signal provider | P3 | FR-11 |
| S-07 LLM provider | P3 | FR-08, NFR-06 |
| S-08 Cluster platform | P3 | FR-18, NFR-20 |
| S-09 Time trigger | P3 | FR-14 |

## ADR drivers

| ADR | Decision | Driven by |
| --- | --- | --- |
| 001 | Modular backend, separate batch workers | NFR-01, NFR-09 |
| 002 | PostgreSQL with provenance and durable operational state | NFR-03, NFR-05, NFR-13 |
| 003 | Forecast model behind an adapter | NFR-07, FR-15 |
| 004 | Operating modes from a simulated carbon signal | NFR-02, NFR-03, NFR-10, NFR-13, NFR-16 |
| 005 | Kubernetes resources by lifecycle | NFR-08, NFR-09 |
| 006 | Show forecast age, never serve silent stale advice | NFR-01, NFR-02, NFR-04 |
| 007 | LLM gateway with router, guardrails, memory, cache and trace | NFR-04, NFR-06, NFR-11, NFR-14 |
| 008 | Baseline plus one ready-made candidate behind an evaluation gate | NFR-12, FR-15 |
| 009 | CI/CD with GitHub Actions and GitOps | NFR-15 |
| 010 | Components defined by interfaces and an allowed-to-use specification | NFR-07, course architecture principles |
| 011 | Batch prediction for forecasts, model-as-a-service for the assistant | NFR-01, NFR-02, NFR-04 |
| 012 | Publish-subscribe event bus on top of database state | FR-19, NFR-13, NFR-19 |
| 013 | Two adaptation layers: behaviour and placement | FR-18, NFR-10, NFR-20 |
| 014 | Observability with Prometheus, Grafana, OpenTelemetry and measured energy | NFR-08, NFR-10, NFR-17 |
| 015 | Route by value and cost; small local model, large external model | FR-21, NFR-10, NFR-14, NFR-18 |
| 016 | No autonomous agent: a fixed, bounded workflow | FR-08, FR-21, NFR-06, NFR-18 |
| 017 | Server-side price watch under a pseudonymous device id | FR-06, NFR-05, NFR-06 |
