# CI/CD

The first revision named CI/CD in the verification plan but did not design it. This document describes the target pipeline, what exists today and the evidence we will collect. Delivery is a quality attribute (NFR-15) and it also protects the AI components: a model or prompt change is released only if its gates pass.

![CI/CD pipeline](diagrams/previews/cicd-pipeline.png)

## Principles

- **Trunk-based development** with short pull requests; required checks block the merge.
- **Everything as code:** application, infrastructure manifests, carbon policy defaults, prompts and PlantUML sources live in this repository.
- **Build once, promote the same image.** Images are tagged with the git SHA; environments differ only in configuration.
- **GitOps delivery.** The pipeline commits new image tags to the deployment manifests; a GitOps controller in the cluster applies them. Rollback is a revert of that commit.
- **AI changes are gated like code.** Forecast and assistant quality are measured in the pipeline before release.

## Stages and gates

| Stage | Trigger | Checks | Gate |
| --- | --- | --- | --- |
| 1. Fast checks | Pull request | Lint, format, type check; unit tests for evidence, advice rules, mode hysteresis, guardrails and the importer; PlantUML syntax and link check; secret scan; dependency audit | All green |
| 2. Contract tests | Pull request | REST schema compatibility; component interface contracts against the [interface catalogue](architecture.md) | No breaking change without a version bump |
| 3. Build | Merge to main | Build images for frontend, backend and workers with the git SHA; vulnerability scan; software bill of materials | No critical findings |
| 4. Integration | Merge to main | Ephemeral Kubernetes cluster: migrations, import the same batch twice (no duplicates), simulated carbon trace through GREEN, AMBER and RED, deadline override, short load smoke at the target request rate | All scenarios pass |
| 5. AI gates | Merge to main | Forecast backtest: candidate MAE not worse than the baseline ([ADR-008](adr/ADR-008.md)); assistant golden set: groundedness and label agreement meet NFR-11, with a capped model budget; the small local model is used so the gate runs on a self-hosted runner | Thresholds met |
| 6. Publish | Merge to main | Push images; commit new tags to the deployment manifests | Stages 3-5 green |
| 7. Deploy | Manifest commit | The GitOps controller synchronises the demo cluster; a change to a model or prompt goes through shadow and staged rollout ([AI architecture](ai-architecture.md)) | Sync healthy |
| 8. Verify | After deploy | Smoke tests: ready check, one insights call, operating-mode call, a metrics scrape | Pass, otherwise roll back |

## Continuous integration practice

- **Flow:** work on a branch, open a pull request, merge to `main` only when the required checks pass (branch protection), merging triggers the build and the deployment. Deployment happens from `main` only.
- **Unit tests on every push** run first; the cheapest check gives the fastest feedback.
- **Self-hosted runner for AI steps.** Stages that need the local model, or data that must stay under our control, run on a self-hosted runner (a machine we operate, for example the one that hosts the local model). A runner has access to the repository, the cluster and the code, so it must clean up after every job (virtual environment, output files) and be registered with the minimum scope. Cloud-hosted runners do the rest. A job that runs only on a single machine can block every other push, so a second runner is planned.
- **Manual trigger and evaluation workflow.** A manually started workflow runs the golden-set evaluation on demand and fails if the answer is empty, too short, or contains an error marker, which catches a broken model before a release.
- **Packaging.** The placement controller is packaged as a Helm chart; a local copy of any third-party chart is kept so that an upstream change cannot break a build.

## Environments

| Environment | Purpose | Notes |
| --- | --- | --- |
| Local | Development | Containers for the database and workers; stubbed carbon feed and model provider. |
| CI | Automated tests | Ephemeral cluster created per run, removed afterwards. |
| Demo cluster | Course demonstration and evidence | Receives every green main build; policy defaults come from the ConfigMap in Git. |

## Configuration, secrets and policy

Carbon policy defaults and prompt versions are versioned in Git. The operator's runtime policy changes are stored in the database with an audit trail and are deliberately *not* a deployment (NFR-13). Secrets (database credentials, model provider key) are Kubernetes Secrets or CI secrets and never appear in the repository (NFR-06).

## Carbon-aware pipeline (optional)

Heavy scheduled pipeline work, such as the nightly extended evaluation, can ask the same Policy Engine mode before it starts and defer in AMBER or RED up to a maximum delay. This is optional and is only meaningful once the application runs. Pull-request checks are never deferred.

## What exists today

Two workflows exist. [`docs-validate.yml`](../.github/workflows/docs-validate.yml) checks the syntax of every PlantUML file in `docs/diagrams` and fails the run on an error; we ran the same loop locally on all PlantUML diagrams of revision 2 (twelve at that time) and on a deliberately broken file, where it failed as intended. [`events.yml`](../.github/workflows/events.yml) runs the event bus tests without a broker, the demonstration, and then the integration tests against an `apache/kafka` service container; the unit tests pass locally, but neither workflow has run on GitHub yet. The rest of the application pipeline above is a design. It becomes evidence once the application exists, and then we will record workflow runs, image tags, the deployment sync and the smoke tests in the verification plan.
