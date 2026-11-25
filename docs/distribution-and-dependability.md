# Distribution, dependability and consistency

The course asks us to distribute out of **necessity, not because it is fashionable**, to justify decisions with metrics and to analyse a system through its architecture, communication, naming, consistency, fault tolerance and security. This document applies those lenses to Smart Shopping. It argues where we distribute, where we deliberately do not, which failures we expect and which consistency each kind of data needs.

## Necessity versus sufficiency

| Decision | Distributed or central? | Necessity argument |
| --- | --- | --- |
| Frontend and backend | Separate deployments | Independent scaling and release; the browser is a separate machine anyway. |
| Backend modules (API, assistant, gateway, policy admin) | One modular deployment, not microservices | Sufficient for the load; fewer network hops and failure points; modules keep the interfaces so that a split stays possible ([ADR-001](adr/ADR-001.md)). |
| Batch workers | Separate Jobs | Different lifecycle and the only workload that can be shifted in time or space for energy reasons. |
| Event notifications | Broker (publish-subscribe) | Producers must not know consumers; five components react to two kinds of change ([ADR-012](adr/ADR-012.md)). |
| Database | One instance, central | One source of truth is easier to keep consistent and to protect. Distribution would add replication and conflict problems for no demonstrated need. The cost is a single point of failure, stated as a limitation. |
| Model hosting | Local small model plus external large model | Cost, data control and energy; see [ADR-015](adr/ADR-015.md). |
| Shortlist | In the browser (edge) | No account, no personal data on the server. |
| Price watch and alerts | On the server, under a random device id | Alerts must catch dips between visits ([ADR-017](adr/ADR-017.md)); no personal data, only the pseudonymous id, the laptop and the target. |

## The six design goals

| Goal | How the design addresses it |
| --- | --- |
| Resource sharing | One database, one gateway to the model providers, shared cache and trace log. |
| Distribution transparency | The shopper sees one application. Location transparency is *hidden from users but visible to designers*: the Placement Controller deliberately chooses where flexible work runs. Relocation (Kubernetes moves pods), failure (a friendly error message) and concurrency (leases) are transparent. |
| Openness | Interface-first design: components are defined by provided and required interfaces ([ADR-010](adr/ADR-010.md)); the forecast model, the signal source and the model providers sit behind adapters. Teams could build the components in parallel from the interface catalogue. |
| Dependability | Availability, reliability, safety and maintainability are in tension (maintenance windows cost availability); see the failure analysis below. |
| Security | TLS, least privilege, operator authentication, untrusted retailer text, no tools for the model (NFR-06). |
| Scalability | Size: stateless backend replicas (HPA), workers by operating mode. Geography and administration are out of scope. |

Transparency has limits, and we respect them: a time-sensitive service that answers too late is useless (an assistant answer after five minutes), so every external call has a timeout and a template fallback; a location-aware behaviour is the stated purpose of the placement layer.

## Pitfalls of distribution and our response

| Pitfall | Where it applies | Response |
| --- | --- | --- |
| Partial failures that are hard to find | Worker down while the API is up | Readiness and liveness probes, job leases, a stored forecast with its age instead of an error. |
| Failure probabilities multiply | Many components in a chain | See the availability calculation below. |
| More endpoints, more attack surface | Broker, controllers, model runtime | Internal services only, network policies, authenticated operator paths, least-privilege cluster access for the Placement Controller. |
| Dynamic environment | Pods are killed, moved and rescheduled | Services addressed by name and port, never by IP; idempotent jobs; state in the database, not in a pod. |

**Availability in series and in parallel.** If every component has an availability of 99.5 %, a chain of two gives 0.995 x 0.995 = 99.0 %. Two independent replicas of one component give 1 - 0.005 x 0.005 = 99.9975 % for that component. Replicating the backend therefore improves the backend but not the system: with the database as a single instance the overall figure stays close to 99.5 % (0.999975 x 0.995 = 99.4975 %). This is why NFR-17 and the limitation about a database outage are stated together, and why the cheapest improvement is a short repair time (MTTR), not another backend replica. The numbers are an illustration of the method with assumed availabilities, not measurements.

## Fault, error, failure

A **fault** is the cause, an **error** is an invalid internal state, a **failure** is the service not meeting its promise. A design can stop the chain at any link: mask the fault, detect the error, or tolerate the failure.

| Fault (type) | Error | Failure to avoid | Where we stop it |
| --- | --- | --- | --- |
| Price provider unreachable (transient) | No new observations | Shopper sees old data presented as current | The age of every observation is shown; the failed run is recorded; the next trigger retries. |
| Pod evicted or node lost while a job runs (crash, intermittent) | Job lease expires | Forecast older than the deadline | Lease, retry, persisted deadline, idempotent job. |
| LLM invents a number (response failure) | Draft with an unsupported fact | Shopper acts on a false price | Output guardrail, retry once, template, human review. |
| Provider sends a plausible but false price or signal (arbitrary failure) | Wrong evidence or wrong mode | Wrong advice or needless deferral | Range and timestamp validation, outlier flags, stale-signal fail-safe. Masking an arbitrary fault by voting would need 2k+1 independent sources; we have one source per signal, so we detect and fail safe instead. |
| Message lost on the bus (omission) | A consumer misses `mode.changed` | Old behaviour for a while | Pull of the mode every 60 s repairs it. |
| Model call slower than the window (timing) | No answer in time | Spinner forever | Timeout, then template. |

In an asynchronous system a crashed process cannot be told from a slow one, so we use timeouts and accept false suspicions; the cost of a false suspicion is a retry, which the idempotent design makes harmless.

## Consistency by kind of data

| Data | Writers and readers | Needed guarantee | Mechanism |
| --- | --- | --- | --- |
| Observations | One writer (importer), many readers | Reads must not go backwards (monotonic reads); staleness is acceptable if labelled | Single database; cache keyed by the evidence hash; observation age displayed. |
| Forecasts | One worker per laptop, many readers | Never show an older forecast after a newer one | `generated_at` is monotonic per laptop; caches are keyed by it. |
| Policy and mode | One writer (Policy Engine), all components read | Strong for writes; bounded staleness for readers | Transaction in the database; readers cache at most 60 s (a time bound, as in continuous consistency); event for earlier notice. |
| Operator edits | Operator writes and reads | Read-your-writes | The administration path reads through to the database, not the cache. |
| Job ownership | Several scheduler runs | Mutual exclusion | Lease claimed in one transaction; unique open job per laptop. |

**Replication and the access-to-update ratio.** An observation is updated about once a day and read many times, so reads dominate (N/M is high) and caching pays off. Policy data is read often and updated rarely; the same holds. If a datum were updated more often than read, replicating it would waste synchronisation, and we would not.

**CAP.** Under a network partition between the backend and the database, the shopper path chooses availability for *prices* (show cached data labelled with its age, within the limits of NFR-04 and the stated limitation), while the policy and job state choose consistency (writes are refused rather than diverge). The partition between the backend and the model provider is simply tolerated by the template fallback.

**Consensus.** We implement none. We depend on systems built on it: the Kubernetes control plane keeps its state in etcd (Raft), and Kafka in KRaft mode uses Raft for its metadata. There is no leader election in our own code because `concurrencyPolicy: Forbid` plus a database lease are enough for single-writer jobs.

## Naming

Components find each other through Kubernetes service names and ports, not addresses, because IPs change. Entities use identifiers that are unique, immutable and never reused (product SKU, job id, trace id, import run id), as opposed to human-readable names that can change.

## Where things run: hybrid and cloud choices

| Question | Our position |
| --- | --- |
| Local or cloud | Everything runs in one cluster for the demonstration. Sensitive or cost-driving parts (the small model, the database) are designed to stay under our control; the large model is an external service that receives only the evidence payload. |
| Region and provider | Prefer a European region and provider (regulation, data location, and carbon intensity differ by region). |
| Lock-in | Containers, Kubernetes manifests, Helm and adapters keep the exit open: a change of provider is a configuration and adapter change, not a rewrite. |
| Cost levers | Right-sizing and autoscaling (HPA) for the backend; short-lived Jobs for batch work; interruptible (spot or preemptible) capacity is a candidate for the workers because they are idempotent and leased, while the database stays on dependable capacity. Budgets and alerts protect against runaway scaling. |
| Edge | The browser holds the shortlist; no server-side training means federated learning is not needed. |
