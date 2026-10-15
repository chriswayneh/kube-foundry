from urllib.parse import urlparse, unquote

from psycopg.conninfo import conninfo_to_dict

PW = "p@ss:/#%"


def env(monkeypatch):
    for k in ("DATABASE_URL", "REDIS_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("POSTGRES_DB", "shop")
    monkeypatch.setenv("POSTGRES_USER", "shop")
    monkeypatch.setenv("POSTGRES_PASSWORD", PW)
    monkeypatch.setenv("REDIS_PASSWORD", PW)


def test_worker_builds_safe_urls(worker, monkeypatch):
    env(monkeypatch)
    assert conninfo_to_dict(worker.database_url())["password"] == PW
    assert unquote(urlparse(worker.redis_url()).password) == PW
    monkeypatch.setenv("DATABASE_URL", "postgresql://explicit")
    assert worker.database_url() == "postgresql://explicit"


def test_api_builds_safe_conninfo(api, monkeypatch):
    env(monkeypatch)
    seen = {}
    monkeypatch.setattr(api.psycopg, "connect", lambda dsn, **k: seen.setdefault("dsn", dsn))
    api.db_connection()
    assert conninfo_to_dict(seen["dsn"])["password"] == PW
    seen2 = {}
    monkeypatch.setattr(api.redis, "from_url", lambda url, **k: seen2.setdefault("url", url))
    api.redis_connection()
    assert unquote(urlparse(seen2["url"]).password) == PW
