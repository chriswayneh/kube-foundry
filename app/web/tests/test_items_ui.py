"""Behavioural tests for the items page against a mocked /api/items (Playwright)."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

WEB = Path(__file__).resolve().parents[1]
ORIGIN = "http://shop.test"


class FakeApi:
    def __init__(self, count: int) -> None:
        self.items: list[dict[str, Any]] = [{"id": i, "name": f"item-{i}", "created_at": "2026-01-01T00:00:00Z"}
                      for i in range(1, count + 1)]
        self.queries: list[dict[str, str]] = []

    def handle(self, route) -> None:
        request = route.request
        url = urlparse(request.url)
        if url.path in ("/", "/index.html"):
            route.fulfill(body=(WEB / "index.html").read_text(), content_type="text/html")
        elif url.path == "/app.js":
            route.fulfill(body=(WEB / "app.js").read_text(), content_type="text/javascript")
        elif url.path == "/api/items" and request.method == "POST":
            item = {"id": len(self.items) + 1, "name": json.loads(request.post_data)["name"],
                    "created_at": "2026-01-02T00:00:00Z"}
            self.items.append(item)
            route.fulfill(status=201, json=item)
        elif url.path == "/api/items":
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            self.queries.append(query)
            after, limit = int(query.get("after_id", 0)), int(query.get("limit", 50))
            route.fulfill(json=[i for i in self.items if i["id"] > after][:limit])
        else:
            route.fulfill(status=404, body="")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


def open_page(browser, api: FakeApi):
    page = browser.new_page()
    page.route(f"{ORIGIN}/**", api.handle)
    page.goto(f"{ORIGIN}/")
    return page


def rows(page) -> list[str]:
    return page.locator("#items li").all_inner_texts()


def test_load_more_pages_with_the_last_seen_id_until_a_short_page(browser):
    api = FakeApi(120)
    page = open_page(browser, api)
    sync_api.expect(page.locator("#items li")).to_have_count(50)
    sync_api.expect(page.locator("#load-more")).to_be_visible()

    page.click("#load-more")
    sync_api.expect(page.locator("#items li")).to_have_count(100)
    assert api.queries[-1]["after_id"] == "50"

    page.click("#load-more")
    sync_api.expect(page.locator("#items li")).to_have_count(120)
    assert api.queries[-1]["after_id"] == "100"
    sync_api.expect(page.locator("#load-more")).to_be_hidden()
    assert len(set(rows(page))) == 120


def test_a_short_first_page_hides_load_more(browser):
    page = open_page(browser, FakeApi(3))
    sync_api.expect(page.locator("#items li")).to_have_count(3)
    sync_api.expect(page.locator("#load-more")).to_be_hidden()


def test_a_new_item_stays_visible_past_the_first_page_and_is_not_duplicated(browser):
    api = FakeApi(60)
    page = open_page(browser, api)
    sync_api.expect(page.locator("#items li")).to_have_count(50)

    page.fill("input[name=name]", "fresh")
    page.click("#item-form button[type=submit]")
    sync_api.expect(page.locator("#items li", has_text="fresh · #61")).to_have_count(1)

    page.click("#load-more")
    sync_api.expect(page.locator("#items li")).to_have_count(61)
    sync_api.expect(page.locator("#items li", has_text="fresh · #61")).to_have_count(1)
