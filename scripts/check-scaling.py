"""Bounded CPU exercise on one API Pod; verify HPA scale-up and recovery."""

import json
import subprocess
import time


def resource(kind, name):
    return json.loads(subprocess.check_output(["kubectl", "--request-timeout=20s", "-n", "shop",
                                              "get", kind, name, "-o", "json"], text=True))


def main():
    hpa = resource("hpa", "api")
    baseline = hpa["spec"]["minReplicas"]
    assert hpa["spec"]["maxReplicas"] > baseline
    assert hpa["status"].get("currentReplicas") == baseline, "Run when the API is idle at its minimum replicas"
    print(f"Baseline: {baseline} replicas. Applying 90 seconds of bounded CPU load to one API Pod.", flush=True)
    code = "import time\nend=time.monotonic()+90\nwhile time.monotonic()<end: pass"
    load = subprocess.Popen(["kubectl", "-n", "shop", "exec", "deployment/api", "--", "python", "-c", code])
    grew = False
    try:
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            hpa = resource("hpa", "api")
            current = hpa["status"].get("currentReplicas", 0)
            if current > baseline:
                print(f"PASS: HPA increased replicas from {baseline} to {current}", flush=True)
                grew = True
                break
            time.sleep(5)
        load.wait(timeout=110)
        assert load.returncode == 0, "CPU exercise failed"
        assert grew, "HPA did not scale up"
        print("Load finished; waiting for the configured scale-down window.", flush=True)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            deployment = resource("deployment", "api")
            if (deployment["spec"]["replicas"] == baseline
                    and deployment["status"].get("readyReplicas") == baseline):
                print(f"PASS: API returned to {baseline} ready replicas", flush=True)
                return
            time.sleep(5)
        raise AssertionError("API did not return to its minimum replica count")
    finally:
        # The remote loop is bounded even if this local client is interrupted.
        if load.poll() is None:
            load.terminate()
            load.wait(timeout=10)


if __name__ == "__main__":
    main()
