# Integration of Technical Architecture Review (v1)

This document records which recommendations from the supplied **Review Smart Shopping Technical Architecture** were integrated into Assignment 1. It is a design update, **not an implementation report**.

| Review topic | Updated decision | Where documented |
| --- | --- | --- |
| Narrow product catalog | Laptop-only MVP; seed at least 10 product variants and three sample retailers | `project-specification.md` |
| Store trust score | Excluded until verified third-party evidence is available | `project-specification.md` |
| Email and push alerts | Excluded from MVP because no accounts and subscription/notification system are planned | `project-specification.md` |
| Carbon "Eco Mode" | Replace simplistic reduced polling with simulated grid-intensity time shifting and persisted deadlines | `kubernetes-design.md`, ADR-004 |
| Search filters | Brand, model, min/max price and price ordering only for MVP | FR-01, FR-02 |
| Evidence-based Buy/Wait | 30-day reference delta plus optional stored seven-day trend, with plain-English reasons | FR-05, FR-07, ADR-006 |
| Missing/stale forecast | Show prices and history, with warning or rules-only / Insufficient Evidence advice | ASUC-02, ASUC-03, ADR-006 |
| Carbon measurement | Estimate kWh/gCO2e and compare matched immediate-run baseline with shifted schedule | NFR-10, verification plan |
| PostgreSQL entities | Products, retailers, price observations, forecast runs and job execution logs | `data-model-api.md` |
| REST contract | `/products`, `/products/{id}/insights`, split `/health/live` and `/health/ready`, private `/metrics` | `data-model-api.md` |
| Kubernetes | Independent API/UI Deployments, batch CronJobs, persistence, config/secret and monitoring | `kubernetes-design.md`, ADR-005 |

## Important corrections to the review

1. **Database outage is not covered by forecasting fallback.** The API can continue showing stored prices if the **forecast worker** fails but PostgreSQL remains reachable; it cannot do so during a total database outage without an additional replicated cache/snapshot. The MVP does not claim this.
2. **A deadline guarantees an attempt, not successful completion.** Forecast freshness (95% within 24 h) is a measurable target, not a certainty if the worker, database or dataset fails.
3. **Lower emissions are not automatic.** Deferral can shift a job into a lower-intensity interval, but energy overhead, retries and workload completion must be measured against a controlled immediate-run baseline.
4. **An observed price delta is not a verified merchant discount claim.** The 30-day reference uses a disclosed comparison method and data-quality requirements.
5. **"Production specification" is treated as proposed.** The architecture is an Assignment 1 design; deployments, endpoints, replicas, performance and carbon outcomes have not been verified.
6. **Kubernetes CronJob only triggers work.** The carbon controller must explicitly perform policy evaluation and persist decisions. `concurrencyPolicy: Forbid` alone does not prevent duplicate work after retries; DB idempotency is required.

Review source: `v1_Review_Smart_Shopping_Technical_Architecture.pdf` (nine pages), supplied with the project materials. The review contains illustrative schematics; editable PlantUML versions matching the revised proposal are in `docs/diagrams/`.
