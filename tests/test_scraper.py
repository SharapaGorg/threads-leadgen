from threads_leadgen.db import create_topic, add_keywords
from threads_leadgen.threads_client import RawPost
from threads_leadgen.scraper import scrape_once, is_active_hour


class FakeClient:
    def __init__(self, mapping: dict[str, list[RawPost]]):
        self.mapping = mapping
        self.calls: list[str] = []

    def login(self): pass

    def search_recent(self, keyword: str, limit: int = 30) -> list[RawPost]:
        self.calls.append(keyword)
        return self.mapping.get(keyword, [])


def _post(pid: str, kw_text: str) -> RawPost:
    return RawPost(
        post_id=pid, author_username="bob", author_followers=10,
        text=f"about {kw_text}", url=f"https://threads.net/p/{pid}",
        posted_at="2026-06-12T08:00:00+00:00",
        likes_count=1, replies_count=0,
    )


def test_scrape_once_visits_all_active_keywords(conn):
    t = create_topic(conn, "ideas")
    add_keywords(conn, t, ["foo", "bar"])
    client = FakeClient({"foo": [_post("p1", "foo")], "bar": [_post("p2", "bar")]})
    result = scrape_once(conn, client, sleep_fn=lambda _: None)
    assert set(client.calls) == {"foo", "bar"}
    assert result["inserted"] == 2
    assert result["seen"] == 2


def test_scrape_once_skips_already_seen(conn):
    t = create_topic(conn, "ideas")
    add_keywords(conn, t, ["foo"])
    client = FakeClient({"foo": [_post("p1", "foo")]})
    scrape_once(conn, client, sleep_fn=lambda _: None)
    result = scrape_once(conn, client, sleep_fn=lambda _: None)
    assert result["inserted"] == 0
    assert result["seen"] == 1


def test_scrape_once_marks_keyword_scraped(conn):
    t = create_topic(conn, "ideas")
    add_keywords(conn, t, ["foo"])
    client = FakeClient({"foo": []})
    scrape_once(conn, client, sleep_fn=lambda _: None)
    row = conn.execute("SELECT last_scraped_at FROM keywords WHERE text='foo'").fetchone()
    assert row["last_scraped_at"] is not None


def test_scrape_once_continues_on_keyword_error(conn):
    t = create_topic(conn, "ideas")
    add_keywords(conn, t, ["good", "bad"])

    class FlakyClient(FakeClient):
        def search_recent(self, keyword, limit=30):
            if keyword == "bad":
                raise RuntimeError("boom")
            return super().search_recent(keyword, limit)

    client = FlakyClient({"good": [_post("p1", "g")]})
    result = scrape_once(conn, client, sleep_fn=lambda _: None)
    assert result["inserted"] == 1
    assert result["errors"] == 1


def test_is_active_hour_window():
    assert is_active_hour(10, 9, 23) is True
    assert is_active_hour(9, 9, 23) is True
    assert is_active_hour(23, 9, 23) is False  # end exclusive
    assert is_active_hour(0, 9, 23) is False
    assert is_active_hour(8, 9, 23) is False
