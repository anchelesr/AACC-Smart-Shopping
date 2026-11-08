# Verification checks

| Check | Evidence to collect |
| --- | --- |
| Data fixture | At least 10 exact laptop variants, three sample retailers and 30+ days of labelled observations where the fixture supports them. |
| Import integrity | Import an identical observation set twice; inspect accepted/rejected counts and confirm there are no duplicates. |
| Shopper flow | Demonstrate search, current-offer comparison, reference-price calculation, and missing/stale forecast handling. |
| API load | Replay 20 requests/s on seeded data; report p95 latency and error rate against the proposed 2-second target. |
| Carbon policy | Supply simulated low, high and missing signals; inspect RUN/DEFER decisions and the deadline override. |
| Sustainability comparison | Execute matched jobs under immediate and shifted schedules; collect kWh, estimated gCO₂e, timing and deferral rates. |
| Kubernetes evidence | Record Deployments, Services, CronJobs/Jobs, retry outcomes, logs and resource constraints. |
| Monitoring | Export metrics and capture evidence for latency, failures, job age and forecast freshness. |
| CI/CD | Record workflow execution covering validation, build, test and deployment to the demonstrator cluster. |
