# Architecture decision records

## ADR-001: kind instead of minikube

**Status:** accepted. **Decision:** use kind 0.33.0 with Kubernetes 1.37.0, one control-plane node, and two workers. **Why:** kind makes the multi-node topology reviewable, works with Docker, and supports fast local image loading. **Consequence:** host ports and storage remain development-grade and Docker resources must be sized explicitly.

## ADR-002: Gateway API instead of Ingress

**Status:** accepted for phase 4. **Decision:** use Gateway API with Envoy Gateway; use ingress-nginx only if a recorded blocker prevents it. **Why:** Gateway separates infrastructure and route ownership and avoids building on the frozen Ingress API. **Consequence:** the cluster needs Gateway API CRDs and a controller before routes reconcile.

## ADR-003: Helm plus Kustomize

**Status:** accepted for phase 5. **Decision:** Helm packages the reusable shop application; Kustomize overlays change replicas, resources, hostnames, and image tags for dev/staging/prod. **Why:** this keeps templates in one place while environment deltas remain plain YAML. **Consequence:** generated YAML is validated in CI and overlays must not duplicate chart templates.

## ADR-004: Argo CD instead of Flux

**Status:** accepted for phase 8. **Decision:** use Argo CD and its app-of-apps pattern. **Why:** the application tree and health model make ownership, reconciliation, and deployment state directly inspectable during release validation. **Consequence:** Argo CD adds a comparatively large local footprint; its chart values will use a slim profile.

## ADR-005: default-deny NetworkPolicies

**Status:** accepted and implemented. **Decision:** deny all ingress and egress in `shop`, then permit DNS and workload-specific API/worker connections to PostgreSQL/Redis. **Why:** allowed communication becomes auditable and lateral movement is constrained. **Consequence:** every new external dependency requires an explicit policy change, and the cluster CNI must enforce NetworkPolicy.

## ADR-006: credentials are runtime inputs

**Status:** accepted and implemented. **Decision:** commit only `.env.example`; create `shop-runtime` from ignored `.env` during deployment. **Why:** base64 Kubernetes Secret manifests are not encryption and do not belong in a public repository. **Consequence:** each operator must provision local values; phase 6 will add a dummy encrypted example for a GitOps-safe pattern.
