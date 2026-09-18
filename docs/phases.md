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

- [ ] Install pinned Gateway API CRDs and Envoy Gateway
- [ ] Route `/` to web and `/api` to API
- [ ] Add cert-manager and self-signed issuer
- [ ] Document host access

## Phase 5: packaging and environments

- [ ] Package shop as Helm chart
- [ ] Add dev/staging/prod Kustomize overlays
- [ ] Verify `make deploy-phase5` from a clean cluster

## Phase 6: security

- [ ] Add ServiceAccounts, namespace RBAC, restricted PSA, and Kyverno policies
- [ ] Add dummy SOPS or Sealed Secrets example

## Phase 7: observability and scale

- [ ] Add slim kube-prometheus-stack, ServiceMonitor, dashboard, HPA, and PDBs

## Phase 8: GitOps and CI

- [ ] Add Argo CD root/child applications and pinned installation
- [ ] Add PR validation/scanning and main image-publish/update workflows
