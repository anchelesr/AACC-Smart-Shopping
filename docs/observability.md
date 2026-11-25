# Observability, monitoring and energy measurement

The course separates two ideas: **monitoring** asks *is something wrong?* with predefined metrics, thresholds and reactive alerts; **observability** asks *why is it wrong?* and needs instrumentation that lets us follow one request across components. "If you don't monitor, you don't know" is especially true here, because carbon savings are an outcome to measure, not a property of the design (NFR-10). This document defines what we instrument, how it is shown and how we measure energy. It is a design; nothing here has run yet.

## Tooling ([ADR-014](adr/ADR-014.md))

| Purpose | Tool | Note |
| --- | --- | --- |
| Metrics | Prometheus (pull from `/metrics` of annotated pods; Pushgateway for short-lived Jobs) | Short-lived jobs end between scrapes, so they push their metrics before exit. |
| Dashboards and alerts | Grafana with Prometheus as the data source | Dashboards are exported as JSON and kept in Git. |
| Traces | OpenTelemetry instrumentation with a trace backend (Jaeger or Grafana Tempo) | One trace id per request; also stored in the assistant trace and the job logs. |
| Logs | Structured JSON with the trace id | A log stack (Loki or ELK) is optional. |
| Energy | Kepler (pod-level energy metrics to Prometheus) and CodeCarbon (Python code, for worker jobs) | See the section on energy. |

## Metric catalogue

Types follow the Prometheus meaning: a **counter** only goes up, a **gauge** goes up and down, a **histogram** groups measurements into buckets (durations). Labels are bounded sets only (no laptop id, session id or free text), because every label value multiplies the number of time series.

| Metric | Type | Labels | Answers |
| --- | --- | --- | --- |
| `http_request_duration_seconds` | Histogram | route, status | NFR-01: p95 latency of the read path. |
| `forecast_age_seconds` | Gauge (oldest, p95) | - | NFR-02: how fresh are forecasts. |
| `forecast_jobs_total` | Counter | decision (run, defer, deadline), mode | NFR-03: deferrals and deadline overrides. |
| `forecast_job_duration_seconds` | Histogram | mode, pool | Speed on the standard and the eco pool. |
| `operating_mode` | Gauge | mode (1 for the active one) | Mode timeline. |
| `mode_changes_total` | Counter | from, to, reason | NFR-16: flapping. |
| `energy_intensity_gco2e_per_kwh`, `electricity_price_eur_per_kwh`, `renewable_available` | Gauge | source | The signals themselves. |
| `signal_status` | Gauge | signal, status (ok, missing, stale) | Sensor health. |
| `placement_decisions_total` | Counter | target pool, outcome | Placement changes and skipped ones. |
| `job_energy_kwh_total`, `job_estimated_gco2e_total` | Counter | mode, method (estimate, measured) | NFR-10: energy and emissions. |
| `assistant_calls_total` | Counter | route, model class, guardrail outcome | Route shares by mode. |
| `assistant_tokens_total` | Counter | direction, model class | Token budget (a separate budget item). |
| `assistant_estimated_energy_wh_total` | Counter | model class | Estimated assistant energy. |
| `router_decisions_total` | Counter | route, reason, mode | FR-21: why each route was chosen. |
| `router_value_score` | Histogram | intent | FR-21: distribution of the value score. |
| `assistant_token_budget_remaining` | Gauge | - | NFR-18: tokens left today. |
| `assistant_estimated_cost_eur_total` | Counter | model class | NFR-18: estimated fees and electricity cost. |
| `assistant_estimated_gco2e_total` | Counter | model class | NFR-10: estimated emissions of model calls. |
| `assistant_cache_total` | Counter | result (hit, miss), kind (exact, memory) | Cache and memory effect. |
| `review_queue_open` | Gauge | - | FR-17: flagged exchanges waiting for the operator. |
| `watch_checks_total` | Counter | outcome (checked, alerted, already_alerted, stale, not_reached, reset) | FR-06: what the scheduled price check did (the code counts `watch_checked` and the other outcomes). |
| `availability_probe_success` | Gauge | probe (ready, insights) | NFR-17: synthetic probe every minute. |
| `import_records_total` | Counter | result (accepted, rejected, unchanged) | NFR-05, data quality. |
| `forecast_abs_error` | Histogram | model | Live error once prices arrive. |
| `data_drift_score` | Gauge | shape (sudden, gradual, incremental, recurring) | Drift ([AI architecture](ai-architecture.md)). |
| `event_consumer_lag` | Gauge | topic, consumer | NFR-19: events not yet processed. |
| `events_published_total` | Counter | topic, result (ok, failed) | FR-19: failed publishes are repaired by the pull. |
| `events_consumed_total` | Counter | group, result (handled, duplicate, retried, dead) | NFR-19: duplicates and dead letters (the code counts `handled`, `duplicate`, `retried`, `dead` and `publish_failed`). |

Pods carry the standard annotations `prometheus.io/scrape`, `prometheus.io/path` and `prometheus.io/port`; `/metrics` is not exposed publicly (NFR-06).

## What the model pipeline must watch

The course names four artifacts worth monitoring for ML, because each is a handover between two transformations: **raw inputs** (price batches), **features** (the cleaned daily series), **predictions** (stored forecasts) and **accuracy** (realised versus forecast price). Our dashboards show all four, because a fault introduced in one step appears in the artifact after it.

## Dashboards per audience

| Audience | Dashboard | Content |
| --- | --- | --- |
| Operator | Operations | Mode timeline with signals, deferrals and deadline overrides, placement, import quality, review queue size, signal health. |
| Engineer | Service health | Latency histogram, error rate, readiness, resource use, event consumer lag. |
| Sustainability (and evaluator) | Energy | kWh and estimated gCO2e per mode, immediate versus adaptive run, pool comparison. |
| AI quality | Assistant and forecast | Route shares, guardrail failures, tokens, template fallback rate, live forecast error, drift score. |

Aggregates hide problems, so the panels can be sliced (by mode, route, pool, model class); a single average error would hide, for example, a broken promotion period.

## Alerts

Alerts have a policy, a channel and a description with a first action, and there are few of them, to avoid alert fatigue and dashboard rot:

| Alert | Condition | First action |
| --- | --- | --- |
| Forecasts too old | p95 forecast age above 24 h for 30 minutes | Check the job log and the scheduler; the deadline should have forced a run. |
| Signal stale | No valid sample for more than the stale limit | Check the provider and the Energy Monitor; the system already runs as GREEN. |
| Mode flapping | More than four mode changes per hour | Review thresholds and hysteresis; use an override. |
| Guardrail failures high | Template fallback share above an agreed limit for an hour | Inspect the review queue and the prompt version. |
| Event lag | Consumer lag above a limit for 10 minutes | Check the consumer; the pull path keeps the system correct meanwhile. |
| Readiness failing | `/health/ready` fails | Check the database. |

## Tracing

One trace id is created at the Shopping API (or at the job start) and passed through the modules, the gateway and the event headers. The assistant trace record and the job execution log store the same id, so a slow or wrong answer can be followed from the shopper request to the route chosen, the model call and the guardrail result. Traces show the time budget of each step, which is how we locate the bottleneck of NFR-01.

## Measuring energy

We use two methods and report both, because one is an assumption and the other may be unavailable:

1. **Estimate:** `energy_kWh = average_power_W * duration_s / 3,600,000`, with a documented power per worker class, and a token-based factor per model class for the assistant. This works everywhere and is labelled *estimate*.
2. **Measurement:** Kepler exports pod-level energy to Prometheus (restart Prometheus after installing it so it scrapes the new endpoint); CodeCarbon measures Python code and pushes the result through the Pushgateway when a short-lived Job ends. Both can fall back to an estimation model in virtualised environments such as a local cluster, so the report must say which source produced each number. We have to verify this on our cluster before quoting any measured value.

The comparison of the standard and the eco pool uses the same job on both pools: execution time (from the histogram), energy and estimated gCO2e at the intensity and price of that moment, to show the trade-off between speed and energy use.

## Availability and the SLO

Availability is `MTTF / (MTTF + MTTR)`. The proposed service-level objective is an availability of 99.5 % per month for the shopper read path (NFR-17), which allows about 3.6 hours of downtime in a 30-day month; 99.9 % would allow about 43 minutes and 99.99 % about 4 minutes. A synthetic probe against `/health/ready` and one insights request every minute provides the measurement. A low MTTR is the practical lever: rolling updates, `kubectl rollout undo` and the GitOps revert make repair quick, while a rare failure with a long repair would still miss the objective.
