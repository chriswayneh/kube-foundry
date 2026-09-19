"""Resolve public GHCR images first, then atomically replace the dev overlay."""

import argparse
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


COMPONENTS = ("api", "worker", "web")
OWNER = "chriswayneh"
OVERLAY = Path(__file__).resolve().parents[1] / "gitops/apps/shop/phase8/dev/kustomization.yaml"


def public_digest(component, revision):
    repository = f"{OWNER}/kube-foundry-{component}"
    query = urllib.parse.urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
    # No local Docker credentials or GitHub token: kind must be able to pull anonymously.
    with urllib.request.urlopen(f"https://ghcr.io/token?{query}", timeout=30) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        f"https://ghcr.io/v2/{repository}/manifests/{revision}",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.oci.image.index.v1+json, "
                           "application/vnd.oci.image.manifest.v1+json, "
                           "application/vnd.docker.distribution.manifest.v2+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        digest = response.headers.get("Docker-Content-Digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(f"Invalid registry digest for {component}")
    return digest


def render(revision, resolve=public_digest):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected a full lowercase Git commit SHA")
    lines = ["apiVersion: kustomize.config.k8s.io/v1beta1", "kind: Kustomization",
             "resources:", "  - ../../phase7/dev", f"# Source commit: {revision}", "images:"]
    for component in COMPONENTS:
        digest = resolve(component, revision)
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid digest for {component}")
        lines.extend([f"  - name: kube-foundry-{component}",
                      f"    newName: ghcr.io/{OWNER}/kube-foundry-{component}", f"    digest: {digest}"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        content = render(args.revision)
    except (urllib.error.URLError, ValueError, KeyError) as error:
        raise SystemExit(
            f"Image resolution failed ({type(error).__name__}); overlay left unchanged.\n"
            "For each api/worker/web package: GitHub profile > Packages > kube-foundry-<component> "
            "> Package settings > Change visibility > Public.\n"
            "Confirm Actions has package write permission, then rerun the Publish and deploy workflow.\n"
            "See docs/gitops.md. No registry credentials belong in Git."
        ) from None
    temporary = OVERLAY.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(OVERLAY)
    print("Updated dev overlay with three anonymously verified image digests.")


if __name__ == "__main__":
    main()
