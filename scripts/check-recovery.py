"""Exercise a bad image rollout on the disposable release cluster only."""

import argparse
import json
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", choices=["kind-kube-foundry-release"], required=True)
    args = parser.parse_args()

    def kubectl(*command):
        return subprocess.check_output(["kubectl", "--context", args.context, "--request-timeout=20s",
                                        *command], text=True)

    def get(namespace, kind, name):
        return json.loads(kubectl("-n", namespace, "get", kind, name, "-o", "json"))

    def replace(name, path, value):
        kubectl("-n", "argocd", "patch", "application", name, "--type=json", "-p",
                json.dumps([{"op": "replace", "path": path, "value": value}]))

    def wait_for(check, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(3)
        raise RuntimeError("Recovery condition did not become true before the deadline")

    application = get("argocd", "application", "shop-dev")
    if (application.get("status", {}).get("health", {}).get("status") != "Healthy"
            or application.get("status", {}).get("sync", {}).get("status") != "Synced"):
        raise SystemExit("Start from a healthy, synced application; no changes were made")
    source = application["spec"]["source"]
    automation = get("argocd", "application", "kube-foundry")["spec"]["syncPolicy"]["automated"]
    good_image = get("shop", "deployment", "api")["spec"]["template"]["spec"]["containers"][0]["image"]
    bad_source = json.loads(json.dumps(source))
    bad_source["kustomize"] = {"images": [
        "kube-foundry-api=ghcr.io/chriswayneh/kube-foundry-api:v1.0.0-recovery-missing"]}

    def image_failure():
        pods = json.loads(kubectl("-n", "shop", "get", "pods", "-l",
                                 "app.kubernetes.io/component=api", "-o", "json"))["items"]
        return any(c.get("state", {}).get("waiting", {}).get("reason") in ("ErrImagePull", "ImagePullBackOff")
                   for pod in pods for c in pod.get("status", {}).get("containerStatuses", []))

    try:
        replace("kube-foundry", "/spec/syncPolicy/automated", {**automation, "enabled": False})
        replace("shop-dev", "/spec/source", bad_source)
        wait_for(image_failure)
        deployment = get("shop", "deployment", "api")
        assert deployment["status"].get("availableReplicas", 0) >= 2, "Known-good replicas were lost"
        print("PASS: unavailable image failed to start; known-good API replicas remained available", flush=True)
    finally:
        try:
            replace("shop-dev", "/spec/source", source)
        finally:
            replace("kube-foundry", "/spec/syncPolicy/automated", automation)

    def recovered():
        app = get("argocd", "application", "shop-dev").get("status", {})
        deployment = get("shop", "deployment", "api")
        return (deployment["spec"]["template"]["spec"]["containers"][0]["image"] == good_image
                and app.get("sync", {}).get("status") == "Synced"
                and app.get("health", {}).get("status") == "Healthy")

    wait_for(recovered)
    print("PASS: restored the original GitOps source and healthy image; root automation resumed", flush=True)


if __name__ == "__main__":
    main()
