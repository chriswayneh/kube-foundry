"""Wait for all three GitOps applications to be synced and healthy."""

import argparse
import json
import subprocess
import time


def at_revision(application, revision):
    def matches(container):
        sources = container.get("sources") or [container.get("source", {})]
        return bool(sources) and all(source.get("targetRevision") == revision for source in sources)

    return (matches(application.get("spec", {}))
            and matches(application.get("status", {}).get("sync", {}).get("comparedTo", {})))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", help="Also require desired and observed source revisions to match")
    args = parser.parse_args()
    deadline = time.monotonic() + 300
    previous = None
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["kubectl", "--request-timeout=20s", "-n", "argocd", "get", "applications", "-o", "json"],
            text=True, capture_output=True, check=True,
        )
        resources = {item["metadata"]["name"]: item for item in json.loads(result.stdout)["items"]}
        apps = {name: item.get("status", {}) for name, item in resources.items()}
        expected = ("kube-foundry", "platform", "shop-dev")
        states = [(name, apps.get(name, {}).get("sync", {}).get("status", "Missing"),
                   apps.get(name, {}).get("health", {}).get("status", "Missing")) for name in expected]
        if states != previous:
            print("; ".join("/".join(state) for state in states), flush=True)
            previous = states
        revision_ready = not args.revision or all(
            at_revision(resources.get(name, {}), args.revision) for name in expected)
        if all(sync == "Synced" and health == "Healthy" for _, sync, health in states) and revision_ready:
            print("PASS: root, platform, and shop-dev are Synced and Healthy", flush=True)
            return
        time.sleep(5)
    raise SystemExit("GitOps did not converge. Inspect kubectl -n argocd describe applications.")


if __name__ == "__main__":
    main()
