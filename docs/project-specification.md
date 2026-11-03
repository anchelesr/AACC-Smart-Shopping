# Project specification - Smart Shopping

## 1. Identity and objective
Smart Shopping: Price Analysis, Discount Prediction & Carbon-Aware Recommendations.
Repository URL: **https://github.com/anchelesr/AACC-Smart-Shopping**
This is a **proposed system**, not an assertion that the code, datasets or cloud resources already exist.

The system helps a shopper compare product offers, understand price history, assess whether a discount is exceptional, and view an evidence-based buy-now / wait recommendation. Non-urgent forecasting runs are scheduled in response to a **simulated grid-carbon-intensity signal**, subject to a freshness deadline.

## 2. Stakeholders and boundaries
Primary: Shopper. Secondary: System Operator (sets policy and inspects metrics), data provider (CSV/approved API), simulated carbon-signal provider, course evaluator. A scheduled event triggers non-interactive jobs. No checkout, payments, inventory reservation, delivery footprint, or real claims about retailer trustworthiness are included.

## 3. MVP features
| ID | Functional requirement | Acceptance idea |
|---|---|---|
| FR-01 | Search the product catalog | Search finds indexed item by name or category |
| FR-02 | Filter and sort product search results | Price range and sort order affect displayed results |
| FR-03 | Show product details and compare offers from multiple retailers | Amount, currency, retailer and observation time present |
| FR-04 | Show a time-series chart of historical observed prices | Chart displays time, amount and price source |
| FR-05 | Calculate discount evidence from historical prices | Shows delta from 30-day reference; missing history is explicit |
| FR-06 | Present a stored seven-day price forecast when credible data is available | Includes model/version, time generated, uncertainty or caveat |
| FR-07 | Explain a buy-now / wait recommendation | Reasons use prices, discount evidence and available forecast |
| FR-08 | Import validated price observations at scheduled intervals | Deduplication and source provenance recorded |
| FR-09 | Apply carbon-aware policy to nonurgent forecast refreshes | Low intensity executes; high defers; due deadline overrides |
| FR-10 | Expose operational and sustainability metrics | Jobs run/deferred, latency, forecast age, energy and gCO2e estimate |

Out of MVP: authenticated accounts, shopping checkout, retailer reviews/quality scoring, push/email alerts, real-time scraping, personalized ranking, shipping or embodied-product footprint. These can be future extensions.

## 4. Nonfunctional properties - **proposed test targets**
| ID | Quality | Proposed acceptance target |
|---|---|---|
| NFR-01 | API responsiveness | p95 GET product insights <= 2 s, tested at 20 requests/second with seeded demo data |
| NFR-02 | Forecast freshness | 95% of eligible catalog products have a forecast <= 24 h old during demo workload; show age or unavailability for exceptions |
| NFR-03 | Carbon policy | When signal > 300 gCO2e/kWh defer jobs without a deadline conflict; never violate 24 h maximum job age in the controlled experiment |
| NFR-04 | Availability and fallback | Failed forecast/signal must not prevent browsing current/historical prices; user sees status |
| NFR-05 | Data integrity | Every observation retains product ID, retailer ID, timestamp, currency, source; invalid/duplicate rows are logged/filtered |
| NFR-06 | Security | HTTPS externally; no credentials in Git; least-privilege app and DB credentials; no payment data |
| NFR-07 | Maintainability | Model adapter can be changed without modifying REST endpoint or recommendation policy |
| NFR-08 | Operability | Prometheus-compatible metrics for HTTP, job states, forecast freshness, estimated carbon; structured logs |
| NFR-09 | Scalability | Stateless API replicated independently from scheduled workers under Kubernetes |
| NFR-10 | Sustainability evidence | Benchmark energy (kWh), estimated gCO2e/forecast, defer rate and SLO violations against an immediate-run baseline |

Targets above are **design proposals for later testing**, not proven results. 300 gCO2e/kWh, 24 h, 7 days and 20 RPS are configurable demonstration parameters.

## 5. Data and AI assumptions
- Focus on a small, fixed electronics catalog for a reproducible student demonstration.
- Data input: authorized provider or CSV with historical price observations; synthetic data labeled as synthetic.
- Normalization includes timestamps, currency policy, retailer-product linkage, duplicate removal, invalid values, missing-history handling.
- Forecasts generated **off the request path**, persisted with model/version, creation time, target date, and a quality/status flag.
- Do **not** train/fine-tune a custom model (Course Overview ground rule). Choose an existing forecasting implementation or simple non-trained rule-based baseline; demonstrate model interface design, not model training.
- Discount evidence is a comparison to historical reference, not a legally verified seller promotion. Negative advice is explained as an estimate, not certainty.
- Carbon intensity is simulated in gCO2e/kWh, and carbon-estimates concern the **compute workload**, not manufacturing/shipping emissions.

## 6. Key quality trade-off
The interactive path returns stored insights immediately; the batch path sacrifices some freshness when carbon intensity is elevated. Enforce the 24-hour freshness deadline before allowing deferral. Actual savings are hypothetical until measured.
