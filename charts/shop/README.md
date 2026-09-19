# Shop Helm chart

The chart packages web, API, worker, PostgreSQL, Redis, Services, NetworkPolicies, and local Gateway/TLS resources. Values configure images, stateless replicas, resources, storage sizes, hostname, controller namespace, and the existing Secret name. `values.schema.json` validates inputs.

Chart 0.3.0 adds dedicated ServiceAccounts, disables workload API token automount, and provides a namespace-scoped observer Role/RoleBinding. The Kustomize base applies restricted Pod Security labels; direct Helm users must label their namespace separately. Kyverno and its namespaced policies are installed by `make deploy-phase6`, outside the application chart.

One installation is supported per namespace. Stable resource names preserve the phase-4 Services, selectors, and PVCs during migration. The chart does not create credentials, namespaces, GatewayClass, or platform controllers. Install Cilium, Envoy Gateway, cert-manager, and `gitops/platform/gatewayclass.yaml` first, and provide a Secret matching `.env.example` in the application namespace.

The repository uses Helm as a renderer and Kustomize as the deployment layer:

```sh
make render-shop
make check-chart
make deploy-phase5 ENVIRONMENT=dev
```

Do not install a Helm release over the resources managed by `kubectl apply`. For a separate namespace managed exclusively by Helm, the same chart can be installed directly after provisioning its namespace and runtime Secret:

```sh
helm upgrade --install shop charts/shop --namespace shop-helm \
  --set gateway.hostname=shop-helm.localhost --wait --timeout 300s
```

PostgreSQL and Redis intentionally remain single replicas. PVC sizes are initial provisioning values, not an automated storage migration mechanism. Do not shrink PVCs or change a StatefulSet claim template in place. See [packaging and environments](../../docs/packaging.md).
