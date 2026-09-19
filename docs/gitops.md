# GitOps and delivery

Phase 8 introduces Argo CD and a repository-to-cluster delivery path. It targets the local development cluster; staging and production profiles are not automatically promoted.

## Ownership and bootstrap

The bootstrap boundary is deliberate. Helm installs pinned platform controllers and their CRDs: Cilium, Envoy Gateway, cert-manager, Kyverno, monitoring, Metrics Server, and Argo CD. Argo does not take over those Helm releases. Controller upgrades remain explicit Make operations. Argo CD chart 10.9.2 installs Argo CD v3.5.3 with a single controller/server/repository server, Redis, and no active Dex, notifications, or ApplicationSet controller.

The root Application reads the explicit Kustomization at `gitops/`, not a recursive directory scan:

```text
kube-foundry
  platform: GatewayClass, Grafana dashboard, Kyverno policies
  shop-dev: phase 8 overlay -> phase 7 resources -> shared chart render
```

AppProjects allow only this repository, the local cluster, and the required resource kinds/namespaces. Projects and the root Application are bootstrapped outside their child sources. Argo's controller itself still has broad cluster privileges; project allowlists do not make untrusted repository writers safe. Protect main and review manifest changes.

On a new cluster, prepare `.env` with local credentials, then run:

```bash
make cluster
make build
make load
make deploy-phase7
make deploy-phase8
make smoke-traffic
```

For the existing phase 7 cluster, run only `make deploy-phase8`. It preserves the runtime Secret and existing PVCs. The source paths must already exist on GitHub main. On forks, replace the repository URLs, project source allowlists, and image owner before bootstrapping.

Once Argo owns shop, use Git to change it. Do not reapply earlier phase overlays or use `kubectl set image` as a release mechanism. Platform-only Make targets remain available for controller maintenance.

## Delivery path

1. A pull request runs YAML/Python lint, updater unit tests, Helm drift checks, all Kustomize renders, and three image builds with Trivy 0.74.0 vulnerability scans. Helm templates are validated by Helm rather than treated as plain YAML; generated YAML is linted with its generated indentation preserved.
2. A main push runs the same static validation, then builds and scans each image. Any HIGH or CRITICAL vulnerability blocks that image's publication, including findings with no available fix. This is a dependency/OS vulnerability gate, not a full source security audit.
3. Successful images publish to `ghcr.io/chriswayneh/kube-foundry-{api,worker,web}:<full-commit-sha>` using the job-scoped `GITHUB_TOKEN`.
4. Only after all three jobs pass, the update job resolves their manifests anonymously and writes their SHA-256 digests to `gitops/apps/shop/phase8/dev/kustomization.yaml`. All three digests change in one commit. Private or missing images leave the overlay unchanged.
5. Argo polls main and reconciles the new digests. API HPA replica ownership is preserved by omitting replicas and respecting Argo's replica ignore rule.

Actions are pinned by commit SHA. PR validation has read-only repository access. Package write permission exists only in the main publication jobs; repository write permission exists only in the update job. No PAT, registry password, kubeconfig, or cluster access is passed to CI. Main-only dispatch is supported. Delivery is serialized, stale revisions are rejected, pushes are never forced, and bot overlay commits do not recursively publish images.

The initial phase 8 overlay retains local `0.1.0` images until the first complete publication. API/worker builds now use Python 3.13.15 on Alpine 3.24: the previous Bookworm runtime had high/critical OS findings, and the Trivy gate was not weakened to pass them. Unneeded pip and ensurepip installers are removed from the runtime after dependencies are installed, eliminating their vulnerable bundled dependencies. Base and dependency scans must keep passing as advisory data changes.

## First GHCR publication and authentication

GitHub creates new packages as private even for a public repository. A successful push alone is not sufficient for an anonymous kind pull.

If the update job reports that images cannot be pulled publicly:

1. Open your GitHub profile's **Packages** tab.
2. Open each of `kube-foundry-api`, `kube-foundry-worker`, and `kube-foundry-web`.
3. Choose **Package settings**, then **Change visibility**, then **Public**, and confirm the package name.
4. Under **Manage Actions access**, ensure `chriswayneh/kube-foundry` has write access when reusing a pre-existing package.
5. Open repository **Actions**, select **Publish and deploy**, then **Run workflow** on main. If main has not changed, rerunning the failed update job is sufficient.

The workflows request the permissions they need. If an organization policy blocks package writes or branch rules block the bot commit, do not weaken those rules or force-push. Grant the approved package access or change delivery to a reviewed promotion PR. The failed job leaves the previous deployment in place.

No personal GHCR token is required for this workflow. For a private-registry variant, provision an image-pull Secret outside Git and explicitly redesign the anonymous-pull check; this repository intentionally uses public images.

## Access and verification

```bash
make argocd-access
make gitops-check
make security-check
make monitoring-check
make smoke-traffic
```

Open `https://127.0.0.1:8081` while the loopback port-forward runs. Argo's local certificate is self-signed. The initial username is `admin`; retrieve its password locally from `argocd-initial-admin-secret` in namespace `argocd`. Do not put it in Git or shared logs. Change the initial password before sharing access. Production would require SSO, restricted admin access, trusted TLS, controller isolation, backups, and reviewed promotions.

`gitops-check` requires the root, platform, and shop-dev Applications to be both Synced and Healthy. That does not replace application smoke tests or prove that a new image has been published: inspect the live Deployment image digests and the workflow result too.

Automatic sync and self-healing are enabled; automatic pruning and cascading Application deletion are deliberately absent. Removing a manifest from Git does not delete the live resource. Review removals manually, especially namespaces and persistent storage. To roll back an image, revert the digest-update commit and let Argo reconcile it. A Git rollback is not a database restore and may be incompatible with future schema changes.

## Verification record

On 2026-09-19, [GitHub delivery run 35465793504](https://github.com/chriswayneh/kube-foundry/actions/runs/35465793504) passed validation, all three builds/scans/publications, anonymous manifest access, and the digest-update commit. Argo reconciled delivery commit `667b2da21ea202253646320f366b2c7b44a84063`; live API, worker, and web Deployments used the published GHCR digests. Root and child Applications reached Synced/Healthy. A deliberate web replica change from two to three was automatically corrected to two. HTTPS application smoke tests, security checks, and monitoring checks were exercised against the new runtime.

References: [Argo automated sync](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/), [resource tracking](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_tracking/), and [GHCR access and visibility](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
