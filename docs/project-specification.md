# Smart Shopping - Project specification

**Course:** AI Architecture and Cloud Computing (AACC)  
**Authors:** Linda Vincelová and Angelika Rischáneková  
**Repository:** https://github.com/anchelesr/AACC-Smart-Shopping  
**Status:** Architecture proposal; the application and its measured results are not yet available

## Project goal

We chose laptops for the first version because prices vary enough to make historical comparison interesting, but the catalog can still remain small and testable. A shopper should see where the numbers came from rather than trust an unexplained bargain label. The interface therefore brings together historical observations (*Past*), current offers (*Present*) and stored seven-day estimates (*Future*). Its recommendation is a short, transparent **Buy Now**, **Wait** or **Insufficient Evidence** message.

Behind the scenes, non-urgent forecast refreshes can be delayed according to a simulated electricity carbon-intensity signal. The delay must not be allowed to silently make the displayed forecast too old.

## System boundary and stakeholders

**Shopper:** searches, filters, examines laptop prices and evidence, reads recommendation.  
**System operator:** configures carbon policy, inspects batch results and metrics.  
**Scheduled trigger:** starts price-import and forecast-refresh workflows.  
**Price data provider:** approved API or CSV import, possibly explicitly synthetic for demonstration.  
**Simulated carbon feed:** provides gCO2e/kWh observations.  
**Course evaluator:** reviews design, executable proof and measured comparisons.

### MVP boundary

Ten or more demonstration laptop models, at least three sample retailers and 30+ days of timestamped price history per relevant case are proposed as a **test fixture**, not real-life retailer coverage. Brand, model and price filtering are in scope; sophisticated specification facets are not. No accounts, checkout, payment processing, price-alert push/email, merchant trust ranking, unauthorised live scraping or product manufacturing/shipping carbon footprint are included.

## Functional requirements

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-01 | Search laptop catalog | Query by product name, brand or model; return matching catalog items. |
| FR-02 | Filter and sort | Filter by price boundaries; sort by price ascending or descending. |
| FR-03 | Compare retailer offers | Show each observed active retailer offer, currency and observed-at timestamp. |
| FR-04 | View historical prices | Plot at least 30 days of sourced observations, where test data supports it. |
| FR-05 | Evaluate discount evidence | Compare current price with a clearly defined 30-day reference; declare insufficient observations when applicable. |
| FR-06 | View seven-day forecast | Read a **stored** forecast; show model identifier, generated-at time, forecast horizon, uncertainty caveat and freshness state. |
| FR-07 | Obtain explainable advice | Explain Buy Now / Wait; return Insufficient Evidence if the inputs cannot justify either. No guarantees of future prices. |
| FR-08 | Import price observations | Scheduled worker validates, normalizes and idempotently upserts observations with source information. |
| FR-09 | Apply carbon-aware scheduling | With a 300 gCO2e/kWh **proposed** threshold, defer only non-urgent forecasts; force deadlines at 24h, with a missing-signal fallback. |
| FR-10 | Publish operational/carbon metrics | Export request latency, job states, forecast age, energy-estimate methodology and estimated gCO2e. |

### Price and recommendation semantics

For the MVP, one possible explicit 30-day product reference is the **median of daily lowest valid offers** for a matching product over the last 30 days. The current discount-evidence delta is `(current_lowest_price / reference_price - 1) * 100%`. This is a design policy to validate during implementation, **not** a claim that the seller advertised a legally compliant discount. The comparison only proceeds if sufficient observations exist and currencies are comparable. Recommendation rules combine this delta and the direction of the stored seven-day forecast; results carry short, evidence-based explanations. When a forecast is missing/stale, use rule-only information with a conspicuous caveat or return Insufficient Evidence.

## Non-functional properties - proposed targets

| ID | Quality attribute | Proposed acceptance target |
| --- | --- | --- |
| NFR-01 | Performance | `GET /products/{id}/insights` p95 latency <= 2.0 s under 20 requests/s on seeded demo data. |
| NFR-02 | Freshness | >=95% of active eligible catalog laptops have a forecast no older than 24h in the target scenario; flag exceptions. |
| NFR-03 | Carbon job deadline | No controlled-test prediction job is intentionally deferred beyond its specified 24h maximum interval; enforce override. |
| NFR-04 | Fault tolerance | A forecast worker/model/signal outage does not prevent viewing stored current and past prices. Database outages require a separately provisioned read cache/snapshot; **not guaranteed** by the database-only MVP. |
| NFR-05 | Data integrity | Reject invalid rows; enforce unique source observations (product, retailer, timestamp, provenance) and idempotent retry. |
| NFR-06 | Security | TLS at edge; no plaintext secrets in repository; least-privilege DB and K8s access. |
| NFR-07 | Modifiability | Swap forecasting adapter without changing the shopper REST contract or recommendation policy. |
| NFR-08 | Observability | Request latency, forecast age, job outcome and estimated kWh/gCO2e visible in monitoring. |
| NFR-09 | Scaling | API replicas independent of scheduled batch workers; defined resource requests and limits. |
| NFR-10 | Sustainability evidence | Controlled immediate-run vs carbon-aware experiment records energy, gCO2e, deferrals, forecast age and deadline errors. |

## Data and AI constraints

- Price observations contain product, retailer, amount, currency, observation time and source provenance.
- The system reads pre-computed forecasts; the interactive HTTP request never launches an expensive forecast calculation.
- The forecasting interface wraps an existing ready-to-use model/baseline; **no custom training or fine-tuning** is part of this course MVP.
- Input quantities, currencies and timezones must be normalized; currency conversion is not silently applied to incomparable offers.
- Forecasts are estimates with timestamp and limitations, not guaranteed purchasing advice.
- Operational gCO2e estimation concerns the server-side **compute workload**, not the environmental impact of producing or shipping laptops.
