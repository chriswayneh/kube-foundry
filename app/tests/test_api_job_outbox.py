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


def test_sweep_sql_selects_only_old_pending_jobs_and_touches_them(api, monkeypatch):
    conn = FakeConn(lambda sql, p: FakeCursor([{"id": ROW["id"]}] if sql.startswith("SELECT") else []))
    monkeypatch.setattr(api, "db_connection", lambda: conn)
    monkeypatch.setattr(api, "redis_connection", lambda: fakeredis.FakeRedis(decode_responses=True))
    api.dispatch_pending_jobs(older_than_seconds=45)
    select_sql, select_params = conn.calls[0]
    assert select_sql == (
        "SELECT id FROM jobs WHERE status = 'pending' "
        "AND updated_at < NOW() - make_interval(secs => %s) LIMIT 500"
    )
    assert select_params == (45,)
    update_sql, update_params = conn.calls[1]
    assert update_sql == "UPDATE jobs SET updated_at = NOW() WHERE id = %s AND status = 'pending'"
    assert update_params == (ROW["id"],)


def test_background_loop_runs_the_sweep(api, monkeypatch):
    import asyncio

    calls = []

    def sweep():
        calls.append(1)
        if len(calls) >= 2:
            raise asyncio.CancelledError
        return 1

    monkeypatch.setattr(api, "dispatch_pending_jobs", sweep)

    async def go():
        try:
            await api.dispatch_loop(interval=0)
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert len(calls) == 2


def test_lifespan_starts_dispatcher_when_dependencies_enabled(api, monkeypatch):
    monkeypatch.setenv("DEPENDENCY_CHECKS_ENABLED", "true")
    monkeypatch.setattr(api, "ensure_schema", lambda: None)
    started = []

    async def fake_loop(interval=0):
        started.append(True)

    monkeypatch.setattr(api, "dispatch_loop", fake_loop)
    with TestClient(api.app):
        pass
    assert started == [True]


def test_a_failed_sweep_is_logged_and_the_loop_runs_again(api, monkeypatch):
    import asyncio

    calls = []

    def sweep():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("redis briefly down")
        raise asyncio.CancelledError

    monkeypatch.setattr(api, "dispatch_pending_jobs", sweep)

    async def go():
        try:
            await api.dispatch_loop(interval=0)
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert len(calls) == 2


def test_lifespan_exit_cancels_the_dispatcher(api, monkeypatch):
    import asyncio

    monkeypatch.setenv("DEPENDENCY_CHECKS_ENABLED", "true")
    monkeypatch.setattr(api, "ensure_schema", lambda: None)
    state = {}

    async def forever(interval=0):
        state["started"] = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    monkeypatch.setattr(api, "dispatch_loop", forever)
    real_info = api.logger.info

    async def settle():
        await asyncio.sleep(0)

    def info(message, *args, **kwargs):
        if message == "api_stopped":
            # Let the cancellation be delivered, then record whether the
            # lifespan itself requested it (not the test client's teardown).
            state["cancel_requested"] = all(
                t.cancelling() for t in asyncio.all_tasks() if t.get_coro().__name__ == "forever"
            ) and any(t.get_coro().__name__ == "forever" for t in asyncio.all_tasks())
        return real_info(message, *args, **kwargs)

    monkeypatch.setattr(api.logger, "info", info)
    with TestClient(api.app):
        pass
    assert state.get("started") is True
    assert state.get("cancel_requested") is True
