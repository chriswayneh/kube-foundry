"""Shared fixtures for app unit tests (no live Postgres/Redis needed).

Run: python -m pip install -r app/tests/requirements.txt && python -m pytest -q app/tests
"""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "app" / "api"))
    sys.modules.pop("main", None)
    from prometheus_client import REGISTRY
    for c in list(REGISTRY._collector_to_names):
        if any(n.startswith("http_request") for n in REGISTRY._collector_to_names[c]):
            REGISTRY.unregister(c)
    return importlib.import_module("main")


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "app" / "worker"))
    sys.modules.pop("worker", None)
    return importlib.import_module("worker")


class FakeCursor:
    def __init__(self, rows=None, rowcount=1):
        self._rows, self.rowcount = rows or [], rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    """Records SQL; returns canned results from a callable(sql, params)."""

    def __init__(self, responder=None):
        self.calls, self.responder, self.commits = [], responder, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self.responder(sql, params) if self.responder else FakeCursor()

    def commit(self):
        self.commits += 1
