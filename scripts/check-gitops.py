"""Wait for all three GitOps applications to be synced and healthy."""

import json
import subprocess
import time


def main():
    deadline = time.monotonic() + 300
    previous = None
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["kubectl", "--request-timeout=20s", "-n", "argocd", "get", "applications", "-o", "json"],
            text=True, capture_output=True, check=True,
        )
        apps = {item["metadata"]["name"]: item.get("status", {}) for item in json.loads(result.stdout)["items"]}
        expected = ("kube-foundry", "platform", "shop-dev")
        states = [(name, apps.get(name, {}).get("sync", {}).get("status", "Missing"),
                   apps.get(name, {}).get("health", {}).get("status", "Missing")) for name in expected]
        if states != previous:
            print("; ".join("/".join(state) for state in states), flush=True)
            previous = states
        if all(sync == "Synced" and health == "Healthy" for _, sync, health in states):
            print("PASS: root, platform, and shop-dev are Synced and Healthy", flush=True)
            return
        time.sleep(5)
    raise SystemExit("GitOps did not converge. Inspect kubectl -n argocd describe applications.")


if __name__ == "__main__":
    main()
