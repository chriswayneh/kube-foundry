"""Verify an exact Git revision, deployed digests, rollout, and ready API response."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import time

import yaml

from proof import CONTEXT, evidence, get, kubectl, require


def revision(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise argparse.ArgumentTypeError("Use the full reviewed Git commit SHA")
    return value


def expected_images(commit):
    source = subprocess.check_output(
        ["git", "show", f"{commit}:gitops/apps/shop/phase8/dev/kustomization.yaml"], text=True)
    images = yaml.safe_load(source)["images"]
    result = {}
    for component in ("api", "worker", "web"):
        matches = [image for image in images if image["name"] == f"kube-foundry-{component}"]
        require(len(matches) == 1, f"Expected one {component} image")
        image = matches[0]
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("digest", "")), "Digest required")
        result[component] = image["newName"] + "@" + image["digest"]
    return result


def app_matches(app, commit):
    status = app.get("status", {})
    sync = status.get("sync", {})
    sources = app["spec"].get("sources") or [app["spec"].get("source", {})]
    observed = sync.get("revisions") or [sync.get("revision")]
    return (all(s.get("targetRevision") == commit for s in sources)
            and len(observed) == len(sources) and all(r == commit for r in observed)
            and sync.get("status") == "Synced" and status.get("health", {}).get("status") == "Healthy")


def rollout_matches(deployment, image):
    desired = deployment["spec"].get("replicas", 1)
    status = deployment.get("status", {})
    return (desired > 0 and deployment["spec"]["template"]["spec"]["containers"][0]["image"] == image
            and status.get("observedGeneration", 0) >= deployment["metadata"]["generation"]
            and all(status.get(field, 0) == desired for field in
                    ("replicas", "updatedReplicas", "readyReplicas", "availableReplicas")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", choices=[CONTEXT], required=True)
    parser.add_argument("--revision", type=revision, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    with evidence(args.evidence, "gitops-revision", args.context) as report:
        images = expected_images(args.revision)
        report.update(revision=args.revision, expected_images=images)
        deadline = time.monotonic() + 300
        while True:
            apps = {name: get(args.context, "argocd", "application", name)
                    for name in ("kube-foundry", "platform", "shop-dev")}
            deployments = {name: get(args.context, "shop", "deployment", name) for name in images}
            report["observed_revisions"] = {
                name: app.get("status", {}).get("sync", {}).get("revisions")
                or [app.get("status", {}).get("sync", {}).get("revision")] for name, app in apps.items()}
            if (all(app_matches(app, args.revision) for app in apps.values())
                    and all(rollout_matches(deployments[name], image) for name, image in images.items())):
                break
            require(time.monotonic() < deadline, "Exact revision/digest rollout did not converge within 300s")
            time.sleep(5)
        # Execute in the selected cluster, not a possibly unrelated host port-forward.
        result = kubectl(args.context, "-n", "shop", "exec", "deployment/api", "--", "python", "-c",
                         "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/readyz',"
                         "timeout=10); raise SystemExit(0 if r.status == 200 else 1)")
        result.check_returncode()
        report.update(applications={name: "Synced/Healthy at " + args.revision for name in apps},
                      rollout="all desired replicas updated, ready and available", readiness_http=200)
    print(json.dumps({"status": "passed", "evidence": str(args.evidence)}))


if __name__ == "__main__":
    main()
