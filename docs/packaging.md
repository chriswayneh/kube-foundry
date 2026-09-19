# Packaging and environments

The Helm chart is the shared source for application resources. Its committed render in `gitops/apps/shop/base/shop.yaml` makes the result reviewable and lets Kustomize deploy it without Helm plugins. Dev, staging, and prod overlays carry only environment differences. Phase 1-4 manifests remain historical checkpoints; phase 5 no longer includes them as application bases.

## Environment profiles

| Overlay | Hostname | API / web replicas | API CPU / memory requests |
| --- | --- | --- | --- |
| dev | shop.localhost | 1 / 1 | 50m / 64Mi |
| staging | shop.staging.localhost | 2 / 2 | 75m / 96Mi |
| prod | shop.prod.localhost | 3 / 3 | 100m / 128Mi |

All profiles pin application images to `0.1.0`, preserve resource limits, and keep worker, PostgreSQL, and Redis at one replica. Image tags are explicit in each overlay so a later release pipeline can update them independently. Hostname patches keep Gateway listeners, HTTPRoute, and Certificate SANs aligned.

Each environment is intended for a separate cluster using the `shop` namespace. Applying another overlay to the same cluster replaces that cluster's profile; these are not three isolated installations within one cluster. `prod` is a configuration example, not a production readiness claim. Authentication, trusted certificates, backups, data-store availability, and later security controls remain necessary before real production use.

## Render, check, and deploy

```sh
make render-shop              # after editing chart templates or values
make check-chart              # Helm lint, render drift, all overlay renders
make deploy-phase5 ENVIRONMENT=dev
make smoke
make smoke-traffic
make gateway-access
```

`deploy-phase5` installs the pinned traffic controllers, provisions the runtime Secret from `.env`, applies the shared GatewayClass and selected overlay, and waits for workloads and TLS. It does not apply the phase-3 or phase-4 application manifests first. To use another ignored credentials file, set `ENV_FILE=/path/to/local.env`.

For another environment, set `ENVIRONMENT=staging` or `ENVIRONMENT=prod`. Use `SHOP_HOST=shop.staging.localhost make smoke-traffic` or `SHOP_HOST=shop.prod.localhost make smoke-traffic` respectively. The same hostname must be used in the browser with ports 8080/8443.

`make validate` also checks all earlier manifest phases. The runtime Secret is never part of the Helm render. Changes to ConfigMap content update the API Pod checksum annotation. Secret rotation still requires coordinated data-store credential changes and workload restarts.

## Migration from phase 4

Use the same `.env` credentials as the running stack. Do not generate new passwords against existing database volumes. Resource names, selectors, and PVC references stay stable, so applying the dev overlay preserves storage and data. The API rolls to pick up the chart's configuration checksum. If the original `.env` is unavailable, retain the existing `shop-runtime` Secret and apply the dev overlay directly after `make check-chart` and ensuring the platform controllers are installed.

Application resources are managed with `kubectl apply`; Helm manages only the platform controller releases in this workflow. Do not run `helm install shop` over the existing application namespace. The chart supports direct Helm installation into a separately provisioned namespace as documented in its README.

From phase 6 onward, `make deploy-phase6 REUSE_SECRET=true` reuses an existing runtime Secret without reading credentials back to disk. Use the normal `.env` path for a new cluster. Restricted namespace labels, service accounts, and observer RBAC are part of the shared application package; Kyverno installation and policies are handled by the phase-6 target.

## Clean-cluster verification

Use a separate kubeconfig and the verification topology to avoid altering the development cluster. It has the same three nodes and Cilium setup but no conflicting Docker host port mappings.

```sh
mkdir -p .tools
export KUBECONFIG="$PWD/.tools/phase5-kubeconfig"
# On Git Bash with Windows binaries, use a Windows path for KUBECONFIG instead.
make cluster CLUSTER_NAME=kube-foundry-phase5 CLUSTER_CONFIG=clusters/kind/verification.yaml
make build
make load CLUSTER_NAME=kube-foundry-phase5
make deploy-phase5 ENVIRONMENT=dev ENV_FILE=.tools/phase5.env
make smoke smoke-traffic
```

Create `.tools/phase5.env` from `.env.example` with fresh local test passwords before deployment. `.tools` is ignored by Git. After testing, `make cluster-delete CLUSTER_NAME=kube-foundry-phase5` removes the test cluster and its test data; then unset `KUBECONFIG` to return to the usual context.

## Verification record

Verified on 2026-09-19:

- `helm lint --strict`, render drift checks, all four earlier manifest renders, YAML lint for values/overlays, and shell syntax checks passed.
- Rendered dev resources matched phase 4 except for the API configuration checksum; all profiles preserved data-store and NetworkPolicy definitions.
- Custom namespace, hostname, Secret name, and replica values rendered correctly. Schema validation rejected zero API replicas.
- `make deploy-phase5 ENV_FILE=.tools/phase5.env` succeeded on a new three-node kind cluster with Cilium and freshly installed platform controllers.
- Dev passed direct API and HTTPS smoke tests. Staging and prod passed HTTPS item creation, listing, job completion, certificate verification, and unmatched-route tests with their respective hostnames.
- The existing development cluster was migrated to the dev overlay without replacing its PVCs. Its HTTPS smoke test passed after the API rollout.

## References

- [Helm chart values and schema validation](https://helm.sh/docs/topics/charts/)
- [Kustomize bases, overlays, replicas, and image transforms](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/)
