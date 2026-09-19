"""Verify live monitoring, dashboard provisioning, metrics and eviction behavior."""

import base64
import json
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


def kubectl(*args, data=None):
    result = subprocess.run(["kubectl", "--request-timeout=20s", *args],
                            input=json.dumps(data) if data is not None else None,
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def eventually(check, timeout=150):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return check()
        except (AssertionError, RuntimeError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(3)


def prometheus(path):
    return kubectl("get", "--raw",
                   "/api/v1/namespaces/monitoring/services/http:monitoring-prometheus:9090/proxy" + path)


def main():
    def targets_ready():
        targets = prometheus("/api/v1/targets")["data"]["activeTargets"]
        app = [t for t in targets if t["labels"].get("namespace") == "shop"
               and t["labels"].get("service") == "api"]
        assert len(app) >= 2 and all(t["health"] == "up" for t in app), "API scrape targets not healthy"
    eventually(targets_ready)
    def series_ready():
        for query in ['http_requests_total{namespace="shop",service="api"}',
                      'kube_deployment_status_replicas_available{namespace="shop",deployment="api"}']:
            result = prometheus("/api/v1/query?" + urllib.parse.urlencode({"query": query}))
            assert result["status"] == "success" and result["data"]["result"], "Missing metric series"
    eventually(series_ready)

    def hpa_ready():
        hpa = kubectl("get", "hpa", "api", "-n", "shop", "-o", "json")
        assert any(c["type"] == "ScalingActive" and c["status"] == "True"
                   for c in hpa["status"].get("conditions", [])), "HPA metrics unavailable"
        assert hpa["status"].get("currentReplicas", 0) >= hpa["spec"]["minReplicas"]
    eventually(hpa_ready)
    metrics = kubectl("get", "--raw", "/apis/metrics.k8s.io/v1beta1/namespaces/shop/pods")
    assert metrics["items"], "Resource metrics missing"
    print("PASS: Prometheus API targets, application/cluster metrics, and active HPA", flush=True)

    secret = kubectl("get", "secret", "monitoring-grafana", "-n", "monitoring", "-o", "json")["data"]
    credentials = base64.b64decode(secret["admin-user"]) + b":" + base64.b64decode(secret["admin-password"])
    authorization = "Basic " + base64.b64encode(credentials).decode()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        forward = subprocess.Popen(["kubectl", "-n", "monitoring", "port-forward", "--address", "127.0.0.1",
                                    "service/monitoring-grafana", f"{port}:80"], stdout=log, stderr=log)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def grafana(path):
                assert forward.poll() is None, "Grafana port-forward stopped"
                request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                                 headers={"Authorization": authorization})
                with opener.open(request, timeout=10) as response:
                    return json.load(response)

            def dashboard_ready():
                assert grafana("/api/health")["database"] == "ok"
                dashboard = grafana("/api/dashboards/uid/kube-foundry-shop")["dashboard"]
                assert len(dashboard["panels"]) == 8, "Dashboard panels missing"
                assert grafana("/api/datasources/uid/prometheus")["type"] == "prometheus"
            eventually(dashboard_ready)
        finally:
            forward.terminate()
            forward.wait(timeout=10)
    print("PASS: Grafana health, provisioned dashboard, and Prometheus datasource", flush=True)

    def budgets_ready():
        budgets = kubectl("get", "pdb", "-n", "shop", "-o", "json")["items"]
        by_name = {p["metadata"]["name"]: p["status"] for p in budgets}
        assert set(by_name) >= {"api", "web", "postgres", "redis", "worker"}
        assert by_name["api"]["disruptionsAllowed"] >= 1
        assert by_name["postgres"]["disruptionsAllowed"] == 0
    eventually(budgets_ready)
    pods = kubectl("get", "pods", "-n", "shop", "-l", "app.kubernetes.io/component=api", "-o", "json")
    api_pod = next(p["metadata"]["name"] for p in pods["items"]
                   if not p["metadata"].get("deletionTimestamp")
                   and any(c["type"] == "Ready" and c["status"] == "True"
                           for c in p["status"].get("conditions", [])))
    for name, allowed in [(api_pod, True), ("postgres-0", False)]:
        eviction = {"apiVersion": "policy/v1", "kind": "Eviction",
                    "metadata": {"name": name, "namespace": "shop"},
                    "deleteOptions": {"dryRun": ["All"]}}
        result = subprocess.run(["kubectl", "--request-timeout=20s", "create", "--raw",
                                 f"/api/v1/namespaces/shop/pods/{name}/eviction", "-f", "-"],
                                input=json.dumps(eviction), text=True, capture_output=True)
        if allowed:
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0 and "disruption budget" in result.stderr.lower(), result.stderr
    print("PASS: API eviction allowed and singleton database eviction denied (dry-run only)", flush=True)


if __name__ == "__main__":
    main()
