# v1.1 operational proof

Three bounded workflows: promote reviewed image digests through Git, undo the promotion with a Git revert, and diagnose policy rejection and database recovery. No new platform controllers, application features, or production environments.

## Safety and prerequisites

Use the [isolated acceptance cluster](release.md#isolated-acceptance-cluster), independent credentials, and a separate kubeconfig. Never rename an important cluster to bypass the context guard. Scripts accept only `kind-kube-foundry-release` and record the `kube-system` namespace UID to distinguish clusters.

Install verification dependencies with `python -m pip install -r requirements-ci.txt`. Run from the repository root in Bash, WSL, or Git Bash. Keep the isolated kubeconfig selected for bootstrap and Make commands as well as explicit-context checks:

```bash
export KUBECONFIG="$PWD/.tools/v11-kubeconfig"
# Native Windows kubectl needs a Windows-style path, for example:
# export KUBECONFIG='C:/dev/kube-foundry/.tools/v11-kubeconfig'
kubectl config current-context   # must be kind-kube-foundry-release
```

Reports use exclusive creation: choose a new `PROOF_DIR` each run. Only `status: passed` is success; running, failed, missing, or invalid reports are not. Reports contain timestamps, cluster identity, revisions, digests, and row hashes/counts, not database rows or credentials. Treat hashes and infrastructure metadata as potentially sensitive and review before publication.

## 1. Git-backed promotion and rollback

The retained `codex/v1.1-promotion-proof` branch is an **exercise history, not a deployment branch for main**. Promotion changes only three image digests and their source-commit comment, using image sets previously published by the v1.0 workflow. No schema, controller, credential, or policy change is included. Do not merge this historical branch into main.

Fetch the proof branch and assign the full baseline, promotion, and rollback SHAs from the acceptance record to the variables below. The proof checker requires immutable full commit SHAs, not branch names.

```bash
git fetch origin codex/v1.1-promotion-proof
python scripts/bootstrap-gitops.py --revision "$BASELINE"
make operational-promotion GITOPS_REVISION="$BASELINE" PROOF_DIR=backups/proof-baseline
make smoke-traffic

python scripts/bootstrap-gitops.py --revision "$PROMOTION"
make operational-promotion GITOPS_REVISION="$PROMOTION" PROOF_DIR=backups/proof-promoted
make smoke-traffic

python scripts/bootstrap-gitops.py --revision "$ROLLBACK"
make operational-promotion GITOPS_REVISION="$ROLLBACK" PROOF_DIR=backups/proof-rollback
make smoke-traffic
```

Root revision selection is an explicit operator bootstrap operation. Argo reconciles the root and children from Git. This is single-cluster configuration promotion, not independently operated staging/production infrastructure or automatic environment promotion.

The checker requires all desired and observed Application commit SHAs to match, all expected Deployment digests to match Git, and every desired replica to be updated, ready, and available at the observed generation. It checks API readiness inside the selected cluster. The separate HTTPS smoke verifies certificate trust, routing, item creation, and background work. Stale Healthy status alone cannot pass.

For a new exercise, create a dedicated branch from a known-good configuration, commit only reviewed digest changes, push, and verify the full promotion SHA. Run `git revert <promotion-SHA>` on that branch, review/push the new commit, then select its SHA with bootstrap. Do not force-push, reset main, patch live Deployment images, or disable admission. Review compatibility first: Git revert is not database recovery or a safe controller downgrade.

If interrupted, select the last verified SHA and rerun its proof and HTTPS smoke. Root automation stays enabled; this flow uses no Argo image overrides.

## 2. Policy rejection and remediation

```bash
make operational-policy PROOF_DIR=backups/proof-policy
```

The script derives a test Deployment from the live API template, removes only its CPU limit, and submits a **server-side dry-run**. It requires the specific Kyverno `require-resources` denial, not a connection, authorization, or unrelated validation failure. It restores the CPU limit and requires successful server-side admission. Neither test Deployment is persisted: this proves admission remediation, not a second workload rollout.

For an actual rejection, inspect the admission message, correct the field in the workload's Git/Helm source, render/review, and commit for reconciliation. Do not weaken the policy. `make security-check` remains the broader admission, RBAC, and token-isolation suite.

## 3. Recovery evidence end to end

Run HTTPS smoke first, then stop other writers and wait for jobs to finish. The drill fails if source rows change during backup/restore rather than accepting a moving baseline.

```bash
make smoke-traffic
make operational-backup PROOF_DIR=backups/proof-recovery
make smoke-traffic
```

Read `backup.json` in the selected directory:

1. Confirm context, cluster UID, timestamps, and `status: passed`.
2. Locate the retained private `archive` and compare its SHA-256 with `archive_sha256`.
3. Check that `source_before`, `source_after`, and `restored` contain equal nonzero row counts and hashes for both `items` and `jobs`.
4. Inspect the named `restore_*` database if needed. The original database is never dropped or overwritten.
5. Confirm post-drill HTTPS smoke succeeds. `application_cutover: false` records that the application still uses the original database.

The restore tool accepts `--sha256 <trusted-checksum>` and rejects a mismatch before creating a destination database. The drill supplies its freshly recorded checksum automatically. Integrity is not authenticity: restore only trusted archives, which can contain executable SQL.

This proves logical row recovery into a separate database and continued operation of the original application. It does not prove application cutover, Redis queue restore, recovery of roles/secrets, off-host backup availability, or an RTO/RPO. Failed restores may retain an empty destination; failed backups may leave incomplete files. Keep and inspect evidence rather than overwriting it.

## Acceptance record

Live acceptance is pending. Release publication requires baseline, promotion, Git revert, policy-remediation, recovery evidence, and the full verification suite. Existing [v1.0 screenshots](release.md#screenshots) are dated illustrations of unchanged interfaces, not evidence of v1.1 execution.
