"""Small, fail-closed evidence helpers for disposable operational exercises."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


CONTEXT = "kind-kube-foundry-release"


def kubectl(context, *args, data=None):
    return subprocess.run(
        ["kubectl", "--context", context, "--request-timeout=30s", *args],
        input=json.dumps(data) if data is not None else None,
        text=True, capture_output=True, timeout=60,
    )


def get(context, namespace, kind, name):
    result = kubectl(context, "-n", namespace, "get", kind, name, "-o", "json")
    result.check_returncode()
    return json.loads(result.stdout)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


@contextmanager
def evidence(path, exercise, context):
    """Reserve a unique report before work. Interrupted reports never say passed."""
    require(context == CONTEXT, "Use the disposable release context only")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        report = {"schema_version": 1, "exercise": exercise, "context": context,
                  "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"}

        def write():
            handle.seek(0)
            json.dump(report, handle, indent=2)
            handle.write("\n")
            handle.truncate()
            handle.flush()

        write()
        try:
            report["cluster_uid"] = get(context, "", "namespace", "kube-system")["metadata"]["uid"]
            yield report
        except BaseException as error:
            # Do not serialize exception bodies, subprocess output, or application data.
            report.update(status="failed", error_type=type(error).__name__)
            raise
        else:
            report["status"] = "passed"
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            write()
