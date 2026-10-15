import re
from pathlib import Path

import fakeredis

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/shop/templates/deployment-worker.yaml"


def test_loop_touches_heartbeat(worker, monkeypatch, tmp_path):
    hb = tmp_path / "hb"
    monkeypatch.setattr(worker, "HEARTBEAT", hb)
    q = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(worker.redis, "from_url", lambda *a, **k: q)
    monkeypatch.setattr(worker, "redis_url", lambda: "redis://x")
    monkeypatch.setattr(worker, "ensure_schema", lambda: None)
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)

    def blmove(*a, **k):
        worker.stopping = True
        return None

    monkeypatch.setattr(q, "blmove", blmove)
    worker.stopping = False
    worker.run()
    assert hb.exists()


def test_default_heartbeat_path_matches_probes(worker):
    assert str(worker.HEARTBEAT) == "/tmp/worker-heartbeat"


def test_chart_probes_use_heartbeat_file_and_30s_threshold(worker):
    text = CHART.read_text()
    assert "startupProbe:" in text and "livenessProbe:" in text
    paths = set(re.findall(r"(/tmp/[\w-]+)", text))
    assert paths == {str(worker.HEARTBEAT)}
    liveness = text.split("livenessProbe:", 1)[1].split("resources:", 1)[0]
    assert re.search(r"-lt 30\b", liveness)


def test_startup_probe_runs_the_heartbeat_file_check(worker):
    startup = CHART.read_text().split("startupProbe:", 1)[1].split("livenessProbe:", 1)[0]
    command = re.search(r"command:\s*\[(.*)\]", startup)
    assert command, "startupProbe must use an exec command"
    args = [a.strip().strip('"') for a in command.group(1).split(",")]
    assert args == ["sh", "-c", f"test -f {worker.HEARTBEAT}"]
