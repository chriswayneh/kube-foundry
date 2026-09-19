#!/usr/bin/env bash
set -euo pipefail
component=${1:?Usage: ci-image.sh api|worker|web scan|publish}
mode=${2:-scan}
case "$component" in api|worker|web) ;; *) exit 2 ;; esac
case "$mode" in scan|publish) ;; *) exit 2 ;; esac
revision=${GITHUB_SHA:-$(git rev-parse HEAD)}
owner=${GITHUB_REPOSITORY_OWNER:-chriswayneh}
owner=${owner,,}
image="ghcr.io/$owner/kube-foundry-$component:$revision"
docker build --pull --label "org.opencontainers.image.source=https://github.com/$owner/kube-foundry" \
  --label "org.opencontainers.image.revision=$revision" -t "$image" "app/$component"
# Scan the exact local image that will be pushed. Never ignore unfixed findings.
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:0.74.0 image --image-src docker --scanners vuln \
  --severity HIGH,CRITICAL --exit-code 1 --timeout 10m "$image"
if [ "$mode" = publish ]; then
  docker push "$image" || {
    echo 'GHCR push failed. Enable Actions write access to packages and grant this repository access to existing packages.' >&2
    echo 'See docs/gitops.md for authentication and first-publication steps.' >&2
    exit 1
  }
fi
