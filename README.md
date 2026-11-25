# Smart Shopping

**Price Analysis, Discount Prediction & Carbon-Aware Recommendations**  
*AI Architecture and Cloud Computing (AACC)*

**Authors:** Linda Vincelová · Angelika Rischáneková  
**Repository:** https://github.com/anchelesr/AACC-Smart-Shopping

## What we are building

Buying a laptop involves more than finding the lowest advertised price. The same model may appear in several shops, the price can change from week to week, and a large percentage discount does not necessarily mean that an offer is unusually good. Our project brings those pieces of information together in one place.

Smart Shopping is designed around three views of a laptop's price:

- **Past:** a dated price history and a clearly defined 30-day reference price;
- **Present:** comparable offers from different retailers, with their source and observation time;
- **Future:** a stored seven-day price forecast, including its age and limitations.

The application then gives a short **Buy Now**, **Wait** or **Insufficient Evidence** recommendation. We want that recommendation to be understandable: a shopper should be able to see which price observations and assumptions led to it.

A second part of the project concerns the infrastructure. Instead of recalculating forecasts whenever someone opens a product page, we plan to run them as background jobs. These jobs can be shifted to periods of lower *simulated* electricity carbon intensity, provided the forecast freshness limit is not exceeded.

**Project status:** The architecture and documentation are prepared. The application, Kubernetes deployment and performance/carbon measurements still need to be implemented and tested.

## Scope of the first version

We are deliberately keeping the demonstration small: laptops only, a fixed catalog of at least ten comparable models, three sample retailers and approximately 30 days of price observations. The dataset may contain clearly identified demonstration data. Searches will focus on brand, model and price; we are not building a full e-commerce platform.

User accounts, payments, email alerts, retailer trust scores and unauthorized scraping are **outside** this first version. The carbon estimate covers the application's computations, not laptop manufacturing or shipping.

## Architecture at a glance

We propose a React interface and a modular Python/FastAPI backend. PostgreSQL stores prices, the latest forecast results and background-job status. Scheduled jobs handle price imports and forecast refreshes. The interactive API only reads stored forecasts, so an expensive calculation does not block a shopper's request.

In Kubernetes, the frontend and API are planned as separate Deployments; import and forecasting work as CronJobs/Jobs. Prometheus and Grafana will be used to check response times, job outcomes, forecast age and estimated operational emissions.

### Use cases

The shopper-facing part covers searching laptops, comparing retailer offers, checking price history and requesting advice. A separate operational view covers data import, forecast refresh and monitoring.

![Shopper use-case diagram](docs/diagrams/previews/use-case-shopper.png)

[Shopper use-case PlantUML](docs/diagrams/use-case-shopper.puml) · [Operational use cases](docs/diagrams/use-case-operations.puml)

### Main request sequence

A shopper opens a laptop; the API reads the observations and latest forecast, calculates discount evidence and returns an explained recommendation. If the forecast is missing or too old, the response shows a clear warning rather than pretending the prediction is fresh.

![Shopping insights sequence](docs/diagrams/previews/sequence-shopping.png)

[Sequence source](docs/diagrams/sequence-shopping.puml)

### Component structure

![Component diagram](docs/diagrams/previews/component-model.png)

[Component source](docs/diagrams/component-model.puml)

### Carbon-aware processing and Kubernetes

Our draft policy uses a **300 gCO₂e/kWh** simulated intensity threshold and a **24-hour** maximum deferral window. These are demonstration settings, not established universal thresholds. A deadline override starts the job even when the intensity remains high; this is an attempt to preserve freshness, not a guarantee that the job will succeed. Any claim of lower emissions must be checked against the same workload run without deferral.

![Carbon-aware forecast sequence](docs/diagrams/previews/sequence-carbon-aware.png)

[Sequence source](docs/diagrams/sequence-carbon-aware.puml)

![Proposed Kubernetes deployment](docs/diagrams/previews/deployment-kubernetes.png)

[Deployment source](docs/diagrams/deployment-kubernetes.puml)

Other diagrams: [combined use-case model](docs/diagrams/use-case.puml), [data model](docs/diagrams/class-model.puml) and [carbon policy activity](docs/diagrams/carbon-policy-activity.puml).

## Main design choices

| Area | Our approach | Why it matters |
| --- | --- | --- |
| Backend | One modular API, separate batch workers | Keeps HTTP requests predictable while batch work can be scheduled independently |
| Data | PostgreSQL with source/timestamp keys | Supports reliable comparison and avoids duplicated imports |
| Forecasting | Existing model or baseline behind an adapter | Allows replacement without changing the shopper interface |
| Recommendations | Rules plus evidence, not an opaque score | Users can see why the application suggests waiting or buying |
| Carbon policy | Time-shift non-urgent forecasts with a deadline | Makes sustainability measurable without sacrificing freshness by design |
| Runtime | Kubernetes Deployments, Services and CronJobs | Reflects the different lifecycles of web and batch work |

The rationale, alternatives and limitations are documented in the [six Architecture Decision Records](docs/adr/ADR-001.md).

The supporting documents cover the [requirements](docs/project-specification.md), [significant use cases](docs/significant-use-cases.md), [system architecture](docs/architecture.md), [data and API design](docs/data-model-api.md), [Kubernetes design](docs/kubernetes-design.md), [decision records](docs/adr/ADR-001.md) and [verification checks](docs/verification-plan.md). The [project architecture PDF](Smart_Shopping_Assignment_1.pdf) is included in its latest reviewed layout, with readable tables and full-width heading rules.

## Scope and limitations

The performance target (p95 ≤ 2 seconds at a defined 20 RPS demo load), forecast freshness target and carbon threshold are **test criteria**, not results. A forecasting failure should not prevent display of stored observed prices while the database is available. A complete database outage would require an additional availability mechanism, which is not claimed here.

The design reflects the AACC course material and the technical review of the original concept.
