# Smart Shopping

**Price Analysis, Discount Prediction & Carbon-Aware Recommendations**

University project for **AI Architecture and Cloud Computing (AACC)**.

**Repository:** [AACC-Smart-Shopping](https://github.com/anchelesr/AACC-Smart-Shopping)  
**Project status:** Architecture and requirements specification (Assignment 1). The application and Kubernetes deployment are planned, not yet implemented.

## Overview

Smart Shopping is a proposed web application that helps users decide **where and when to buy products**. It compares retailer prices, analyzes historical price changes, identifies potentially attractive discounts and uses an existing forecasting component to estimate future prices.

The application provides a simple recommendation: **Buy Now**, **Wait**, or **Insufficient Evidence**. Its background forecasting jobs are designed to respond to a simulated electricity carbon-intensity signal, while respecting prediction freshness requirements.

## Main Features

- **Product search and filtering:** Find products and narrow results.
- **Retailer price comparison:** Compare currently observed offers.
- **Price history and discount analysis:** Explore price trends and evaluate discounts against historical values.
- **Price forecasting:** Display available estimates of future prices with timestamps and uncertainty information where supported.
- **Shopping recommendation:** Explain whether current price evidence supports buying now or waiting.
- **Carbon-aware scheduling:** Run or defer non-urgent forecasting jobs according to simulated carbon intensity and a maximum freshness deadline.
- **Monitoring:** Observe service latency, job status, forecast freshness and estimated operational carbon emissions.

These features describe the **intended system**; they should not be interpreted as completed functionality.

## System Architecture

The proposed design separates fast user-facing requests from scheduled data processing and AI prediction tasks. The backend coordinates product and pricing logic, but the forecasting component and carbon-aware scheduler have their own responsibilities.

| Component | Purpose |
| --- | --- |
| Web Frontend | Search, product details, price charts and recommendations |
| Backend API | Handles requests and coordinates application services |
| Price Analysis | Compares offers, historical prices and discount evidence |
| Forecasting Component | Produces price forecasts via a replaceable adapter |
| Recommendation Engine | Generates explained Buy Now / Wait / Insufficient Evidence outputs |
| Carbon-Aware Scheduler | Decides when non-urgent forecast refreshes may execute |
| PostgreSQL | Stores product data, price observations, forecasts and jobs |
| Monitoring | Collects operational and carbon-related metrics |

Further explanation: [Architecture Overview](docs/architecture.md).

## UML Diagrams

The following **six diagrams are the same images embedded in the latest editable project DOCX**. PlantUML source files are linked below each image, so the diagrams can be updated later.

### 1. Shopper Use Cases

Shows the main user goals, such as finding products, viewing price history, comparing offers, reviewing predictions and receiving buying recommendations.

![Shopper-facing UML use case diagram](docs/diagrams/previews/use-case-shopper.png)

PlantUML: [Use Case Diagram](docs/diagrams/use-case.puml)

### 2. Operational Use Cases

Shows the system's scheduled import, forecast refresh, carbon-aware decision making and monitoring interactions.

![Operational UML use case diagram](docs/diagrams/previews/use-case-operations.png)

PlantUML: [Use Case Diagram source](docs/diagrams/use-case.puml)

### 3. Shopping Recommendation Sequence

Shows how the application retrieves product prices and stored forecasts to provide a shopping recommendation, including a fallback when a forecast is unavailable.

![Shopping recommendation UML sequence diagram](docs/diagrams/previews/sequence-shopping.png)

PlantUML: [Shopping Sequence](docs/diagrams/sequence-shopping.puml)

### 4. Carbon-Aware Forecasting Sequence

Shows how a scheduled forecasting task is either executed or deferred using the carbon-intensity signal and freshness constraints.

![Carbon-aware forecasting UML sequence diagram](docs/diagrams/previews/sequence-carbon-aware.png)

PlantUML: [Carbon-Aware Sequence](docs/diagrams/sequence-carbon-aware.puml)

### 5. Component Diagram

Shows the logical components, their responsibilities and interactions with the database and external data sources.

![Smart Shopping UML component diagram](docs/diagrams/previews/component-model.png)

PlantUML: [Component Model](docs/diagrams/component-model.puml)

### 6. Kubernetes Deployment Concept

Shows the proposed deployment structure with continuously running services, scheduled jobs, persistent data and monitoring.

![Kubernetes deployment UML diagram](docs/diagrams/previews/deployment-kubernetes.png)

PlantUML: [Kubernetes Deployment](docs/diagrams/deployment-kubernetes.puml)

## Kubernetes and Carbon-Aware Computing

The system is designed for future containerized deployment:

- **Deployments and Services** for the frontend and API.
- **CronJobs / Jobs** for scheduled price imports and forecast refreshes.
- **Persistent storage** for historical prices and generated forecasts.
- **Prometheus and Grafana** for monitoring and evaluation.

Non-urgent forecasting may be deferred when simulated carbon intensity is high, provided the predicted information remains acceptably fresh. Deadline-critical work must not be postponed indefinitely. The final implementation will compare immediate execution with carbon-aware scheduling using energy estimates, carbon intensity and freshness metrics.

**Scope of carbon metrics:** The estimate concerns the application's computations, not the environmental footprint of product manufacturing or shipping.

## Architecturally Significant Use Cases

| ID | Use Case | Architectural Significance |
| --- | --- | --- |
| ASUC-01 | Import and validate price observations | Data quality, ingestion and persistence |
| ASUC-02 | View prices, history and forecasts | API responsiveness, caching and graceful fallback |
| ASUC-03 | Generate shopping recommendations | Separation of decision logic and AI predictions |
| ASUC-04 | Carbon-aware forecast refresh | Background execution, scheduling, monitoring and freshness |

Detailed descriptions: [Significant Use Cases](docs/significant-use-cases.md).

## Architecture Decisions

Six Architecture Decision Records (ADRs) document the main choices and trade-offs:

- [ADR-001 — Modular API and batch workers](docs/adr/ADR-001.md)
- [ADR-002 — Relational storage and provenance](docs/adr/ADR-002.md)
- [ADR-003 — Forecasting adapter and fallback](docs/adr/ADR-003.md)
- [ADR-004 — Carbon-aware time shifting](docs/adr/ADR-004.md)
- [ADR-005 — Kubernetes and monitoring](docs/adr/ADR-005.md)
- [ADR-006 — Stored forecasts and freshness](docs/adr/ADR-006.md)

## Proposed Technologies

| Area | Technology |
| --- | --- |
| Frontend | React |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Data Processing | Pandas |
| Forecasting | Existing forecasting model or documented baseline |
| Containerization and Deployment | Docker, Kubernetes |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus, Grafana |
| UML | PlantUML |

These are **proposed technologies**, not an assertion that all have been implemented.

## Documentation

- [Project Specification](docs/project-specification.md)
- [Architecture Overview](docs/architecture.md)
- [Significant Use Cases](docs/significant-use-cases.md)
- [Verification Plan](docs/verification-plan.md)
- [References](docs/references.md)

## References

This architecture proposal is based primarily on the AACC course overview and lecture notes, together with the provided SE4AI requirements and architecture materials. Source details are listed in [References](docs/references.md).
