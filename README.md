# kube-foundry

A small Kubernetes platform I'm building on top of kind.

The app is intentionally simple: a FastAPI service, a worker, PostgreSQL, Redis, and a tiny web frontend. The interesting part is everything around it: cluster networking, persistence, probes, policies, packaging, observability, and eventually GitOps.

It's still under construction. I keep adding one layer at a time and try to leave the cluster working after each change.

## What's running now

- A three-node kind cluster with Cilium
- FastAPI endpoints for items and background jobs
- A Redis queue and Python worker
- PostgreSQL and Redis with persistent volumes
- Startup, liveness, and dependency-aware readiness probes
- Default-deny network policies with explicit API/worker data paths
- Envoy Gateway routing for the web frontend and API
- Local HTTPS certificates issued and renewed by cert-manager
- A shared Helm chart with dev, staging, and prod Kustomize overlays
- Dedicated service accounts, scoped observer RBAC, restricted Pod Security, and Kyverno admission policies
- Multi-stage, non-root containers with pinned versions
- A few smoke and failure tests so I can tell when I break something

```mermaid
flowchart LR
    Client --> Gateway[Envoy Gateway HTTP/HTTPS]
    Gateway --> Web[Web frontend]
    Gateway --> API[FastAPI API]
    API --> PG[(PostgreSQL)]
    API --> Redis[(Redis queue)]
    Redis --> Worker[Python worker]
    Worker --> PG

    subgraph kind[kind cluster]
      subgraph shop[shop namespace]
        API
        Worker
        PG
        Redis
      end
    end
```

The frontend and API share `shop.localhost`. Envoy routes `/api` to FastAPI and `/` to the frontend.

## Run it

You'll need Docker, kind 0.33.0, kubectl, Helm 3.22.0, GNU Make, Python 3, and `curl`. On Windows, run the Make targets from WSL or Git Bash.

```bash
cp .env.example .env
# replace the placeholder passwords in .env

make cluster
make build
make load
make deploy-phase6
make security-check
make smoke
make smoke-traffic
make status
make gateway-access
```

With `make gateway-access` running, open `http://shop.localhost:8080` or `https://shop.localhost:8443`.
The HTTPS certificate is self-signed for local development, so browsers will show a trust warning.
See [host access and TLS verification](docs/traffic.md) for certificate verification and Windows commands.

Clean it up with:

```bash
make cluster-delete
```

`.env`, rendered Secrets, tokens, and kubeconfigs do not belong in Git.

## Things I've tested so far

- Item CRUD works through the API
- Jobs make it through Redis and complete in the worker
- PostgreSQL data survives deleting and recreating its Pod
- The API goes unready when its dependencies fail
- An unlabeled Pod can't connect to PostgreSQL through the default-deny policies
- The Kubernetes manifests pass strict 1.37 schema validation
- HTTP and HTTPS serve the frontend and API through Envoy
- TLS verification succeeds with the generated public certificate
- Item creation and background jobs work through HTTPS
- Unknown hosts and unknown API paths return 404

The exact commands and failure notes are in [docs/failures.md](docs/failures.md). Architecture notes and tradeoffs are in [docs/architecture.md](docs/architecture.md) and [docs/decisions.md](docs/decisions.md).

## Roadmap

- Prometheus, Grafana, autoscaling, and disruption budgets
- Argo CD and a small GitHub Actions pipeline

The rough build checklist is in [docs/phases.md](docs/phases.md). It will probably move around as the project does.

Chart usage, environment differences, and clean-cluster setup are in [docs/packaging.md](docs/packaging.md).

## License

MIT
