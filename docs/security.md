# Security model

## Trust boundaries and assets

The public Git repository and built images are untrusted inputs until reviewed. The local workstation, Docker daemon, and kind control plane are trusted for development. Data and credentials inside `shop` are protected assets; the API is the only client-facing workload.

## Implemented controls (phases 1-3)

- Real credentials and kubeconfigs are excluded from Git. `make secret` creates `shop-runtime` from ignored `.env` at runtime.
- Every image uses an explicit version; the kind node image is pinned by tag and digest.
- API and worker run as UID/GID 10001, disallow privilege escalation, drop all capabilities, use `RuntimeDefault` seccomp, and mount a read-only root filesystem with a writable `/tmp` only.
- CPU/memory requests and limits bound accidental resource consumption.
- Namespace-wide ingress and egress are denied. DNS is explicitly allowed. PostgreSQL and Redis accept network traffic only from the API and worker; those are the only workloads permitted to initiate connections to the data stores.
- Readiness fails closed when PostgreSQL or Redis is unavailable.

Live verification on 2026-09-17 confirmed the API and worker could reach both stores while an unlabeled Pod in `shop` timed out connecting to PostgreSQL port 5432 under the same policies.

kindnet does not enforce NetworkPolicy. `cluster.yaml` therefore disables the default CNI, and `make cluster` installs the Cilium 1.20.2 Helm chart before waiting for nodes. This makes the committed NetworkPolicies enforceable rather than documentary.

## Threats and roadmap controls

| Threat | Current mitigation | Planned phase 6+ control |
|---|---|---|
| Workload token theft | Application code never reads Kubernetes APIs | Dedicated ServiceAccounts, token automount disabled, namespace Role/RoleBinding |
| Lateral movement | Default-deny plus port- and label-scoped policies | Kyverno validation and restricted Pod Security Admission |
| Secret disclosure | No credentials in Git; runtime-created Secret | SOPS or Sealed Secrets, documented rotation, external manager in production |
| Malicious image | Exact tags, non-root runtime | Trivy in CI, digest updates, signing/admission in production |

## Credential rules

Never commit `.env`, rendered Secrets, tokens, private keys, kubeconfigs, or command output containing them. If a credential is exposed, revoke/rotate it before removing it from history. Placeholder values must be unmistakably non-production.
