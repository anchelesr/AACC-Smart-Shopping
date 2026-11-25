# Smart Shopping — submission note

**Smart Shopping — Price Analysis, Discount Prediction & Energy-Aware Recommendations**

**Authors:** Linda Vincelová and Angelika Rischáneková  
**Course:** AI Architecture and Cloud Computing (AACC)  
**University GitHub:** https://github.com/anchelesr/AACC-Smart-Shopping  
**Revision:** 9 (final project, 25 November 2026)

| Expected part | Where |
| --- | --- |
| Project specification (features, non-functional properties) | [project-specification.md](project-specification.md) |
| Architecturally significant use cases | [significant-use-cases.md](significant-use-cases.md) |
| Architecture: UML use-case, sequence and component models in PlantUML | [diagrams](diagrams/) and [architecture.md](architecture.md) |
| Architecture decisions | [adr](adr/) (ADR-001 to ADR-017; ADR-011, ADR-013, ADR-014 and ADR-017 are proposed and await the authors' confirmation, ADR-012, ADR-015 and ADR-016 are accepted) |

The repository also contains the energy-adaptation, AI, data, observability, dependability, Kubernetes and CI/CD designs, the traceability matrices, the response to the course feedback and the AI usage log. Since revision 8 the shopper path and the energy-adaptive control loop are implemented as code with tests, and revision 9 adds the deployment files for a two-pool Kubernetes cluster, Prometheus and Grafana, a CI/CD pipeline, estimated carbon metrics with a reproducible simulated experiment, and a video script (see [implementation.md](implementation.md), [../deploy/README.md](../deploy/README.md), [carbon-experiment.md](carbon-experiment.md) and [video-script.md](video-script.md)). The deployment, the pipeline and the monitoring have been written and checked statically but **have not run on a real cluster or on GitHub Actions**, and no measured energy or carbon saving is claimed: all energy and emission values are estimates on simulated signals.
