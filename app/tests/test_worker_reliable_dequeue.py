import fakeredis
import psycopg

from conftest import FakeConn, FakeCursor


def test_db_error_after_dequeue_keeps_job_and_requeues_on_restart(worker, monkeypatch):
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

    assert q.lrange("jobs", 0, -1) == []
    assert q.lrange(worker.PROCESSING, 0, -1) == ["job-1"]
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
