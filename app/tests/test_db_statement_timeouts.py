import pytest

from conftest import FakeConn, FakeCursor

EXPECTED = "-c statement_timeout=5000 -c lock_timeout=2000"


def test_api_connection_uses_exact_default_options(api, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.delenv("PG_OPTIONS", raising=False)
    got = []
    monkeypatch.setattr(api.psycopg, "connect", lambda *a, **k: got.append(k))
    api.db_connection()
    assert got[0]["options"] == EXPECTED


@pytest.mark.parametrize("call", ["ensure_schema", "update_status", "claim"])
def test_every_worker_connection_uses_exact_default_options(worker, monkeypatch, call):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.delenv("PG_OPTIONS", raising=False)
    got = []

    def connect(*a, **k):
        got.append(k)
        return FakeConn(lambda sql, p: FakeCursor(rowcount=1))

    monkeypatch.setattr(worker.psycopg, "connect", connect)
    {"ensure_schema": lambda: worker.ensure_schema(),
     "update_status": lambda: worker.update_status("j", "complete"),
     "claim": lambda: worker.claim("j")}[call]()
    assert [k["options"] for k in got] == [EXPECTED]


def test_api_and_worker_read_pg_options_the_same_way(api, worker, monkeypatch):
    monkeypatch.setenv("PG_OPTIONS", "-c statement_timeout=100")
    assert api.pg_options() == worker.pg_options() == "-c statement_timeout=100"
