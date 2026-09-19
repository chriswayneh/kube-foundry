# Architecture decision records

## ADR-001: kind instead of minikube

**Status:** accepted. **Decision:** use kind 0.33.0 with Kubernetes 1.37.0, one control-plane node, and two workers. **Why:** kind makes the multi-node topology reviewable, works with Docker, and supports fast local image loading. **Consequence:** host ports and storage remain development-grade and Docker resources must be sized explicitly.

## ADR-002: Gateway API instead of Ingress

**Status:** implemented in phase 4. **Decision:** use Gateway API with Envoy Gateway. **Why:** Gateway separates infrastructure and route ownership. **Consequence:** the cluster needs Gateway API CRDs and a controller before routes reconcile. The pinned controller chart bundles the compatible CRDs.

## ADR-007: loopback access and local TLS

**Status:** implemented in phase 4. **Decision:** expose the Envoy ClusterIP Service through a loopback port-forward on 8080/8443 and issue a local certificate with cert-manager. **Why:** this works with the existing Docker Desktop cluster without rebuilding nodes or installing a load balancer. **Consequence:** access requires a running port-forward, and browsers do not trust the self-signed certificate automatically. The original kind 80/443 mappings remain unused. Production requires a trusted issuer, an external entry point, and authentication.

## ADR-003: Helm plus Kustomize

**Status:** implemented. **Decision:** Helm packages the reusable shop application; Kustomize overlays change replicas, resources, hostnames, and image references. **Why:** templates stay in one place while environment deltas remain reviewable YAML. **Consequence:** CI checks the committed Helm render for drift. Argo CD owns application reconciliation from phase 8; Helm owns controller releases. Environments target separate clusters.

## ADR-004: Argo CD instead of Flux

**Status:** implemented in phase 8. **Decision:** use Argo CD and its app-of-apps pattern. **Why:** the application tree and health model make ownership, reconciliation, and deployment state directly inspectable during release validation. **Consequence:** a slim local installation reconciles platform configuration and shop; pinned controller Helm releases remain an explicit bootstrap boundary. Automatic pruning is disabled to protect local data. See [GitOps ownership and delivery](gitops.md).

## ADR-005: default-deny NetworkPolicies

**Status:** accepted and implemented. **Decision:** deny all ingress and egress in `shop`, then permit DNS and workload-specific API/worker connections to PostgreSQL/Redis. **Why:** allowed communication becomes auditable and lateral movement is constrained. **Consequence:** every new external dependency requires an explicit policy change, and the cluster CNI must enforce NetworkPolicy.

## ADR-006: credentials are runtime inputs

**Status:** accepted and implemented. **Decision:** keep credentials outside Git and create `shop-runtime` from ignored `.env` during deployment. **Why:** base64 Kubernetes Secret manifests are not encryption. **Consequence:** `make init-env` generates local credentials without overwriting existing values. The dummy SOPS example illustrates encryption but does not manage live decryption or key rotation.

## ADR-008: bounded v1.0 release

**Status:** accepted for v1.0. **Decision:** ship a local reference platform with a tagged, reproducible GitOps source and explicit operational limits. **Why:** a fresh install and recovery evidence define a useful finish line without adding cloud services or pretending single-instance data stores are highly available. **Consequence:** release installation pins all Application revisions; following main is an explicit choice. Backup restores target a new database, and failure drills are restricted to a disposable release cluster. Advanced promotion, availability, and alerting remain optional backlog items.
