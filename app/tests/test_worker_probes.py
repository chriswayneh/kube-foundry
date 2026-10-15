import fakeredis
from pathlib import Path


def test_loop_touches_heartbeat(worker, monkeypatch, tmp_path):
    hb = tmp_path / "hb"
    monkeypatch.setattr(worker, "HEARTBEAT", hb)
    q = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(worker.redis, "from_url", lambda *a, **k: q)
    monkeypatch.setattr(worker, "redis_url", lambda: "redis://x")
    monkeypatch.setattr(worker, "ensure_schema", lambda: None)
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)

    def blpop(*a, **k):
        worker.stopping = True
        return None

    monkeypatch.setattr(q, "blpop", blpop)
    worker.stopping = False
    worker.run()
    assert hb.exists()


def test_chart_has_worker_probes():
    root = Path(__file__).resolve().parents[2]
    text = (root / "charts/shop/templates/deployment-worker.yaml").read_text()
    assert "startupProbe:" in text and "livenessProbe:" in text and "/tmp/worker-heartbeat" in text
