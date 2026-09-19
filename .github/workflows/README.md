# Workflows

`ci.yaml` validates pull requests and builds/scans all three application images without publishing. It also provides reusable validation for the main-branch workflow.

`gitops-image-update.yaml` validates main, builds and scans each image, publishes commit-SHA tags to GHCR, verifies anonymous pulls, and commits all three immutable digests to the dev overlay. A failed scan, private package, or stale source revision prevents the overlay update.

See [delivery setup and troubleshooting](../../docs/gitops.md).
