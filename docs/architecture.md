# Smart Shopping - Architecture overview

## Architecture objectives

The proposed MVP covers only laptops. It preserves a quick shopper experience while handling slower price imports and CPU-intensive forecast refreshes in background jobs. The read path and background path do not share request-time compute. Scheduled work may adapt to a simulated carbon-intensity signal, subject to a strict *attempt-to-execute-by-deadline* policy and measurable freshness SLOs.

## Logical modules

- **React SPA:** laptop search, retailer price comparison, history, stored predictions and explained advice.
- **FastAPI API:** request validation, catalog/price queries, discount evidence and recommendation response.
- **Discount Analyzer:** derives a product's reference-price delta from valid comparable historical observations.
- **Recommendation Policy:** separates deterministic advice from the forecasting adapter; returns `INSUFFICIENT_EVIDENCE` when required evidence is weak.
- **Price Import CronJob:** CSV/approved API validation, provenance preservation and PostgreSQL upsert.
- **Carbon-Aware Forecast CronJob:** persists due jobs, uses intensity signal, checks deadline override, runs an existing forecast adapter and records executions/energy.
- **PostgreSQL:** products, retailers, price observations, forecast runs and job logs.
- **Observability:** planned Prometheus/Grafana, request/job/carbon metrics and logging.

## Runtime flows

1. **Interactive insights:** Shopper -> React -> FastAPI -> PostgreSQL observations and latest forecast -> Discount/Recommendation -> JSON with provenance/staleness -> UI. Missing forecasts do not trigger costly synchronous inference.
2. **Ingestion:** CronJob -> approved CSV/data source -> validate -> unique-key upsert -> metrics.
3. **Carbon-aware refresh:** CronJob -> job claim and intensity/deadline evaluation -> execute or defer -> existing forecast adapter -> forecast and job log -> metrics.

## Views and editable UML

- [Shopper use-case diagram](diagrams/use-case-shopper.puml) and [operational use-case diagram](diagrams/use-case-operations.puml).
- [Shopper sequence](diagrams/sequence-shopping.puml) and [carbon-aware sequence](diagrams/sequence-carbon-aware.puml).
- [Logical component model](diagrams/component-model.puml).
- [Kubernetes deployment](diagrams/deployment-kubernetes.puml).
- [Optional data class model](diagrams/class-model.puml) and [carbon policy activity](diagrams/carbon-policy-activity.puml).

## Architectural boundaries

A Use Case Diagram models actors and goals, not physical placement. The Component Diagram models application responsibilities. The Deployment Diagram specifies the proposed Kubernetes Deployments, Services, CronJobs and database storage. All diagrams are proposals, not infrastructure evidence.

## Key refinements from the architecture review

- Narrow the catalog to laptops; only simple brand/model/price filters in the MVP.
- Remove merchant trustworthiness scores and price alert subscriptions; neither is supportable without new sources/accounts.
- Keep 7-day predictions **pre-computed** and freshness-labelled.
- Use deterministic, transparent buy/wait/insufficient-evidence advice instead of unqualified AI certainty.
- Preserve a durable 24-hour forecast job deadline and avoid misrepresenting high-carbon deferral as guaranteed emissions savings.
- Add explicit PostgreSQL schema, REST API contract, resource guards and a baseline sustainability experiment.

Full API schema: [Data Model and API](data-model-api.md). Kubernetes/policy details: [Kubernetes Design](kubernetes-design.md).
