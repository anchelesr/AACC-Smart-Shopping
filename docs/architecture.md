# Architecture overview

## Views
- `use-case.puml`: external use cases and stakeholders (not a workflow or deployment map).
- `sequence-shopping.puml`: shopper-facing analysis and recommendation; stored forecast vs missing/stale.
- `sequence-carbon-aware.puml`: asynchronous scheduled refresh, carbon policy, freshness deadline.
- `component-model.puml`: logical modules and their dependencies.
- `deployment-kubernetes.puml`: proposed container and Kubernetes resource mapping.
- `class-model.puml`: optional conceptual storage/data classes.

## Design principle
One responsibility per component; keep forecasting adapter separate from discount/recommendation business logic, reflecting course SE4AI architectural-quality material (SRP, cohesion, separation of concerns). Choose a modular API plus an independently deployable batch worker; do not introduce unnecessary microservices for a small demo.

## Logical building blocks
| Component | Responsibility | Interface / state |
|---|---|---|
| Web UI | Search, compare, history chart, recommendation | REST; no DB credentials |
| REST API | Product endpoints, validate requests, orchestrate modules | stateless HTTP JSON |
| Catalog/Price Queries | Retrieve observed latest/history per product and retailer | SQL read |
| Discount Analyzer | Compare observed current and historical reference | deterministic Python function |
| Forecast Reader | Fetch latest stored precomputed forecast and age | SQL read |
| Recommendation Engine | buy / wait / insufficient evidence and explanations | pure business logic |
| Price Import CronJob | Ingest source and normalize data | CSV/approved API, upsert SQL |
| Forecast Batch CronJob | Read due work; carbon policy; invoke prediction adapter | scheduled SQL + simulated signal |
| Forecast Adapter | existing model/baseline inference, no training | input time series -> forecast + metadata |
| PostgreSQL | catalog, retailers, observations, forecasts, job state | persistent; schema migrations |
| Metrics stack | Collect API/job/energy/carbon/status metrics | Prometheus and dashboard |

## Proposed API contract (illustrative, not implemented)
- `GET /products?q=...&sort=price_asc`: product search.
- `GET /products/{id}/insights`: offers, price history, discount evidence, latest stored forecast, recommendation, timestamps/status.
- `GET /health`: liveness; internal readiness checks.
- `GET /metrics`: monitoring endpoint; restrict operational exposure.

## Data pipeline and reliability
1. Scheduled CSV/authorized API importer validates and upserts price observations with uniqueness by product/retailer/observation time/source.
2. Catalog/price queries use normalized observations; confidence depends on history availability.
3. Forecasting jobs operate asynchronously and write versioned forecasts; API reads existing values without synchronous heavy compute.
4. Policy on signal: intensity <= configured threshold -> run, high -> defer only if deadline allows; absent signal -> documented fallback (run deadline-critical, log reason).
5. Each run records job ID/status; duplicate CronJob execution may occur and is handled with unique work claims / idempotency. ConcurrencyPolicy: Forbid is proposed but DB idempotency is still needed.

## Kubernetes mapping (planned, not deployed)
- `frontend` Deployment + ClusterIP Service, exposed via Ingress.
- `api` Deployment + ClusterIP Service; replicas are stateless.
- `price-import` CronJob.
- `forecast-batch` CronJob (runs policy and forecasting in same short-lived worker initially); `concurrencyPolicy: Forbid`, with `resources.requests/limits`.
- PostgreSQL StatefulSet + PVC for demo; production would prefer managed Postgres with backups.
- Prometheus/Grafana or lightweight equivalent for metrics.
- ConfigMap: policy thresholds / simulator profile; Secret: DB credentials; readiness/liveness and resource budgets.

**Why not cloud/local boundary in Use Case UML?** A UML use case describes actors/goals. Runtime placement is specified by the deployment view.

## Carbon measurement and experiment
- Carbon signal: deliberately simulated time series in gCO2e/kWh, not a real-time claim.
- Energy estimate: capture measured/estimated workload kWh and derive operational emissions `gCO2e = kWh * gCO2e/kWh` with recorded methodology. CodeCarbon may help estimate energy; intensity is applied consistently to both experiment arms.
- A/B experiment: same workload with immediate-run policy vs carbon-aware deferral, record actual job completion time, forecast age, p95 response latency, energy per forecast, estimated gCO2e/forecast, and deadline/SLO violations.
- Distinguish reduced carbon intensity from reduced **energy**; deferment alone does not guarantee lower energy use or absolute emissions.
