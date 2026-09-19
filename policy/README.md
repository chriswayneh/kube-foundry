# Policy

Phase 6 installs Kyverno chart 3.9.1 (controller v1.19.1) and two CEL `NamespacedValidatingPolicy` resources scoped to `shop`.

- `shop-workloads` validates Pods and automatically generated rules for Deployments, StatefulSets, DaemonSets, Jobs, and CronJobs. Background reporting is enabled.
- `shop-ephemeral-containers` validates the ephemeral-container subresource. Background reporting is disabled because that subresource cannot be listed independently.

Both deny unversioned and `:latest` images, require explicit non-root container settings, require named service accounts with token automount disabled, and require CPU/memory requests and limits for regular and init containers. Ephemeral containers cannot declare resources in Kubernetes, so their images and security settings are checked without resource requirements. SHA256 image digests are accepted. A version tag alone is not an immutable supply-chain guarantee.

Policies use `failurePolicy: Fail` and `validationActions: [Deny, Audit]`. Restricted Pod Security Admission on the namespace independently rejects privileged workloads and other unsafe Pod settings.

```sh
make deploy-phase6                 # uses .env for the runtime Secret
make deploy-phase6 REUSE_SECRET=true  # preserves an existing shop-runtime Secret
make security-check
make smoke-traffic
```

The check script uses server-side dry-runs for allowed and denied Pod, controller, and ephemeral-container cases. It also checks RBAC impersonation and verifies live containers have no service-account token file. Run it with a cluster-admin development context; it needs impersonation, server dry-run, and exec permissions. It creates no test workloads and does not inject a debug container.

The local Kyverno setup runs one admission replica and one reports replica. Background mutation/generation and cleanup controllers are disabled because these policies do not use them. It is not highly available; an admission-controller outage can block matching workload writes. Existing running Pods are not evicted by these policies.

For a failed rollout, inspect the rejected resource and `kubectl -n shop get namespacedvalidatingpolicies -o yaml`, then fix the manifest. Check controller health with `kubectl -n kyverno get pods`. Do not disable enforcement to bypass a policy violation. Namespace administrators who can change policies or RBAC remain trusted; these controls are not a boundary against cluster-admin.

[Kyverno CEL policy documentation](https://kyverno.io/docs/guides/migration-to-cel/) and [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).
