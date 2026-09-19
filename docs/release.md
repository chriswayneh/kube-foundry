# v1.0 release and operations

## Release contract

kube-foundry v1.0 is a local Kubernetes reference platform. It provides a repeatable three-node kind environment for application delivery, policy validation, monitoring, and recovery exercises. It does not provide a hosted service, authenticated application users, cloud infrastructure, or production availability guarantees.

The supported release path uses Docker Linux containers, kind 0.33.0, Kubernetes/kubectl 1.37.0, Helm 3.22.0, Python 3.13+, GNU Make, Git, and curl. Windows acceptance uses Docker Desktop, Python 3.14, and Git Bash with native tools; CI checks scripts on Python 3.13. Linux/WSL use the same Bash targets but were not separately cluster-acceptance-tested for this release. Allow 16 GB of Docker memory and free disk space for images and volumes. Registry and GitHub access are required.

## Install and verify

From the tagged checkout:

```bash
make init-env
make cluster
kubectl config current-context
make install GITOPS_REVISION=v1.0.0
make gateway-access
```

Before installation, confirm the context is `kind-kube-foundry` or the explicitly selected disposable cluster. `make install` targets the active kubeconfig; never point it at an unrelated/shared cluster. `init-env` generates random local credentials, creates a private file on systems supporting POSIX permissions, and refuses to overwrite an existing file. Protect the file with your workstation's access controls on Windows.

Installation bootstraps the pinned controllers, applies the root Application, and runs `make verify`. The root adds Kustomize patches that pin both child Applications to the chosen revision. Argo fetches published images by digest; local Docker builds are not required. The release tag freezes repository configuration and image references, not upstream registries or vulnerability advisory databases. Future scans can discover new findings in a previously released image.

For an existing instance, retain its credentials. If the original `.env` is unavailable, use `REUSE_SECRET=true`; do not generate replacement passwords against existing database volumes.

`make verify` runs GitOps health, admission/RBAC/token checks, metrics/dashboard checks, eviction dry-runs, and HTTPS item/job smoke tests. Smoke tests create identifiable sample items and jobs. Scaling tests are separate because they deliberately add CPU load.

## Isolated acceptance cluster

Keep the main cluster and its current context untouched by using a separate kubeconfig. The verification topology uses the same three nodes but omits the historical, unused host 80/443 mappings.

```bash
mkdir -p .tools
export KUBECONFIG="$PWD/.tools/release-kubeconfig"
# With native Windows binaries in Git Bash, use a Windows path instead:
# export KUBECONFIG='C:/dev/kube-foundry/.tools/release-kubeconfig'
make init-env ENV_FILE=.tools/release.env
make cluster CLUSTER_NAME=kube-foundry-release CLUSTER_CONFIG=clusters/kind/verification.yaml
make install ENV_FILE=.tools/release.env GITOPS_REVISION=v1.0.0
python scripts/check-recovery.py --context kind-kube-foundry-release
python scripts/check-backup.py --context kind-kube-foundry-release
make verify
```

The failure drills refuse any context name other than `kind-kube-foundry-release`. Do not rename a valuable cluster to bypass that guard. A second full cluster needs additional resources; run acceptance on a separate host if necessary. On repeated runs, reuse your existing private credentials file instead of rerunning `init-env`, which intentionally refuses to replace it.

## Upgrade and rollback

1. Read the target release notes, including controller/CRD compatibility and data changes.
2. Back up the application database using the [recovery runbook](recovery.md); verify a restore and protect the dump.
3. Check out the reviewed release tag. Keep `.env`, the existing Secret, and PVCs intact.
4. Run `make install GITOPS_REVISION=<reviewed-tag> REUSE_SECRET=true`, then `make verify`.

Controller upgrades are explicit Helm operations within the installer. There is no promise that arbitrary future controller downgrades or data-schema downgrades are safe. For an application-only rollback, restore a reviewed GitOps revision with `python scripts/bootstrap-gitops.py --revision <known-good-revision>`, then verify. This does not downgrade controllers or restore the database.

To intentionally follow development again, use `python scripts/bootstrap-gitops.py --revision main`. That opts into future main-branch GitOps changes. Do not follow main for a frozen acceptance environment.

## Teardown

Stop any port-forwards first. Back up required data before deleting a cluster:

```bash
make cluster-delete CLUSTER_NAME=kube-foundry-release  # disposable acceptance cluster only
# make cluster-delete CLUSTER_NAME=kube-foundry     # main cluster, only when intentionally retiring it
```

Cluster deletion removes the cluster's local PostgreSQL, Redis, and Prometheus volumes. There is no undelete operation; recovery requires a retained backup and separately retained credentials. Local `.env` and files under `backups/` are not deleted by Make. Store sensitive backups outside the repository and encrypt them before sharing or moving off-host.

## Acceptance record

Release acceptance was exercised on 2026-09-19 using a new `kube-foundry-release` cluster and independent credentials. No existing development PVC was reused. The clean bootstrap first pinned root and child Applications to known-good source `f2b408061a0669423767137b92713688be48b229`, using the release installer in this checkout. The final release candidate is then re-pinned and verified before tagging.

| Check | Outcome |
| --- | --- |
| Fresh three-node cluster and published-image install | Passed without local image loading |
| Root and all child source revisions | Pinned to the requested commit; Synced/Healthy |
| Security, RBAC, API token isolation, and admission | Passed |
| Prometheus, Grafana, HPA metrics, and eviction dry-runs | Passed |
| HTTPS routing, certificate verification, items, and jobs | Passed |
| Deliberately unavailable API image | Pull failure observed; at least two healthy API replicas remained |
| Restore known-good Application source | Healthy image restored and root automation resumed |
| PostgreSQL backup and separate-database restore | Every ordered item/job row matched; source unchanged |
| Original development cluster | Default context and PostgreSQL/Redis PVC identities preserved |
| Browser screenshots | Actual Argo/Grafana pages visually checked; credentials excluded |

The fresh install exposed optional Grafana plugin downloads during startup. The release disables those downloads, and the resulting fresh Grafana Pod reached readiness without a restart. Unit coverage includes safe restore names, archive streaming, revision propagation, and refusal to overwrite credentials. These checks are acceptance evidence for the documented local setup, not a production availability benchmark.

## Screenshots

`docs/images/argocd.png` and `docs/images/grafana.png` are direct browser captures from the running development cluster on 2026-09-19. Argo shows all three Applications healthy and synced. Grafana shows the provisioned dashboard; bounded GET requests generated sample request/latency data. Screenshots contain no admin credentials, tokens, or database contents. They illustrate the development instance following main, not a separate hosted service.

## Troubleshooting

- **Pending Pods or slow startup:** inspect `kubectl get pods -A`, events, Docker memory/disk, and registry connectivity. Initial controller downloads can take several minutes.
- **Argo missing paths or revision:** verify the repository URL and that the requested Git tag/commit exists. A local-only commit cannot be fetched by Argo.
- **ImagePullBackOff:** verify the committed digest and anonymous GHCR access. Do not substitute `latest` or embed registry credentials in Git.
- **Credential mismatch:** preserve existing Secret values for initialized volumes; generating a new `.env` does not rotate an existing database password.
- **No latency data while idle:** send sample requests and wait for Prometheus's scrape interval. An idle histogram is not an application failure.
- **Port already in use:** stop the conflicting local forward. Do not bind admin interfaces to all host interfaces as a workaround.
