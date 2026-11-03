# Verification and evolution plan (future milestones)

All thresholds are targets, not measured results.

| Check | Evidence / how to test |
|---|---|
| FR-01..03 | Seed 3 retailers and 10 products; query/search/filter test, source timestamps visible |
| FR-04..05 | Ingest 30+ days of observations, verify time ordering, missing data, 30-day reference calculation |
| FR-06..07 | Fixtures with forecast valid / stale / absent; no unsupported recommendation |
| FR-08 | Import same CSV twice, no duplicate observations; invalid rows quarantined/logged |
| FR-09 | Simulated LOW/HIGH profile; controlled job queue and max freshness deadline verify RUN/DEFER/OVERRIDE |
| NFR-01 | Load-test 20 req/s product insights, record p95 < 2 s goal |
| NFR-02..03 | Simulate 48h of scheduler ticks; max age and violation log; explicit deadline override |
| NFR-10 | Same job set under immediate and carbon-aware policy, compare kWh, estimated gCO2e, latency and violations |
| Kubernetes | `kubectl get deploy,svc,cronjob`; observe run, retry, volumes; scale API replicas |
| CI/CD | Workflow lints/validates tests, builds container images, deploys to test cluster |
| Observability | Metrics dashboard with HTTP p95, error rate, forecast age, job decisions, carbon estimate |

Experiment interpretation must report all baseline assumptions: prices, hardware/energy measurement limits, carbon-signal provenance, and user-facing freshness conditions.
