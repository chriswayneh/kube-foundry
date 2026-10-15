import pytest
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


@pytest.mark.parametrize("missing", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"])
def test_missing_db_variable_is_a_clear_error(worker, api, monkeypatch, missing):
    env(monkeypatch)
    monkeypatch.delenv(missing)
    for module in (worker, api):
        with pytest.raises(RuntimeError, match=f"{missing} is required when DATABASE_URL is not set"):
            module.database_url()


def test_missing_redis_password_is_a_clear_error(worker, api, monkeypatch):
    env(monkeypatch)
    monkeypatch.delenv("REDIS_PASSWORD")
    for module in (worker, api):
        with pytest.raises(RuntimeError, match="REDIS_PASSWORD is required when REDIS_URL is not set"):
            module.redis_url()


def test_no_manifest_embeds_a_password_in_a_url():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for path in list((root / "clusters").rglob("*.yaml")) + list((root / "charts").rglob("*.yaml")) + [
        root / "gitops/apps/shop/base/shop.yaml"
    ]:
        assert not re.search(r"\$\((POSTGRES|REDIS)_PASSWORD\)@", path.read_text()), path
