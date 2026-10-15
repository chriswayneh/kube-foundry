import fakeredis
from fastapi.testclient import TestClient

from conftest import FakeConn, FakeCursor

ROW = {"id": "7f0c1a6e-0000-4000-8000-000000000001", "status": "pending",
       "created_at": "2026-10-15T00:00:00Z", "updated_at": "2026-10-15T00:00:00Z"}


def test_rpush_failure_keeps_job_pending_and_returns_202(api, monkeypatch):
    conn = FakeConn(lambda sql, p: FakeCursor([ROW]))
    monkeypatch.setattr(api, "db_connection", lambda: conn)

    class Down:
        def rpush(self, *a):
            raise TimeoutError("ambiguous")

    monkeypatch.setattr(api, "redis_connection", lambda: Down())
    r = TestClient(api.app).post("/api/jobs")
    assert r.status_code == 202 and r.json()["status"] == "pending"
    assert not any("failed" in sql for sql, _ in conn.calls)


def test_sweep_repushes_pending_jobs(api, monkeypatch):
    conn = FakeConn(lambda sql, p: FakeCursor([{"id": ROW["id"]}] if sql.startswith("SELECT") else []))
    q = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(api, "db_connection", lambda: conn)
    monkeypatch.setattr(api, "redis_connection", lambda: q)
    assert api.dispatch_pending_jobs() == 1
    assert q.lrange("jobs", 0, -1) == [ROW["id"]]
    assert conn.commits == 1
