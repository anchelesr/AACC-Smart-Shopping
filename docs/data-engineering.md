# Data engineering

The course treats data handling (preprocessing, storage and pipelines) as a graded project component and stresses that more than 80 % of AI project failures trace back to data that does not fit its purpose. This document records our data decisions in the order the lectures use: sources, formats, data model, storage, dataflow, processing, and the protection of the evaluation from leakage.

## Sources

| Source | Kind | What it gives us | Risk and handling |
| --- | --- | --- | --- |
| Price Data Provider (approved CSV or API) | Third-party data | Offers per laptop variant and retailer | Untrusted text and values: validated, normalised and kept with provenance; no unauthorised scraping. |
| Demonstration fixture | Synthetic data | 10+ laptop variants, three sample retailers, 30+ days of prices | Labelled as synthetic everywhere; limits what the forecast evaluation can show (see below). |
| Energy Signal Provider | Third-party or simulated data | Carbon intensity, electricity price, renewable flag | Simulator by default, Electricity Maps as an optional live source; range and timestamp validated. |
| Shopper input | User input | Search text, questions to the assistant | Length and scope checks; retailer and product text treated as data, never as instructions. |
| System-generated data | System-generated data | Job logs, traces, metrics, forecasts, samples | Structured, versioned, used for evaluation and for the energy comparison. |
| User behaviour (clicks, sessions) | Not collected | - | Not needed for the goals; avoids personal data (GDPR). Session ids are anonymous and short-lived. |

## Formats

| Place | Format | Why |
| --- | --- | --- |
| Import files and API payloads | CSV or JSON as received | Human-readable, so a reviewer can check a rejected batch by eye. |
| Raw layer | The batch stored unchanged with a checksum (text or JSONB) | Reproducibility: any observation can be re-derived and a parser fix can be replayed. |
| Operational store | Relational rows | Structured entities with relationships and integrity rules. |
| Payload snapshots, traces, policy parameters | JSONB columns | Semi-structured, read as a whole, no joins needed. |
| Evaluation exports | Optional Parquet | Column-oriented, compact and fast for backtests over many series; not human-readable, so it is a derived copy and never the source of truth. |
| Events | Small JSON messages with a schema | Notification only; no bulk data travels on the bus. |

## Data model and storage

We use a relational model (PostgreSQL) because the data is structured, entities are related (product, retailer, observation, forecast, job), uniqueness and referential rules matter (NFR-05) and a transaction must either complete or not happen (ACID: atomic, consistent, isolated, durable), for example when a job lease is taken or a policy version is stored. NoSQL stores were not chosen: the schema is stable, the volume is small (about 900 observations for the fixture; even 10,000 laptops at three retailers and 30 days would be about 900,000 rows) and a document or graph model would add nothing. A data lake or warehouse is not justified at this size; the OLTP and the occasional analytical query (backtests, dashboards) run on the same database. The workload split is stated explicitly so that the decision can be revisited when the volume changes ([ADR-002](adr/ADR-002.md)).

## Layers: raw, validated, derived

We borrow the medallion idea (bronze, silver, gold) to keep the pipeline explainable:

| Layer | Content | Where | Created by |
| --- | --- | --- | --- |
| Raw (bronze) | Batches as received, with checksum and source | `raw_batches` | Price Importer |
| Validated (silver) | Observations that passed validation, normalised to decimal amount, UTC time and currency code, unique on `(product, retailer, observedAt, provenance)` | `price_observations` | Price Importer |
| Derived (gold) | Daily lowest valid offer, 30-day reference, forecasts, drift scores | views and `forecast_runs`, `drift_checks` | Price Evidence, Forecast Worker, Model Evaluator |

## Dataflow

| Flow | Pattern | Reason |
| --- | --- | --- |
| Price import | Batch (daily job) | Source data changes slowly; the shopper needs yesterday's and today's observations, not milliseconds. |
| Energy signals | Micro-batch (sample every 5 minutes) | The decision rhythm is minutes; a continuous stream adds cost without benefit. |
| Notification of changes | Publish-subscribe (`price.changed`, `mode.changed`) | The producer does not know its consumers; consumers react without polling ([ADR-012](adr/ADR-012.md)). |
| Shopper requests | Synchronous REST | The request path reads stored data only. |
| Forecasts | Batch prediction, results stored and looked up | [ADR-011](adr/ADR-011.md). |

The pub/sub layer carries notifications, not data; the database remains the source of truth, which is why a lost event is harmless (it is repaired by the next pull).

## Cleaning, imputation and quality

- **Validation:** known variant and retailer, ISO currency, positive amount, observation time not in the future; rejected rows are listed with reasons in the import report (FR-10).
- **One value per day:** the lowest valid offer in a comparable currency.
- **Gaps:** up to three missing days are carried forward from the *previous* value; longer gaps make the series ineligible and the job reports `insufficient_data`. Imputation uses past values only (see leakage).
- **Quality metrics** exported per import: accepted, rejected and unchanged counts, share of rejected rows, age of the newest observation.

## Protecting the evaluation from leakage

A model can look excellent in testing and fail in deployment when information from the future or from the test set reaches the training or selection step. We do not train, but we still select between a baseline and a candidate, so the same rules apply:

| Leak | Our rule |
| --- | --- |
| Time | Rolling-origin backtest with chronological splits only; never a random split of days. |
| Scaling and imputation | Statistics and gap filling computed from data before the origin only. |
| Duplicates | Duplicates are removed before the split; the unique observation key prevents them. |
| Groups | Evaluation is per laptop; the same series is never in two folds of one origin. |
| Test set | The last origins are held out for the final comparison and not used to tune the candidate's settings. |
| Synthetic data | The fixture is generated with documented rules; a model that learns the generator would look good. We therefore report that results on synthetic data prove only that the pipeline works. |

Rare events such as promotion days (for example the days around Black Friday) are the cases a forecast most needs to handle and the ones a plain average hides. The report therefore also shows the error on days where the price moved by more than the advice threshold.

## Business alignment and framing

The data decisions follow from the framing in [Project specification](project-specification.md): the forecast takes a 30-day daily series as input, produces seven daily prices as output and minimises the mean absolute error (a regression problem); the assistant takes an evidence payload and a question and produces a grounded explanation.
