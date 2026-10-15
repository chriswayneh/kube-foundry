import uuid

from fastapi.testclient import TestClient


def test_unmatched_paths_share_one_label(api):
    c = TestClient(api.app)
    for _ in range(100):
        c.get(f"/random/{uuid.uuid4()}")
    body = c.get("/metrics").text
    lines = [l for l in body.splitlines() if l.startswith("http_requests_total{") and 'status="404"' in l]
    assert len(lines) == 1 and 'path="__unmatched__"' in lines[0]
