# Architecturally significant use cases (ASUC)

The following are architecturally significant because they drive persistence, component boundaries, asynchronous processing, consistency, SLO enforcement and measurement. All cases are design proposals.

## ASUC-01 - Ingest and validate price observations
- **Actor / trigger:** Scheduled trigger; external authorized data source or local CSV.
- **Precondition:** Data source and product/retailer IDs configured.
- **Main flow:** trigger -> importer reads rows -> validate source, currency, amount, timestamp -> deduplicate -> upsert into PostgreSQL -> record counts/errors.
- **Alternatives:** source offline -> retry next scheduled run; bad row -> quarantine/log, not inserted; duplicate -> idempotently skipped.
- **Postcondition:** Valid observations available for historical analysis and forecasting.
- **Why significant:** external data trust boundary; data quality; idempotency and provenance; scheduled compute.
- **Trace:** FR-03, FR-04, FR-08; NFR-05, NFR-08; ADR-002, ADR-005.

## ASUC-02 - View current prices, historical evidence and forecast
- **Primary actor:** Shopper.
- **Precondition:** Product exists in catalog.
- **Main flow:** shopper opens product -> API reads retailer observations/history -> calculates 30-day discount evidence -> reads latest stored seven-day forecast -> returns data and generated-at timestamp.
- **Alternatives:** no forecast -> show prices + "forecast unavailable"; stale forecast -> label age; missing history -> hide discount confidence / report insufficient history.
- **Postcondition:** Shopper can distinguish observed data from estimated values.
- **Why significant:** latency and fail-soft behavior, data consistency and model isolation from synchronous request path.
- **Trace:** FR-03..FR-06; NFR-01, NFR-04, NFR-07; ADR-001, ADR-003, ADR-006.

## ASUC-03 - Produce explainable buy / wait recommendation
- **Primary actor:** Shopper.
- **Precondition:** Observed price exists; historical and forecast data may vary.
- **Main flow:** shopper requests recommendation -> API gathers current offers and historical reference -> retrieves stored forecast if valid -> policy evaluates buy / wait / insufficient evidence -> returns reasons and warnings.
- **Alternatives:** confidence insufficient -> show "insufficient evidence" rather than unsupported action; no forecast -> optional rules-only indication explicitly marked.
- **Postcondition:** Recommendation shows provenance, timestamp and non-guarantee.
- **Why significant:** business rules must not be inside model; separate recommendation policy allows model substitution and testing.
- **Trace:** FR-05, FR-06, FR-07; NFR-04, NFR-07; ADR-001, ADR-003.

## ASUC-04 - Refresh forecasts under carbon and freshness constraints
- **Actor / trigger:** Scheduled Kubernetes CronJob, with simulated Carbon Signal provider.
- **Precondition:** Due products and their next deadlines are persisted; carbon-signal source available or can fail.
- **Main flow:** scheduled controller reads pending work -> reads intensity -> apply policy -> if intensity <= threshold, run; otherwise defer while within 24 h deadline -> worker uses existing forecasting adapter -> persist timestamped forecast and metrics.
- **Alternatives:** when carbon signal missing, run deadline-critical work and follow documented safe fallback for other jobs; insufficient data -> record failure without fabricated forecast; job retries are idempotent.
- **Postcondition:** Every job is complete/deferred/failed with reason; deadlines are monitored.
- **Why significant:** asynchronous worker lifecycle, job ownership, reliability, energy/carbon measurement, Kubernetes workload design.
- **Trace:** FR-06, FR-09, FR-10; NFR-02, NFR-03, NFR-08..NFR-10; ADR-004, ADR-005.
