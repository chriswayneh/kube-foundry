# Delivery checklist

Every phase must end with healthy workloads, updated documentation, and reproducible verification.

## Phase 1: cluster and first workload

- [x] Pin kind node image by version and digest
- [x] Configure one control-plane, two workers, and host ports 80/443
- [x] Create `shop` and deploy API with a Service, startup/liveness probes, and resources
- [x] Document Pod, ReplicaSet, and Deployment ownership
- [x] Verify manifests render with `kubectl kustomize`
- [x] Live verify `/healthz` against the kind-hosted API (2026-09-17)

## Phase 2: config and health

- [x] Commit non-sensitive ConfigMap; create Secret at runtime from ignored `.env`
- [x] Add startup, liveness, and fail-closed readiness semantics
- [x] Record the forced probe-failure runbook
- [x] Execute and record timestamped probe-failure evidence (2026-09-17)

## Phase 3: data plane

- [x] Add PostgreSQL StatefulSet, headless Service, and PVC
- [x] Add Redis Deployment, Service, password, and PVC
- [x] Create tables idempotently on API/worker startup
- [x] Add queue worker and job status persistence
- [x] Default-deny ingress/egress and explicitly allow DNS/data paths
- [x] Add smoke and persistence exercises
- [x] Live verify CRUD, queued work, PVC persistence, and denied unauthorized traffic (2026-09-17)

## Phase 4: traffic

- [x] Install pinned Gateway API CRDs and Envoy Gateway
- [x] Route `/` to web and `/api` to API
- [x] Add cert-manager and self-signed issuer
- [x] Document host access
- [x] Verify HTTP/HTTPS, certificate trust, item creation, job completion, and unmatched routes (2026-09-19)

## Phase 5: packaging and environments

- [x] Package shop as Helm chart
- [x] Add dev/staging/prod Kustomize overlays
- [x] Verify `make deploy-phase5` from a clean cluster (2026-09-19)
- [x] Verify all three profiles through HTTPS and preserve existing development PVCs during migration

## Phase 6: security

- [x] Add ServiceAccounts, namespace RBAC, restricted PSA, and Kyverno policies
- [x] Add dummy SOPS or Sealed Secrets example
- [x] Verify allowed/denied admissions, RBAC scope, token isolation, and dummy encryption round-trip (2026-09-19)

## Phase 7: observability and scale

- [x] Add slim kube-prometheus-stack, ServiceMonitor, dashboard, HPA, and PDBs
- [x] Verify scraping, dashboard provisioning, CPU scale-up/recovery, and eviction dry-runs (2026-09-19)

## Phase 8: GitOps and CI

- [ ] Add Argo CD root/child applications and pinned installation
- [ ] Add PR validation/scanning and main image-publish/update workflows
