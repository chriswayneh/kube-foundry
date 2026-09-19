# Backup and recovery

The v1.0 recovery tools are designed to prove recovery without overwriting the running application database. Use an explicit context for every backup or restore.

## Logical database backup

```bash
python scripts/database.py --context kind-kube-foundry backup --output backups/shop-before-upgrade.dump
```

The command runs PostgreSQL 17's `pg_dump` inside the existing database Pod and streams a custom-format archive to an exclusively created local file. It prints a SHA-256 checksum, not the contents or credentials. The dump contains application data and must remain private. `backups/` and `*.dump` are ignored by Git. A failed command can leave an incomplete file; do not treat it as a usable backup or overwrite it silently.

This is a manual snapshot of one database. It does not back up cluster roles, Kubernetes Secrets, Redis queues, persistent-volume internals, or the entire cluster. There is no scheduled backup service, encryption-at-rest guarantee for the local file, or defined recovery-point objective. Keep encrypted copies off-host for real data and test them periodically.

## Restore into a new database

```bash
python scripts/database.py --context kind-kube-foundry restore \
  --input backups/shop-before-upgrade.dump --database restore_review
```

Only names beginning with `restore_` and containing safe lowercase characters are accepted. `createdb` fails if that database already exists. The tool restores in a single transaction and never drops or cleans the original database. The app continues to use its original database. A failed restore may leave an empty destination database, which should be inspected before manual removal.

Restore only archives from trusted sources: PostgreSQL restore can execute SQL/code from the backup. Validate checksums against your own trusted record before restoration. The tools intentionally do not automate production data replacement or secret changes.

After verification, a real cutover would require a maintenance window, stopping writes and worker processing, reconciling Redis job state, updating the database connection, and running application checks. That cutover is not included in the non-destructive v1.0 drill. Existing jobs can otherwise become inconsistent with the queue.

## Acceptance drill

Run only on the disposable cluster after the smoke test has created at least one item and completed job:

```bash
python scripts/check-backup.py --context kind-kube-foundry-release
```

This fingerprints all ordered item/job rows, creates a dump, restores it into a new timestamped database, and compares the restored fingerprints to the unchanged source. It retains the local dump and separate database for inspection. Removing the disposable cluster later removes its databases, but not the local dump.

## Failed image rollout

```bash
python scripts/check-recovery.py --context kind-kube-foundry-release
```

The drill saves the known-good Application source, temporarily pauses root auto-sync, and sets a child Application image override to an explicitly nonexistent tag. It requires an actual image-pull failure while at least two known-good API replicas remain available. A `finally` block restores the original source and root automation, then waits for the known-good image and healthy Argo status.

This is an Argo parameter-override rollback exercise, not a production Git revert or database rollback. It publishes no deliberately broken commit. If the process or host is forcibly terminated before cleanup, explicitly resume root automation in the disposable cluster, then restore the reviewed source:

```bash
kubectl --context kind-kube-foundry-release -n argocd patch application kube-foundry --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"enabled":true}}}}'
python scripts/bootstrap-gitops.py --revision v1.0.0
make verify
```

Use the disposable cluster's kubeconfig for all three commands. Never run the drill against a live service.

References: PostgreSQL [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html) and [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
