# Architecturally significant use cases

These scenarios are significant because they drive system boundaries, reliability, data integrity, runtime placement, SLOs and monitoring. All describe the **proposed** Smart Shopping MVP.

## ASUC-01 - Import and validate laptop price observations

- **Primary actor/trigger:** Scheduled Price Import CronJob; approved price CSV/API as data provider.
- **Goal:** Maintain reliable timestamped laptop price observations from multiple retailers.
- **Preconditions:** Laptop catalog and retailer mapping exist; data source location is configured.
- **Main success flow:** 1. Schedule starts importer. 2. Importer retrieves observation batch. 3. Validate product/retailer, currency, amount, date and provenance. 4. Normalize timestamps/currencies (without inventing conversion rates). 5. Upsert unique observations to PostgreSQL. 6. Report counts, rejects and failures.
- **Alternative flows:** Bad rows are quarantined/reported; duplicate imports have no duplicate effect; source is unavailable -> error recorded and subsequent retry; unsupported currency -> exclude from comparisons.
- **Postconditions:** Valid observations persisted exactly once per defined unique key, with provenance; failures observable.
- **Architecture impact:** Trust boundary at input, schema, idempotency, scheduled jobs, data quality.
- **Trace:** FR-03/04/08, NFR-05/08, ADR-002/005.

## ASUC-02 - View price, history and forecast

- **Primary actor:** Shopper.
- **Goal:** Obtain the Past/Present/Future overview for a selected laptop.
- **Preconditions:** Laptop exists; offers and historical prices may be incomplete.
- **Main success flow:** 1. Shopper opens laptop. 2. Frontend calls `GET /products/{id}/insights`. 3. API retrieves current offers and 30-day observations. 4. Discount analyzer derives reference-price evidence if valid. 5. API reads the most recent stored seven-day forecast, model ID and generated timestamp. 6. API returns a single response and frontend renders it.
- **Alternative flows:** No valid forecast -> forecast unavailable and explicit caveat; forecast age >24h -> mark stale and do not present as fresh; inadequate history -> no unsupported discount percentage; DB unavailable -> meaningful error unless an explicit read-cache/snapshot exists.
- **Postconditions:** All price/forecast values are labelled by status and time.
- **Architecture impact:** Query latency, model decoupling, API contract and fail-soft behavior.
- **Trace:** FR-01..06; NFR-01/04/07; ADR-001/003/006.

## ASUC-03 - Generate explainable buy/wait recommendation

- **Primary actor:** Shopper.
- **Goal:** Receive an understandable decision grounded in available price evidence.
- **Preconditions:** Valid current offer exists; history and forecast are optional.
- **Main success flow:** 1. API gathers current price, 30-day median reference and usable stored seven-day trajectory. 2. Deterministic recommendation policy evaluates evidence. 3. It returns Buy Now / Wait / Insufficient Evidence with 1-3 reasons and metadata. 4. UI distinguishes observed facts from estimated forecasts.
- **Alternative flows:** Stale/missing forecast -> historical rules only with caution or Insufficient Evidence; missing 30-day history -> Insufficient Evidence; contradictory weak indicators -> Insufficient Evidence.
- **Postconditions:** Recommendation is explainable, not guaranteed.
- **Architecture impact:** Business logic outside the forecasting model; testable, replaceable adapters.
- **Trace:** FR-05..07; NFR-04/07; ADR-003/006.

## ASUC-04 - Carbon-aware scheduled refresh with freshness guarantee

- **Primary actor/trigger:** Kubernetes CronJob; System Operator oversees; simulated carbon-intensity feed provides values.
- **Goal:** Shift deferrable forecast work to lower-intensity periods without exceeding freshness deadlines.
- **Preconditions:** Due jobs persisted with next-run/due-by timestamps; last completion time known; simulator configured.
- **Main success flow:** 1. CronJob claims pending task idempotently. 2. Reads simulated intensity (gCO2e/kWh), job age and due-by. 3. When <=300, runs. 4. When >300 and ample time remains, records defer reason and next evaluation. 5. When due-by is reached, runs regardless of intensity. 6. Forecast adapter computes/stores versioned seven-day result. 7. Monitor records completion, duration, energy estimate and gCO2e.
- **Alternative flows:** Missing signal -> run deadline-critical work, log cause and use defined conservative retry behavior for other work; insufficient prices -> persist failed/insufficient-data outcome, do not invent forecast; worker retry -> idempotent state transition; overlapping CronJobs -> `concurrencyPolicy: Forbid` plus DB guards.
- **Postconditions:** Every job is runnable/deferred/failed/completed with timestamps; no planned deferral past due-by in the controlled test.
- **Architecture impact:** Job lifecycle, carbon/quality trade-offs, schedulability, concurrency, metrics.
- **Trace:** FR-06/09/10; NFR-02/03/08/10; ADR-004/005/006.
