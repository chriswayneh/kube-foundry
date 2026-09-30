# Changelog

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
