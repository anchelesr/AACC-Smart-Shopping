# Smart Shopping - Project specification

**Course:** AI Architecture and Cloud Computing (AACC)  
**Authors:** Linda Vincelová and Angelika Rischáneková  
**Repository:** https://github.com/anchelesr/AACC-Smart-Shopping  
**Revision:** 4 (25 November 2026): revision 2 answered the course feedback; revision 3 added the lecture material (energy price and placement, events, observability, model lifecycle, data engineering); revision 4 added value- and cost-aware routing (FR-21), the agent decision, stakeholder priorities and an evidence chain; revision 5 implemented the event bus; revision 6 adds the price watch, budget and brand constraints (FR-22) and ADR-017  
**Status:** Architecture proposal; the application and its measured results are not yet available

## Project goal

We chose laptops for the first version because prices vary enough to make historical comparison interesting, while the catalog can stay small and testable. A shopper should see where the numbers came from rather than trust an unexplained bargain label. The interface therefore brings together historical observations (*Past*), current offers (*Present*) and stored seven-day estimates (*Future*). Its recommendation is a short, transparent **Buy Now**, **Wait** or **Insufficient Evidence** message, which an AI assistant can explain in natural language using only the evidence on the screen.

Two further ideas shape the architecture. First, forecasting and the assistant are the application's AI components, so we design the harness around them (routing, guardrails, caching, tracing, human review) and evaluate them before they are trusted. Second, the application reacts to simulated energy signals (carbon intensity, electricity price and the availability of renewable energy): it senses them, decides an *operating mode* and changes its behaviour (deferred forecasts, fewer workers, cheaper AI routes) and its **placement** (flexible workloads move to a different node pool) without a redeploy. Neither may silently make the displayed forecast too old.

## System boundary and stakeholders

Each stakeholder has an identifier, an influence on the project (how much they can change what we build or whether it is accepted), an interest (how much the result matters to them) and a priority (P1 highest). The ranking is our own analysis and a proposal.

| ID | Stakeholder | Influence | Interest | Priority | Main interest |
| --- | --- | --- | --- | --- | --- |
| S-01 | Shopper | High | High | P1 | Fast, understandable price evidence and advice; honest caveats; an assistant answer that can be trusted. |
| S-02 | System operator | High | High | P1 | Controls the energy policy, sees job results, reviews flagged AI answers, keeps the system running at a known cost. |
| S-03 | Course evaluator | High | High | P1 | Sound architecture, traceable decisions, measurable quality and sustainability claims. |
| S-04 | Product owner (business view) | Medium | High | P2 | Value for the effort (see business alignment), predictable token and compute cost. |
| S-05 | Price data provider (approved CSV or API) | Low | Medium | P2 | Imports remain valid, attributed and repeatable. |
| S-06 | Energy signal provider (simulated, optionally Electricity Maps) | Low | Low | P3 | Supplies carbon intensity, price and renewable flag; a missing value must not break the application. |
| S-07 | LLM provider (external, large model) | Low | Low | P3 | Receives only the structured evidence payload needed for an explanation. |
| S-08 | Cluster platform (Kubernetes) | Low | Low | P3 | Receives taints from the Placement Controller; must stay schedulable. |
| S-09 | Time trigger (Kubernetes scheduler) | Low | Low | P3 | Starts import, carbon evaluation, forecast and evaluation jobs. |

### Conflicts of interest and how priority resolves them

Three rules turn the ranking into decisions. **R1:** a requirement is as important as the highest-priority stakeholder who needs it (S-01 to S-03 give Must, S-04 and S-05 give Should, P3 stakeholders alone give Could). **R2:** when two requirements conflict, the one of the higher-priority stakeholder wins unless that would break a Must; equal priorities are settled by the option that can be measured. **R3:** a lower-priority stakeholder is never harmed silently: the effect is shown (label, dashboard or trace).

| Conflict | Stakeholders | Resolution and where it is recorded |
| --- | --- | --- |
| Best assistant answer against token and compute cost | S-01 against S-02, S-04 | The router answers from a template or the small local model unless the value of a model call is high enough; escalation to the large model is allowed only in GREEN and within the budget; the shopper always gets a labelled answer (FR-21, NFR-18, ADR-015). |
| Fresh forecast against low-energy operation | S-01 against S-03 and the energy goal | Jobs may be deferred, but the persisted 24 h deadline wins in every mode; the shopper path is never throttled and stored prices stay visible (NFR-03, NFR-04, ADR-004). |
| Operator control against automation | S-02 | The mode is automatic; the operator can override it with an expiry and an audit entry (FR-12, ADR-004). |
| Ambitious scope against available time | S-03 against S-04 | MoSCoW priorities; Should and Could items are cut first; claims are limited to what is measured (NFR-10). |
| Answer quality against data exposure | S-01 against S-07 | Only the structured evidence payload leaves the cluster, the small model runs locally, the large model is a fallback (ADR-015, NFR-06). |
| Open data supply against data quality | S-05 against S-01 | Rejected records are reported, never silently corrected (FR-09, FR-10, NFR-05). |

Priority guides the requirements below (rule R1): shopper-, operator- and evaluator-facing requirements are *Must*; extensions that mainly add convenience are *Should* or *Could*.

### MVP boundary

Ten or more demonstration laptop models, at least three sample retailers and 30+ days of timestamped price history per relevant case are proposed as a **test fixture**, not real-life retailer coverage. Brand, model and price filtering are in scope; sophisticated specification facets are not. Out of scope: user accounts, checkout and payments, email or push alerts (alerts are shown in the application only), merchant trust ranking, unauthorised live scraping, training or fine-tuning of our own models, and the manufacturing or shipping footprint of laptops. The in-app price watch (FR-06) is kept in the shopper's browser and sends nothing.

## Use cases

The earlier eleven use cases were too fine-grained. Searching and filtering are one goal, and so are viewing the 30-day history and inspecting discount evidence. The model now has four use cases (diagram: [use-case.puml](diagrams/use-case.puml)).

| ID | Use case | Actors | Architecturally significant? |
| --- | --- | --- | --- |
| UC1 | Find and compare laptop offers | Shopper | No: a read-only catalog query that forces no structural decision. |
| UC2 | Assess a laptop's price and get advice (extension point: *explain in natural language*) | Shopper | Yes: ASUC-01, and the extension is ASUC-02. |
| UC3 | Maintain price data | Time trigger, price data provider, operator | Yes: ASUC-03. |
| UC4 | Adapt operation to carbon and energy-price conditions | Time trigger, energy signal provider, operator | Yes: ASUC-04 (decide, act and relocate: 04a, 04b, 04c). |

Details, selection criteria and sequences are in [Significant use cases](significant-use-cases.md).

## Functional requirements

Priority follows MoSCoW (Must, Should, Could) and the stakeholder importance above.

| ID | Priority | Use case | Requirement | Acceptance criterion |
| --- | --- | --- | --- | --- |
| FR-01 | Must | UC1 | Find and compare offers | Search by name, brand or model; filter by price bounds; sort ascending or descending; list every active retailer offer with currency and observed-at timestamp. |
| FR-02 | Must | UC2 | Price evidence | Plot at least 30 days of sourced observations where the data supports it; compute the 30-day reference and the delta; declare insufficient data when too few observation days exist. |
| FR-03 | Must | UC2 | Stored seven-day forecast | Read a **stored** forecast; show model identifier, generated-at time, horizon, uncertainty caveat and freshness state. |
| FR-04 | Must | UC2 | Explainable advice | Return Buy Now, Wait or Insufficient Evidence with short reasons that separate observations from estimates; never promise future prices. |
| FR-05 | Should | UC1 | Side-by-side comparison | Compare up to three laptops on best offer, reference delta, forecast status and advice. |
| FR-06 | Should | UC1, UC2 (extension) | Shortlist and in-app price watch | The shortlist is kept in the browser. A price watch (laptop and target price) is stored on the server under a random, pseudonymous device identifier, without an account or personal data; a scheduled check compares the lowest fresh comparable offer with the target and stores one in-app alert per episode (offer at or below the target), with a deduplication key. Stale data never creates an alert; the shopper can pause, change or delete a watch and sees the alerts when opening the application. No email or push ([ADR-017](adr/ADR-017.md)). |
| FR-07 | Must | UC2 | Freshness and provenance display | Show the source and age of each observation and the age and model of the forecast; mark stale or missing data. |
| FR-08 | Should | UC2 (extension) | Assistant explanation | Explain the advice in natural language using only the evidence payload; label the answer as AI-generated, simplified or refused. |
| FR-09 | Must | UC3 | Price import and validation | Scheduled importer validates, normalizes and idempotently upserts observations with source information. |
| FR-10 | Should | UC3 | Import report | Provide accepted and rejected counts with reject reasons per run as a data-quality view for the operator. |
| FR-11 | Must | UC4 | Energy signal monitoring | Sample carbon intensity, electricity price and the renewable flag every 5 minutes from the simulator (or, optionally, Electricity Maps), validate each value, keep the history and flag missing samples. |
| FR-12 | Must | UC4 | Operating mode and runtime policy | Decide GREEN, AMBER or RED from intensity and price (the more restrictive class) with hysteresis, let available renewable energy force GREEN and use a stale-signal fail-safe; the operator edits the policy and sets a time-limited override at runtime, with an audit trail. |
| FR-13 | Must | UC4 | Carbon-adaptive behaviour | Forecast jobs, worker concurrency, AI routing (see FR-21), cache lifetime and optional batches follow the operating mode (table in [Carbon adaptation](carbon-adaptation.md)). |
| FR-14 | Must | UC4 | Forecast refresh under a deadline | Each laptop has a persisted forecast job with a 24 h deadline that is never reset; the deadline forces an execution attempt in any mode. |
| FR-15 | Should | UC4 | Forecast model evaluation and selection | Backtest the baseline and the candidate model, store the results and keep the baseline active unless the candidate passes the gate. |
| FR-16 | Must | UC4 | Metrics, tracing and dashboards | Export request latency, job and mode events, forecast age, assistant routes and estimated kWh and gCO2e; show them to the operator. |
| FR-17 | Could | UC2 (extension) | Review queue for flagged answers | List guardrail-flagged assistant exchanges for the operator, record the decision and add it to the evaluation set. |
| FR-18 | Should | UC4 | Energy-aware placement | In AMBER, RED or when renewable energy is available, flexible workloads (forecast and evaluation Jobs, local model runtime) are steered to the eco node pool by taints; request-path components never move; changes follow safety and dwell rules. |
| FR-19 | Should | UC3, UC4 | Change notification | Publish `price.changed` and `mode.changed` events; consumers are idempotent; state stays in the database and a lost event is repaired by the periodic pull. |
| FR-20 | Should | UC4 | Drift and live quality monitoring | Compare a current window with a reference window of the price series, record a drift score and its shape, compute the live forecast error when prices arrive, run candidate models in shadow mode and allow a rollback of the active model. |
| FR-21 | Should | UC2 (extension) | Value- and cost-aware routing | Before any model call the router compares the value of the call (question type, caveats, follow-up) with its estimated cost (tokens, energy, gCO2e, electricity price) under the current mode and budget, and chooses template, small local model or large external model; every decision is traced with its reason (table in [AI architecture](ai-architecture.md)). |
| FR-22 | Should | UC2 | Budget and brand constraints | The shopper may give a budget and preferred brands. When the best offer is above the budget, Buy Now is withheld (the advice becomes Wait with the reason "above your budget") and up to three comparable alternatives within the constraints are offered; a brand mismatch adds a caveat and alternatives. Constraints never change the evidence rules and are not stored. |

### Price and recommendation semantics

The explicit 30-day reference for the MVP is the **median of daily lowest valid offers** for a matching product over the last 30 days. The delta is `d = current_lowest_price / reference - 1`. This is a design policy to validate, **not** a claim that the seller advertised a compliant discount. Evidence is *sufficient* when at least 10 distinct days of the last 30 contain a valid offer in a comparable currency and a valid current offer exists (configurable).

Advice rules (demonstration values, configurable; `f` is the stored forecast's change from today to day 7):

0. Optional constraints (FR-22) are applied after the rules below: above the budget, Buy Now becomes Wait.
1. No sufficient evidence → **Insufficient Evidence**.
2. Fresh forecast and `f <= -3 %` → **Wait** (a fall is expected).
3. `d >= +3 %` → **Wait** (above the 30-day reference).
4. `d <= -3 %` → **Buy Now** (below the reference).
5. Fresh forecast and `f >= +3 %` → **Buy Now** (a rise is expected).
6. Otherwise → **Insufficient Evidence** (no clear signal).

If the forecast is stale or missing, rules 2 and 5 are skipped and the answer carries a caveat. The assistant may only restate this result; it never changes it.

## Non-functional properties - proposed targets

These are acceptance criteria to test, not results.

| ID | Quality attribute | Proposed acceptance target |
| --- | --- | --- |
| NFR-01 | Performance | `GET /products/{id}/insights` p95 latency <= 2.0 s at 20 requests/s on seeded demo data (the deterministic path; the assistant is excluded). |
| NFR-02 | Freshness | At least 95 % of active eligible laptops have a forecast no older than 24 h in the target scenario; exceptions are flagged. |
| NFR-03 | Deadline | No controlled-test forecast job is intentionally deferred past its persisted 24 h deadline, in any operating mode. |
| NFR-04 | Fault tolerance | A forecast worker, model, carbon signal or LLM outage does not prevent viewing stored prices. A database outage needs a separately provisioned read cache and is **not guaranteed** by the MVP. |
| NFR-05 | Data integrity | Reject invalid rows; enforce unique source observations and idempotent retry; a repeated import inserts nothing new. |
| NFR-06 | Security | TLS at the edge; no plaintext secrets in the repository; least-privilege database and Kubernetes access; operator endpoints authenticated; retailer-supplied text treated as data, never as instructions. |
| NFR-07 | Modifiability | The forecast model and the LLM provider or model can be swapped behind their adapters without changing the shopper REST contract or the advice rules. |
| NFR-08 | Observability | Request latency, forecast age, job outcome, operating mode, signals, placement and estimated or measured kWh and gCO2e are visible in monitoring; one trace id follows a request through the components ([Observability](observability.md)). |
| NFR-09 | Scaling | API replicas and batch workers scale independently with defined resource requests and limits. |
| NFR-10 | Sustainability evidence | A controlled experiment compares immediate execution with the adaptive policy on the same workload and records energy, gCO2e, deferrals, forecast age and deadline errors. |
| NFR-11 | Assistant groundedness | On the golden evaluation set, every number, currency and date in an approved answer appears in the evidence payload, and the answer's action label equals the rule result; failures fall back to the template. |
| NFR-12 | Forecast quality | The candidate model replaces the baseline only if its backtest MAE is not worse than the baseline's; the comparison and its data limits are reported. |
| NFR-13 | Runtime reconfigurability | A policy change or override takes effect within one evaluation interval plus the 60 s cache time, with no redeployment (the event only makes it earlier). |
| NFR-14 | AI traceability | Every model call is logged with route, model, prompt version, tokens, latency, guardrail result and an estimated energy value whose method is documented. |
| NFR-15 | Deployability | A merged change reaches the demo cluster through the pipeline without manual steps; a release can be rolled back by reverting one commit. |
| NFR-16 | Mode stability | With a noisy simulated signal around a threshold, the mode changes at most four times per hour. |
| NFR-17 | Availability | Shopper read path: proposed objective 99.5 % per month (about 3.6 h of downtime), measured by a synthetic probe; a database outage is not covered by the MVP. |
| NFR-18 | Cost control | A daily token budget and a compute budget are enforced by the router; when the budget is exhausted the assistant answers from templates. Costs are visible in dashboards. |
| NFR-19 | Event delivery | Delivery is at-least-once, consumers are idempotent (a duplicated event creates no second job), and a missed event is corrected by the next pull within 60 s. |
| NFR-20 | Placement safety | The Placement Controller never leaves zero schedulable nodes, changes placement at most once per dwell time (15 min) and records every decision, including skipped ones. |

## Business alignment and framing

The course asks for goals to be translated into measurable terms before any design. Our bridge from business to technical metrics:

| Business goal | Hard value (measurable) | Soft value | Technical metric |
| --- | --- | --- | --- |
| A shopper decides with less effort and fewer regrets | Time to a decision; share of sessions that reach a shortlist | Trust in the advice, clarity of caveats | NFR-01, NFR-11, advice-rule tests |
| Keep running cost predictable | Tokens and compute cost per day | Confidence to leave the system running | NFR-18, assistant cost panel |
| Lower the footprint of the server-side workload | kWh and gCO2e against the immediate-run baseline | A credible sustainability story | NFR-10 |

**Framing.** *Forecast:* input = the cleaned 30-day daily series of one laptop; output = seven daily prices; objective = minimise mean absolute error (a regression). *Assistant:* input = evidence payload and question; output = a grounded explanation; success = every number grounded and the action label equal to the rule result (NFR-11). The assistant is deliberately not given the decision.

**Where AI is worth it.** The advice is rule-based because rules are cheap, deterministic and auditable. A model call is made only when it adds value that a template cannot, and when the mode and budget allow it (the router's value and cost gate, FR-21, [AI architecture](ai-architecture.md)). A forecast model is adopted only when it beats the baseline.

## Data and AI constraints

- Price observations contain product, retailer, amount, currency, observation time and source provenance.
- The interactive request never launches a forecast; it reads a stored forecast with its age ([ADR-006](adr/ADR-006.md)).
- We do **not** train or fine-tune models. The forecast uses a non-trained baseline and one ready-made candidate behind an adapter ([ADR-008](adr/ADR-008.md)); the assistant uses an existing LLM through a gateway ([ADR-007](adr/ADR-007.md)).
- The assistant receives a structured evidence payload only. It has no tools and cannot read other data or change anything.
- Quantities, currencies and time zones are normalized; incomparable currencies are never converted silently.
- Forecasts and explanations are estimates with a timestamp and limits, not purchasing guarantees.
- gCO2e estimation concerns the server-side compute workload, including model calls, not laptop manufacturing or shipping.
- Language-model output is non-deterministic, so the model never sits in a control loop: the advice rules and the operating-mode decision are deterministic, and the model only phrases a result ([ADR-015](adr/ADR-015.md)).
- Data handling decisions (sources, formats, layers, leakage rules) are in [Data engineering](data-engineering.md).
