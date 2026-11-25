# Architecturally significant use cases

These four scenarios cover the decisions that matter most for our laptop-price comparison system: reliable observations, a responsive product page, understandable advice and scheduled forecasts. They describe planned behaviour, not an implemented application.

## ASUC-01 — Import laptop price observations

**Actor / trigger:** Scheduled price-import CronJob using an approved CSV or API source.

**Goal and normal flow:** Keep dated, attributable observations from several retailers. The scheduled importer reads a batch, checks the exact laptop variant, retailer, currency, positive amount, observation time and source, then normalizes supported values and upserts them using a stable source identity. It records the number of accepted and rejected observations.

**Preconditions:** Catalog entries, retailer mappings and data-source configuration are available.

**Postconditions:** Valid observations are stored without duplicate source identities; import results are logged.

**Traceability:** FR-03, FR-04, FR-08; NFR-05, NFR-08; ADR-002, ADR-005.

## ASUC-02 — View a laptop's price evidence

**Actor:** Shopper.

**Goal and normal flow:** Show current offers, price history and the latest stored forecast together. The shopper opens a laptop in the React interface, which requests `GET /products/{id}/insights`. The API reads timestamped offers and history from PostgreSQL, calculates the reference-price comparison when enough data exists, adds the stored seven-day forecast and returns its generation time, model identifier and freshness status.

**Preconditions:** The requested laptop exists. Historical observations and forecasts may be incomplete.

**Postconditions:** The interface distinguishes observed prices from forecasts, shows their dates and identifies unavailable or stale estimates.

**Traceability:** FR-01–FR-06; NFR-01, NFR-04, NFR-07; ADR-001, ADR-003, ADR-006.

## ASUC-03 — Explain whether to buy or wait

**Actor:** Shopper.

**Goal and normal flow:** Offer advice that can be checked against the available evidence. The recommendation service compares a valid current price with the defined 30-day reference and, when usable, a stored seven-day trend. It produces **Buy Now**, **Wait** or **Insufficient Evidence**, together with short reasons that distinguish observations from estimates.

**Preconditions:** A valid current offer exists. Historical data and forecasts are optional inputs.

**Postconditions:** The recommendation includes its basis and does not imply guaranteed future prices.

**Traceability:** FR-05–FR-07; NFR-04, NFR-07; ADR-003, ADR-006.

## ASUC-04 — Refresh forecasts under a freshness deadline

**Actor / trigger:** Forecast-scheduling CronJob, observed by the system operator, with a simulated carbon-intensity feed.

**Goal and normal flow:** Schedule non-urgent forecasts in lower-intensity periods without indefinite delays. The controller claims a due job, reads the simulated intensity and its persisted deadline, then executes it if the intensity is at or below the configured threshold or the deadline has arrived. Otherwise it records a deferral and the next check. The worker stores the versioned forecast and its execution metrics.

**Preconditions:** Pending work, due-by timestamps, last-completion state and simulated-intensity configuration are available.

**Postconditions:** A run or deferral is recorded with timing, reason and status; the scheduler does not deliberately defer a job beyond its deadline.

**Traceability:** FR-06, FR-09, FR-10; NFR-02, NFR-03, NFR-08, NFR-10; ADR-004, ADR-005, ADR-006.
