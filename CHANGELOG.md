# Changelog

## Unreleased

- API and worker database connections set `statement_timeout=5s` and `lock_timeout=2s` on every connection, including the worker schema setup and job claim (override with `PG_OPTIONS`, read the same way by both; see docs/architecture.md).
- `GET /api/items` is now paginated with `after_id` and `limit` (default 50, max 200). Behaviour change: callers that expected every item in one response must page (pass the last id as `after_id`; there is no next-page marker). The web UI gains a "Load more" button and the traffic smoke test looks its item up by id. See docs/architecture.md.
- Worker writes a heartbeat file each loop; the chart adds startup and liveness exec probes for it.
- Job creation no longer marks a job failed when the Redis push errors (the push may have landed); the request still returns 202 with the job `pending`, and the API re-enqueues pending jobs older than 30 seconds from a background sweep every 30 seconds (`JOB_DISPATCH_INTERVAL_SECONDS`). Known limit: each API replica runs its own sweep, so a stuck job can be pushed more than once; the worker's idempotent claim makes the duplicate a no-op.
- Worker no longer loses a job when the database fails after dequeue: jobs move to `jobs:processing` until complete, claims are idempotent, and orphans are requeued at startup; a DB error mid-job puts the job back on the queue. The worker is limited to one replica (`values.schema.json` `maximum: 1`, `Recreate` strategy). CI now runs the app unit tests.
- `scripts/database.py backup` creates the dump file with mode 0600 regardless of umask.
- Database and Redis passwords are no longer interpolated raw into connection URLs in the chart; the apps build URLs with proper quoting (`DATABASE_URL`/`REDIS_URL` still win if set). The phase 2 and phase 3 kind manifests no longer embed passwords either, and a missing `POSTGRES_*` or `REDIS_PASSWORD` variable fails with a clear error naming it.
- Unhandled API exceptions are now counted as status 500 in `http_requests_total` and latency.
- Unmatched request paths are recorded under one `__unmatched__` metrics label instead of one series per URL.
- Prepare development image promotions on reviewed branches instead of pushing protected main; reject stale or mixed-scope digest promotions without expanding workflow permissions.
- Add local 5-minute API reliability signals and Prometheus diagnostic alerts without introducing paging or a production SLO commitment.
- Permit PrometheusRule resources in the platform Argo project; handle low traffic, idle periods, client errors, and missing targets correctly.
- Evaluate deployed expressions with pinned promtool in CI, and reject missing or failed live rule evaluations.
- Give Grafana bounded startup/query headroom, offer the configured 15-second dashboard refresh interval, and verify both reliability panels through its datasource API.
- Retry transient monitoring socket timeouts within the existing deadline; these changes remain unreleased.
- State the live limits in the README: no application authentication, `shop`-only default-deny, unused all-interfaces kind host ports 80/443, no TLS on PostgreSQL or Redis, and operator acceptance records rather than an independent review.
- Refresh the web runtime's libx11 package (1.8.13 -> 1.8.14) to address CVE-2026-88806 (HIGH) found by the image scan; no scanner exceptions added.

## v1.1.0 - 2026-09-29

- Exact Git-revision and image-digest rollout verification for promotion and Git revert exercises.
- Server-side policy rejection/remediation without persisting test workloads.
- Exclusive timestamped JSON evidence with cluster identity and explicit pass/fail status.
- Optional trusted-checksum verification before restore, plus source/restored row counts and hashes.
- Operator guidance separating local proof from production promotion and data-cutover guarantees.
- Refresh the web runtime's libexpat package to address the high-severity finding detected during release validation.
- Verified the historical promotion/revert chain, policy remediation, and four-item/four-job restore on an isolated three-node cluster. See [acceptance evidence](docs/operational-proof.md#acceptance-record).

## v1.0.0 - 2026-09-19

- Released the local Kubernetes reference platform with GitOps, policy controls, monitoring, TLS, and isolated recovery verification.
- Published installation, operating guidance, screenshots, and explicit scope limitations.
