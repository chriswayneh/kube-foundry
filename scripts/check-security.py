"""Exercise live admission, RBAC, and token isolation without creating test workloads."""

import copy
import json
import subprocess
import uuid


def kubectl(*args, data=None):
    return subprocess.run(
        ["kubectl", "--request-timeout=30s", *args],
        input=json.dumps(data) if data is not None else None,
        text=True, capture_output=True, check=False,
    )


def check_manifest(manifest, expected_error=None):
    result = kubectl("create", "--dry-run=server", "-f", "-", data=manifest)
    if expected_error:
        assert result.returncode != 0 and expected_error in result.stderr, result.stderr or result.stdout
    else:
        assert result.returncode == 0, result.stderr


def permission(account, verb, resource, allowed, namespace="shop"):
    result = kubectl("auth", "can-i", verb, resource, "-n", namespace,
                     "--as", f"system:serviceaccount:shop:{account}")
    assert result.stdout.strip() == ("yes" if allowed else "no"), result.stderr or result.stdout


def main():
    name = "security-check-" + uuid.uuid4().hex[:8]
    container = {
        "name": "test", "image": "kube-foundry-api:0.1.0",
        "resources": {"requests": {"cpu": "10m", "memory": "16Mi"},
                      "limits": {"cpu": "100m", "memory": "64Mi"}},
        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001,
                            "allowPrivilegeEscalation": False,
                            "capabilities": {"drop": ["ALL"]},
                            "seccompProfile": {"type": "RuntimeDefault"}},
    }
    pod = {"apiVersion": "v1", "kind": "Pod",
           "metadata": {"name": name, "namespace": "shop"},
           "spec": {"serviceAccountName": "api", "automountServiceAccountToken": False,
                    "containers": [container]}}
    check_manifest(pod)
    for image in ["nginx:latest", "nginx", "registry.example:5000/nginx", "nginx@sha256:invalid"]:
        bad = copy.deepcopy(pod)
        bad["spec"]["containers"][0]["image"] = image
        check_manifest(bad, "require-versioned-images")
    digest = copy.deepcopy(pod)
    digest["spec"]["containers"][0]["image"] = "nginx@sha256:" + "a" * 64
    check_manifest(digest)
    for location in ["containers", "initContainers"]:
        bad = copy.deepcopy(pod)
        bad["spec"][location] = [copy.deepcopy(container)]
        bad["spec"][location][0]["name"] = "resource-check"
        del bad["spec"][location][0]["resources"]["limits"]["cpu"]
        check_manifest(bad, "require-resources")
    bad = copy.deepcopy(pod)
    bad["spec"]["initContainers"] = [copy.deepcopy(container)]
    bad["spec"]["initContainers"][0]["name"] = "init-check"
    bad["spec"]["initContainers"][0]["image"] = "nginx:latest"
    check_manifest(bad, "require-versioned-images")
    for field, value in [("automountServiceAccountToken", True), ("serviceAccountName", "default")]:
        bad = copy.deepcopy(pod)
        bad["spec"][field] = value
        check_manifest(bad, "require-workload-identity")
    bad = copy.deepcopy(pod)
    bad["spec"]["containers"][0]["securityContext"]["privileged"] = True
    bad["spec"]["containers"][0]["securityContext"]["allowPrivilegeEscalation"] = True
    check_manifest(bad, "violates PodSecurity")
    # PSA only warns on Deployment templates; this proves Kyverno's controller validation.
    deployment = {"apiVersion": "apps/v1", "kind": "Deployment",
                  "metadata": {"name": name, "namespace": "shop"},
                  "spec": {"selector": {"matchLabels": {"app": name}},
                           "template": {"metadata": {"labels": {"app": name}},
                                        "spec": copy.deepcopy(pod["spec"])}}}
    check_manifest(deployment)
    deployment["spec"]["template"]["spec"]["containers"][0]["securityContext"]["runAsNonRoot"] = False
    check_manifest(deployment, "require-non-root")
    live = kubectl("get", "pods", "-n", "shop", "-l", "app.kubernetes.io/component=api", "-o", "json")
    assert live.returncode == 0, live.stderr
    live_pod = json.loads(live.stdout)["items"][0]["metadata"]["name"]
    debug = {"name": name, "image": "kube-foundry-api:0.1.0",
             "securityContext": copy.deepcopy(container["securityContext"])}
    for image, expected in [("kube-foundry-api:0.1.0", None), ("nginx:latest", "require-versioned-images")]:
        debug["image"] = image
        result = kubectl("patch", "pod", live_pod, "-n", "shop", "--subresource=ephemeralcontainers",
                         "--type=merge", "--dry-run=server", "-p",
                         json.dumps({"spec": {"ephemeralContainers": [debug]}}))
        if expected:
            assert result.returncode != 0 and expected in result.stderr, result.stderr or result.stdout
        else:
            assert result.returncode == 0, result.stderr
    print("PASS: ephemeral container admission tested with server dry-run")
    print("PASS: compliant Pods/controllers allowed; unsafe images, resources, identities, root and privileged settings denied")

    for account in ["api", "web", "worker", "postgres", "redis"]:
        for verb, resource in [("get", "secrets"), ("list", "pods"), ("create", "pods")]:
            permission(account, verb, resource, False)
        result = kubectl("get", "pods", "-n", "shop", "-l",
                         f"app.kubernetes.io/component={account}", "-o", "json")
        assert result.returncode == 0, result.stderr
        pods = json.loads(result.stdout)["items"]
        assert pods, f"No {account} Pods"
        for item in pods:
            assert item["spec"]["serviceAccountName"] == account
            assert item["spec"]["automountServiceAccountToken"] is False
            result = kubectl("exec", "-n", "shop", item["metadata"]["name"], "--", "sh", "-c",
                             "test ! -e /var/run/secrets/kubernetes.io/serviceaccount/token")
            assert result.returncode == 0, result.stderr
    permission("shop-observer", "get", "pods", True)
    permission("shop-observer", "get", "pods/log", True)
    for verb, resource in [("get", "secrets"), ("create", "pods/exec"), ("delete", "pods"),
                           ("patch", "deployments"), ("create", "rolebindings")]:
        permission("shop-observer", verb, resource, False)
    permission("shop-observer", "get", "pods", False, "kube-system")
    print("PASS: namespace RBAC boundaries and absence of workload API tokens")


if __name__ == "__main__":
    main()
