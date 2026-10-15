def test_api_and_worker_pass_statement_and_lock_timeouts(api, worker, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    got = []
    monkeypatch.setattr(api.psycopg, "connect", lambda *a, **k: got.append(k) or None)
    api.db_connection()
    assert "statement_timeout=5000" in got[0]["options"] and "lock_timeout=2000" in got[0]["options"]

    class C:
        def __enter__(s): return s
        def __exit__(s, *a): return False
        def execute(s, *a): pass
        def commit(s): pass

    monkeypatch.setattr(worker.psycopg, "connect", lambda *a, **k: got.append(k) or C())
    worker.update_status("j", "complete")
    assert got[1]["options"] == worker.PG_OPTIONS and "statement_timeout" in worker.PG_OPTIONS
