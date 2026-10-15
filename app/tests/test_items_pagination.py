from fastapi.testclient import TestClient

from conftest import FakeConn, FakeCursor

ITEMS = [{"id": i, "name": f"n{i}", "created_at": "2026-10-15T00:00:00Z"} for i in range(1, 121)]


def responder(sql, params):
    after, limit = params
    return FakeCursor([r for r in ITEMS if r["id"] > after][:limit])


def test_limit_over_200_is_rejected(api, monkeypatch):
    monkeypatch.setattr(api, "db_connection", lambda: FakeConn(responder))
    assert TestClient(api.app).get("/api/items?limit=201").status_code == 422


def test_default_limit_is_50_and_paging_returns_each_item_once(api, monkeypatch):
    monkeypatch.setattr(api, "db_connection", lambda: FakeConn(responder))
    c = TestClient(api.app)
    assert len(c.get("/api/items").json()) == 50
    seen, after = [], 0
    while True:
        page = c.get(f"/api/items?after_id={after}&limit=50").json()
        if not page:
            break
        seen += [r["id"] for r in page]
        after = page[-1]["id"]
    assert seen == list(range(1, 121))
