# Security model

## Trust boundaries and assets

The public Git repository and built images are untrusted inputs until reviewed. The local workstation, Docker daemon, and kind control plane are trusted for development. Data and credentials inside `shop` are protected assets; Envoy exposes the web frontend and API to local clients.

## Implemented controls

- Real credentials and kubeconfigs are excluded from Git. `make secret` creates `shop-runtime` from ignored `.env` at runtime.
- Every image uses an explicit version; the kind node image is pinned by tag and digest.
- API and worker run as UID/GID 10001, disallow privilege escalation, drop all capabilities, use `RuntimeDefault` seccomp, and mount a read-only root filesystem with a writable `/tmp` only.
- CPU/memory requests and limits bound accidental resource consumption.
- Namespace-wide ingress and egress are denied. DNS is explicitly allowed. PostgreSQL and Redis accept network traffic only from the API and worker; those are the only workloads permitted to initiate connections to the data stores.
- Readiness fails closed when PostgreSQL or Redis is unavailable.
- Each workload uses its own ServiceAccount, with API token automount disabled on both the account and Pod. Workload accounts receive no RoleBindings.
- A dedicated `shop-observer` ServiceAccount has namespace-only read access to workload status and logs. It cannot read Secrets, exec into Pods, change workloads, or read other namespaces.
- The `shop` Namespace enforces the restricted Pod Security standard pinned to v1.37, with matching audit and warning labels.
- Kyverno CEL policies enforce versioned images, explicit non-root settings, resource requests/limits, and disabled token automount. They cover Pod creation/updates, controller templates, and ephemeral-container admission.
- A dummy SOPS/age example demonstrates encryption without publishing or changing application credentials.
- Envoy proxy Pods are allowed to reach only the API and web workload ports in `shop`. Data-store access remains limited to the API and worker.
- The web container runs as UID/GID 101 with a read-only root filesystem, dropped capabilities, and writable `/tmp`.
- Host access uses a loopback-only port-forward. TLS uses a development self-signed certificate; no private keys are committed or installed into the host trust store.

Live verification on 2026-09-17 confirmed the API and worker could reach both stores while an unlabeled Pod in `shop` timed out connecting to PostgreSQL port 5432 under the same policies.

kindnet does not enforce NetworkPolicy. `cluster.yaml` therefore disables the default CNI, and `make cluster` installs the Cilium 1.20.2 Helm chart before waiting for nodes. This makes the committed NetworkPolicies enforceable rather than documentary.

## Threats and roadmap controls

| Threat | Current mitigation | Remaining work |
|---|---|---|
| Workload token theft | Dedicated accounts with no grants and no mounted API token | Short-lived, scoped credentials if API access is added |
| Lateral movement | Default-deny policies, restricted PSA, and Kyverno admission | Additional policy coverage as dependencies grow |
| Secret disclosure | Runtime Secret, no observer access to Secrets, dummy SOPS example | Managed encryption keys, rotation, and controlled GitOps decryption |
| Malicious image | Non-root runtime, Trivy high/critical gate, digest-pinned GitOps delivery | Signing, provenance enforcement, and production admission |

## Credential rules

Phase 6 verification on 2026-09-19 exercised allowed and rejected server-side admissions, namespace RBAC boundaries, and the absence of token files in all five workload containers. See [policy checks](../policy/README.md) and [the SOPS example](../examples/secrets/README.md). Kubernetes administrators can still read Secrets, change policy, or grant permissions; those identities remain trusted.

Never commit `.env`, rendered Secrets, tokens, private keys, kubeconfigs, or command output containing them. If a credential is exposed, revoke/rotate it before removing it from history. Placeholder values must be unmistakably non-production.
