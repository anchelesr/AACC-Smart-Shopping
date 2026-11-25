# Event bus (Kafka)

The event bus lets components react to changes without polling each other: a new price batch creates forecast jobs, and a mode change reaches the scheduler, the assistant gateway and the placement controller. It is decided in [ADR-012](adr/ADR-012.md) (FR-19, NFR-19). **The database stays the source of truth**; an event only says "something changed, look at the database".

Unlike most of this repository, the event bus is **implemented**: code, deployment files and tests exist. What is verified and what is not is stated at the end.

## Topics

| Topic | Key | Partitions | Retention | Producer | Consumer groups |
| --- | --- | --- | --- | --- | --- |
| `price.changed` | laptop id | 3 | 7 days | Price Importer (once per laptop with new observations) | `job-scheduler` |
| `mode.changed` | `operating-mode` | 1 | 7 days | Policy Engine (only when the mode or the placement target changes) | `job-scheduler`, `llm-gateway`, `placement-controller` |
| `events.dead` | `dead` | 1 | 14 days | any consumer | operator inspection |

Why these numbers: events with the same key stay in one partition and therefore in order, so all events of one laptop arrive in order. Mode changes use one key and one partition because their order matters (a late AMBER must not overwrite a newer RED). Three partitions for prices allow up to three scheduler replicas to share the work, because inside one consumer group each partition goes to one consumer. Every group receives every event, which is how three components react to the same mode change.

## Event format

Every event is a small JSON document with an envelope and a topic-specific `data` part (`src/events/model.py`); invalid events are rejected when they are created and when they are read.

| Field | Meaning |
| --- | --- |
| `id` | Unique identifier (UUID); the basis of duplicate detection |
| `type` | Topic name |
| `key` | Partition key |
| `occurred_at` | UTC time |
| `version` | Schema version (1) |
| `data` | `price.changed`: `laptop_id`, `batch_id`, `new_observations`. `mode.changed`: `mode` (GREEN, AMBER, RED), `reason`, `since`, `placement_target` (standard, eco), `policy_version` |

## Delivery guarantees

| Mechanism | Setting | Effect |
| --- | --- | --- |
| Producer acknowledgement | `acks=all`, `enable.idempotence=true` | A published event is acknowledged by the broker; retries of the producer do not create duplicates. If the broker does not acknowledge, `BusUnavailable` is raised. |
| State before notification | The importer and the policy engine commit to the database first and publish afterwards | A published event always refers to stored state. A failed publish is counted and does not fail the import or the decision. |
| Consumer commit | `enable.auto.commit=false`; the offset is committed after the handler succeeded | At-least-once: a crash before the commit redelivers the event. |
| Idempotent handler | At most one open forecast job per laptop (unique index in the database) | Handling the same or an equivalent event twice changes nothing. |
| Processed-events table | One row per group and event id | A redelivered event is skipped and counted as a duplicate. |
| Retry and dead letter | Three attempts, then the event goes to `events.dead` with the error and the offset is committed | One bad event does not block a partition. An unparsable message goes to `events.dead` at once. |
| Pull as repair | `reconcile()` for jobs; the mode is read with a cache of at most 60 seconds | A lost event is repaired without the broker (see the table below). |

Exactly-once delivery is not claimed; at-least-once with idempotent consumers gives the same result for our two topics.

## Failure cases

| Failure | What happens | Covered by |
| --- | --- | --- |
| Broker down while importing | Prices are stored, the publish is counted as failed, the shopper path is untouched; the next `reconcile()` creates the jobs | `test_broker_down_does_not_fail_the_import_and_the_pull_repairs_it` |
| Event acknowledged but lost | Jobs are missing until `reconcile()` runs; the mode cache refreshes within 60 s | `test_lost_price_event_is_repaired_by_the_pull` |
| Event delivered twice | One job only | `test_duplicated_price_event_creates_one_job`, `test_handler_is_idempotent_even_without_the_processed_table` |
| Consumer crashes after handling, before commit | The event is redelivered and skipped as a duplicate | `test_uncommitted_event_is_redelivered_after_a_crash` |
| Handler fails temporarily or for good | Retried, then dead-lettered | `test_a_transient_failure_succeeds_on_retry`, `test_failing_handler_is_retried_then_dead_lettered` |
| Malformed message | Dead-lettered, not retried | `test_poison_message_is_dead_lettered_not_retried` |
| Broker restarts | Events survive on the persistent volume; consumers resume from the committed offsets | Round-trip integration tests (not yet run, see below) |
| Mode change arrives late | The mode is also pulled, and the cache is at most 60 s old; events only shorten the delay | `test_mode_cache_is_at_most_60_seconds_old_and_events_invalidate_it` |

## Deployment

| File | Purpose |
| --- | --- |
| `deploy/kafka/kafka.yaml` | Headless Service `kafka` and a StatefulSet with one broker in KRaft mode (no ZooKeeper), image `apache/kafka:3.9.0`, a 2 Gi volume, resource requests and limits, probes, automatic topic creation off. The pod tolerates the `energy-role` taint, so the Placement Controller never evicts the broker; it runs on the standard pool. |
| `deploy/kafka/topics-job.yaml` | A Job that waits for the broker and creates the three topics (`--if-not-exists`, safe to repeat). |
| `deploy/docker-compose.yml` | The same broker and topics on a developer laptop. |

```
kubectl apply -f deploy/kafka/kafka.yaml
kubectl apply -f deploy/kafka/topics-job.yaml
# local alternative
docker compose -f deploy/docker-compose.yml up -d
KAFKA_BOOTSTRAP=localhost:9092 PYTHONPATH=src python -m events.demo
```

Clients inside the cluster use the bootstrap address `kafka:9092` (environment variable `KAFKA_BOOTSTRAP`).

## Code

| Path | Content |
| --- | --- |
| `src/events/model.py` | Event envelope, topic schemas, validation |
| `src/events/bus.py` | `IEventBus`: an in-memory bus with fault injection (tests, demo) and the Kafka bus (confluent-kafka), topic creation |
| `src/events/consumer.py` | Idempotent consumption, retry, dead letter, counters |
| `src/shopping/core.py` | Price Importer, Job Scheduler (with `reconcile()`), Policy Engine and the cached mode reader, on SQLite for the demonstration |
| `src/events/demo.py` | End-to-end demonstration |
| `tests/` | 30 event bus tests without a broker, 3 integration tests that need one (the other tests cover advice, catalog and watch) |

## Limits and what has been verified

- **One broker, replication factor 1.** If the broker or its volume is lost, events are lost; the pull path repairs the effects. A production setup would use three brokers, replication factor 3 and `min.insync.replicas=2`. We do not claim high availability of the bus.
- **No authentication or encryption** on the in-cluster listener (demonstration only). A NetworkPolicy that allows only the producers and consumers, and TLS with authentication, would be needed before real use.
- **Verified:** 30 automated tests pass without a broker (event schema, delivery cases above, Kafka client settings against a fake client library, and that the deployment files and the code describe the same topics). The in-memory demonstration runs end to end.
- **Not yet verified:** the three integration tests and the demonstration against a real broker, the Kubernetes manifests on a cluster and the GitHub workflow `events.yml`. They could not be run in the environment in which this revision was prepared (no container runtime, no access to the broker image or to the Kafka distribution). Run `docker compose up -d` and the demonstration or the CI workflow to obtain this evidence, and record the result in the [verification plan](verification-plan.md) (V-11).
- The SQLite database in `shopping/core.py` stands in for PostgreSQL; the behaviour that matters (unique open job per laptop, idempotent upsert) maps to a unique partial index and `INSERT ... ON CONFLICT DO NOTHING` there.
