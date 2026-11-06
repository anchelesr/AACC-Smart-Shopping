# Kubernetes, monitoring and carbon-aware scheduling (planned)

## 1. Deployment mapping

| Component | Kubernetes resources | Reason |
| --- | --- | --- |
| React web UI | `Deployment` (2 replica proposal) and ClusterIP `Service` | Stateless frontend, separate scale from API. |
| FastAPI backend | `Deployment` (2-3 replicas proposal) and ClusterIP `Service` | Stateless read path and HTTP request validation. |
| Ingress | Ingress controller with TLS | External web access and routing. |
| Price importer | `CronJob` (e.g. once daily) | Import from approved local/CSV or API source. |
| Forecast scheduler + worker | CronJob that claims pending jobs and applies policy, optionally creates Jobs | Avoid synchronous forecasting; begin with one short-lived worker to reduce MVP complexity. |
| PostgreSQL 16 | Demo `StatefulSet` + PVC + internal Service; managed production DB preferred | Durable price history/forecasts, with clear caveats about backups and availability. |
| Prometheus, Grafana | Monitoring workloads or hosted deployment | HTTP latency, job and carbon metrics. |
| ConfigMap, Secret | Policy/carbon-simulator configuration, credentials | No plaintext secrets in version control. |

**Controls:** CronJobs should propose `concurrencyPolicy: Forbid`, retry limits, resource requests/limits, non-root containers where feasible, readiness/liveness probes and network-limited internal DB access. `Forbid` does not eliminate duplicates after failure: SQL uniqueness and idempotent state changes remain necessary.

## 2. Carbon-aware decision policy

**Inputs:** Simulated intensity in gCO2e/kWh, current UTC time, job `deadline_at`, product's latest forecast creation time and model-data availability.

**Proposed threshold:** 300 gCO2e/kWh (demonstration config, not an energy industry standard). **Proposed freshness limit:** 24 h. A clock-based deadline is checked before deciding to defer. Job age and forecast age are distinct: storing one per-job due-by timestamp prevents the scheduler from resetting a deadline on each retry.

```
if deadline_reached(job):
    execute_and_record(reason="freshness_deadline")
elif intensity_missing:
    record_signal_failure()
    execute_if_critical_else_retry_without_crossing_deadline()
elif simulated_carbon_intensity <= 300:
    execute_and_record(reason="low_carbon_window")
else:
    persist_deferral_and_next_check(before=job.deadline_at)
```

A job failure cannot be counted as meeting a freshness SLO. A deadline override tries to execute but cannot guarantee successful completion when dependencies are broken. The 95% fresh-forecast target and the no-intentional-past-deadline rule are design-level objectives to verify.

## 3. Energy and carbon estimation

`energy_kWh = average_power_W * duration_seconds / (3600 * 1000)`  
`estimated_gCO2e = energy_kWh * grid_intensity_gCO2e_per_kWh`

The power/energy estimate requires a documented method (e.g. instrument or estimator). Separate **energy savings** from lower grid intensity. Under a fixed workload, deferral can lower emissions even when energy stays similar; overhead and retries may offset gains. Never label unmeasured outcomes as proven reductions.

## 4. Observability and SLO monitoring

Prometheus-compatible telemetry should include API p95 latency, 4xx/5xx, pending/finished/failed/deferred job counts, oldest forecast age, deadline overrides/misses, kWh/job, estimated gCO2e/job and intensity at execution. Grafana panels can compare baseline and carbon-aware runs. The `/metrics` endpoint should not be exposed publicly.

## 5. Graceful failures

- **Forecast unavailable/stale:** serve observed prices and history; show warning and rules-only or insufficient-evidence recommendation.
- **Signal unavailable:** log status and use fail-safe policy; do not defer deadline-critical work.
- **Price import unavailable:** retain existing verified observations and label their age.
- **PostgreSQL unavailable:** API returns a dependency error unless a separately designed replicated cache/snapshot provides readable historical data. This is not guaranteed in the minimal architecture.
