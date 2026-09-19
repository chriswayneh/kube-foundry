# Observability and scaling

Phase 7 adds application metrics and bounded CPU autoscaling without changing the application images or existing data volumes.

## Deploy and verify

After the cluster, images, and runtime credentials are prepared:

```bash
make deploy-phase7
make monitoring-check
make scaling-check
make smoke
make smoke-traffic
```

For an existing cluster whose `shop-runtime` Secret is already provisioned, use `make deploy-phase7 REUSE_SECRET=true`. This preserves the existing credentials. Use `ENVIRONMENT=staging` or `ENVIRONMENT=prod` only against that environment's separate cluster. These profiles are not a claim of production readiness.

The deployment installs pinned kube-prometheus-stack 91.4.1 and Metrics Server chart 3.14.0, then applies `gitops/apps/shop/phase7/<environment>`. These wrappers retain the earlier environment overlays and add monitoring, scaling, and disruption resources. Do not reapply a pre-phase-7 overlay afterward: its explicit API replica count conflicts with the HPA.

## Local access

Run each port-forward in a separate terminal:

```bash
make grafana-access
make prometheus-access
```

Grafana is at `http://127.0.0.1:3000`; Prometheus is at `http://127.0.0.1:9090`. Both Services remain ClusterIP and forwards bind only to loopback. Prometheus has no application authentication: do not expose its port externally.

Grafana's generated credentials are in the `monitoring-grafana` Secret in namespace `monitoring`, under `admin-user` and `admin-password`. Retrieve and decode them locally with an authorized Kubernetes client. Never paste them into Git, screenshots, or shared logs.

The **kube-foundry / Shop** dashboard is provisioned from `gitops/platform/monitoring/shop.json`. Its eight panels cover replicas, scrape health, request rate, p95 latency, server errors, process memory, HPA desired replicas, and allowed disruptions. Request-rate and latency panels select `/api/` traffic rather than probe traffic. Generate requests with the smoke tests; empty latency data while idle is expected. Process memory is not total container memory.

## Resource footprint and boundaries

- Prometheus retains up to 24 hours of samples, with an 800 MB retention-size limit and a 1 GiB local PVC. Cluster deletion removes local storage; this is not a backup or durable monitoring service.
- Alertmanager, default alert rules/dashboards, node exporter, and control-plane/kubelet scrapes are disabled. This is application-focused monitoring, not full cluster coverage or paging.
- Grafana is ephemeral. Dashboard and datasource provisioning are reproducible from configuration; manual UI changes are not durable.
- kube-state-metrics provides workload, HPA, and disruption-budget state.
- Only Prometheus-labeled Pods in namespace `monitoring` gain ingress to API TCP port 8000. NetworkPolicy restricts ports, not HTTP paths; this permission reaches more than `/metrics`. Existing default-deny policies remain in place.
- Metrics Server uses `--kubelet-insecure-tls` for kind's local kubelet certificates. This is a development-only exception. Its aggregated API uses a chart-generated certificate and CA verification, not `insecureSkipTLSVerify`. Use trusted kubelet certificates outside this local setup.

## Scaling and maintenance

| Profile | API minimum / maximum | Web replicas |
| --- | --- | --- |
| dev | 2 / 4 | 2 |
| staging | 2 / 5 | 2 |
| prod | 3 / 6 | 3 |

The API HPA targets 60% CPU utilization relative to requests. Scale-up allows two additional Pods per 30 seconds; scale-down uses a 60-second stabilization window and removes at most one Pod per 30 seconds. Prometheus does not drive this HPA: Metrics Server does. The phase 7 render removes `Deployment.spec.replicas` for API so subsequent applies leave replica ownership to the HPA.

All five workloads have `minAvailable: 1` disruption budgets. Redundant API and web Pods can permit voluntary evictions. Singleton PostgreSQL, Redis, and worker budgets deliberately block eviction during node drain. They do not create high availability, protect against node failure, block direct Pod deletion, or govern Deployment rolling updates. Plan explicit maintenance and recovery for singleton workloads rather than forcing a drain and assuming the budgets preserve service. There are no cross-node placement guarantees.

`make monitoring-check` verifies live API scrape targets, application and cluster metrics, HPA metric availability, Grafana health, the provisioned dashboard/datasource, and eviction admission. Evictions use server-side dry-run and do not remove Pods.

`make scaling-check` adds 90 seconds of bounded CPU load to one API Pod, verifies scale-up, then waits for ready replicas to return to the configured minimum. Run only on an idle local cluster. It changes replica count temporarily and can affect latency; it is not a throughput benchmark.

## Verification record

Verified on the local three-node kind cluster on 2026-09-19: healthy API scrape targets, populated results for all eight dashboard queries, Grafana dashboard and datasource provisioning, CPU-driven scale-up from two to four replicas and recovery to two, permitted API eviction dry-run, and denied database eviction dry-run. The complete deployment was reapplied successfully with existing credentials. All three environment profiles passed server-side dry-run; security checks and direct/HTTPS application smoke tests passed.

References: [HPA behavior](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/), [disruption budgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/), and [Metrics Server requirements](https://github.com/kubernetes-sigs/metrics-server).
