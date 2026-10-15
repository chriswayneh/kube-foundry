import fakeredis
import psycopg

from conftest import FakeConn, FakeCursor


def test_db_error_after_dequeue_releases_job_for_retry(worker, monkeypatch):
    q = fakeredis.FakeRedis(decode_responses=True)
    q.rpush("jobs", "job-1")
    monkeypatch.setattr(worker.redis, "from_url", lambda *a, **k: q)
    monkeypatch.setattr(worker, "redis_url", lambda: "redis://x")
    monkeypatch.setattr(worker, "ensure_schema", lambda: None)
    monkeypatch.setattr(worker, "claim", lambda job_id: True)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)

    def boom(job_id, state):
        worker.stopping = True
        raise psycopg.OperationalError("db down")

    monkeypatch.setattr(worker, "update_status", boom)
    worker.stopping = False
    worker.run()

    # The DB error releases the job back to the queue for a retry.
    assert q.lrange(worker.PROCESSING, 0, -1) == []
    assert q.lrange("jobs", 0, -1) == ["job-1"]


def test_orphans_left_by_a_dead_worker_are_requeued(worker):
    q = fakeredis.FakeRedis(decode_responses=True)
    q.rpush(worker.PROCESSING, "job-1")
    worker.requeue_orphans(q)
    assert q.lrange("jobs", 0, -1) == ["job-1"]
    assert q.llen(worker.PROCESSING) == 0


def test_completed_job_is_acked(worker, monkeypatch):
    q = fakeredis.FakeRedis(decode_responses=True)
    q.rpush("jobs", "job-2")
    monkeypatch.setattr(worker.redis, "from_url", lambda *a, **k: q)
    monkeypatch.setattr(worker, "redis_url", lambda: "redis://x")
    monkeypatch.setattr(worker, "ensure_schema", lambda: None)
    monkeypatch.setattr(worker, "claim", lambda job_id: True)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)
    states = []

    def record(job_id, state):
        states.append(state)
        worker.stopping = True

    monkeypatch.setattr(worker, "update_status", record)
    worker.stopping = False
    worker.run()
    assert states == ["complete"]
    assert q.llen(worker.PROCESSING) == 0 and q.llen("jobs") == 0


def test_claim_is_idempotent_and_skips_finished(worker, monkeypatch):
    conn = FakeConn(lambda sql, p: FakeCursor(rowcount=0))
    monkeypatch.setattr(worker, "database_url", lambda: "x")
    monkeypatch.setattr(worker.psycopg, "connect", lambda *a, **k: conn)
    assert worker.claim("done-job") is False
    assert "status IN ('pending', 'running')" in conn.calls[0][0]


def _harness(worker, monkeypatch, q):
    monkeypatch.setattr(worker.redis, "from_url", lambda *a, **k: q)
    monkeypatch.setattr(worker, "redis_url", lambda: "redis://x")
    monkeypatch.setattr(worker, "ensure_schema", lambda: None)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker.signal, "signal", lambda *a: None)
    worker.stopping = False


def test_claim_db_error_requeues_job(worker, monkeypatch):
    q = fakeredis.FakeRedis(decode_responses=True)
    q.rpush("jobs", "job-3")
    _harness(worker, monkeypatch, q)

    def claim_fails(job_id):
        worker.stopping = True
        raise psycopg.OperationalError("db down during claim")

    monkeypatch.setattr(worker, "claim", claim_fails)
    worker.run()
    assert q.llen(worker.PROCESSING) == 0
    assert q.lrange("jobs", 0, -1) == ["job-3"]


def test_startup_requeues_orphans_before_processing(worker, monkeypatch):
    q = fakeredis.FakeRedis(decode_responses=True)
    q.rpush(worker.PROCESSING, "orphan-1")
    _harness(worker, monkeypatch, q)
    monkeypatch.setattr(worker, "claim", lambda job_id: True)
    done = []

    def complete(job_id, state):
        done.append(job_id)
        worker.stopping = True

    monkeypatch.setattr(worker, "update_status", complete)
    worker.run()
    assert done == ["orphan-1"]
    assert q.llen(worker.PROCESSING) == 0


def test_duplicate_delivery_is_acked_without_processing(worker, monkeypatch):
    q = fakeredis.FakeRedis(decode_responses=True)
    q.rpush("jobs", "dup-1")
    _harness(worker, monkeypatch, q)

    def already_done(job_id):
        worker.stopping = True
        return False

    monkeypatch.setattr(worker, "claim", already_done)
    monkeypatch.setattr(worker, "update_status", lambda *a: (_ for _ in ()).throw(AssertionError("processed")))
    worker.run()
    assert q.llen(worker.PROCESSING) == 0 and q.llen("jobs") == 0


def test_chart_pins_single_worker():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "charts/shop/values.schema.json").read_text())
    assert schema["properties"]["worker"]["properties"]["replicas"]["maximum"] == 1
    assert "type: Recreate" in (root / "charts/shop/templates/deployment-worker.yaml").read_text()
