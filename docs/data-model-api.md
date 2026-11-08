# Relational data model and API contract (proposed)

## PostgreSQL schema

The project review proposes PostgreSQL 16 for the 10-laptop/3-retailer reproducible demonstration. Keys below are **design-level specifications** and need implementation migrations and integration tests.

| Entity | Key columns | Constraints and purpose |
| --- | --- | --- |
| `products` | `id` PK, `sku` UNIQUE | Laptop brand, model, optional JSONB specs; fixed demonstration catalog. |
| `retailers` | `id` PK, `name` UNIQUE | Retailer identity and default currency. No unverified trust score. |
| `price_observations` | `id` PK, `product_id` FK, `retailer_id` FK, `observed_at`, `source_provenance` | Uniqueness `(product_id, retailer_id, observed_at, source_provenance)`; positive amount, currency and source. |
| `forecast_runs` | `id` PK, `product_id` FK | Seven predicted day/price pairs or JSONB array, model version, `generated_at`, status and caveat. |
| `job_execution_logs` | `id` PK, `job_key` UNIQUE | Start/end, status, deferral reason, intensity, estimated kWh and gCO2e, deadline/next retry. |

Consider PostgreSQL constraints and idempotency under duplicate import or repeated Kubernetes CronJob execution. Recommended indexes include `price_observations(product_id, observed_at DESC)`, `forecast_runs(product_id, generated_at DESC)` and pending-job deadlines. Forecast data and job state must be durable; do not hold critical job ownership only in a process-memory variable.

Laptop variants need a stable SKU; otherwise a comparison could mix different CPU/RAM configurations. Only valid, comparable prices enter discount calculations. Timestamp fields use UTC; the displayed UI may convert to local time.

## API

The proposed HTTP API uses FastAPI, JSON, Pydantic validation and an OpenAPI 3.1-compatible contract to be finalized in implementation.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/products?q=...&sort=...&min_price=...&max_price=...` | Matches laptop catalog rows; sorts and filters; includes lowest known offer and retailer count where available. |
| GET | `/products/{id}/insights` | Returns `present`, `past`, `future`, `recommendation` with source/timestamp/freshness metadata. |
| GET | `/health/live` | Process liveness; no heavy DB query. |
| GET | `/health/ready` | Readiness; may fail if required dependencies such as PostgreSQL are unreachable. |
| GET | `/metrics` | Prometheus metrics; **internal access only**. |

The supplied review used a single `GET /health` endpoint; we split it into `live` and `ready` to avoid conflating process liveness with dependent service readiness. This is a **recommended refinement**, not a claim of an implemented endpoint.

### Example JSON response shape (illustrative, not real prices)

```json
{
  "product_id": 1,
  "present": {"best_offer": {"retailer": "Sample Store", "price": 899.0, "currency": "EUR", "observed_at": "2026-11-01T09:00:00Z"}},
  "past": {"reference_30d": 950.0, "reference_method": "median_of_daily_lowest_valid_offer", "discount_delta_pct": -5.37, "history": []},
  "future": {"horizon_days": 7, "model_id": "existing-adapter-v1", "generated_at": "2026-11-01T02:00:00Z", "status": "example-fresh", "prices": [], "caveat": "Model estimates are uncertain"},
  "recommendation": {"action": "INSUFFICIENT_EVIDENCE", "reasons": ["Example response only"]}
}
```

If the forecast worker fails, the API returns `future.status=unavailable` and an explicit rules-only recommendation or no recommendation; prices remain visible if PostgreSQL responds. Without a separate verified read cache or snapshot, a full database outage cannot satisfy the stronger availability claim made in the review PDF.
