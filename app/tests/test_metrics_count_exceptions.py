from fastapi.testclient import TestClient


def test_unhandled_exception_is_counted_as_500(api):
    @api.app.get("/boom-test")
    def boom():
        raise RuntimeError("x")

    c = TestClient(api.app, raise_server_exceptions=False)
    assert c.get("/boom-test").status_code == 500
    v = api.REQUESTS.labels("GET", "/boom-test", "500")._value.get()
    assert v == 1
