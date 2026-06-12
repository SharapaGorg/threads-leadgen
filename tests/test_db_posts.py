import pytest
from threads_leadgen.db import (
    create_topic, add_keywords, insert_post, list_unreviewed,
    get_post, mark_post, search_leads, stats, VALID_STATUSES,
)


@pytest.fixture
def seeded(conn):
    """Topic with one keyword, conn returned."""
    t = create_topic(conn, "ideas")
    [kid] = add_keywords(conn, t, ["where to find"])
    return conn, t, kid


def _ipost(conn, kid, post_id, posted_at="2026-06-10T12:00:00+00:00", text="hi"):
    return insert_post(
        conn, post_id=post_id, keyword_id=kid,
        author_username="alice", author_followers=100,
        text=text, url=f"https://threads.net/post/{post_id}",
        posted_at=posted_at, likes_count=0, replies_count=0,
    )


def test_insert_post_returns_true_first_time(seeded):
    conn, _, kid = seeded
    assert _ipost(conn, kid, "p1") is True


def test_insert_post_idempotent(seeded):
    conn, _, kid = seeded
    assert _ipost(conn, kid, "p1") is True
    assert _ipost(conn, kid, "p1") is False
    rows = conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()
    assert rows["c"] == 1


def test_list_unreviewed_orders_newest_first(seeded):
    conn, _, kid = seeded
    _ipost(conn, kid, "old", posted_at="2026-01-01T00:00:00+00:00")
    _ipost(conn, kid, "new", posted_at="2026-06-10T00:00:00+00:00")
    posts = list_unreviewed(conn, topic_id=None, limit=10)
    assert [p["id"] for p in posts] == ["new", "old"]


def test_list_unreviewed_filters_by_topic(conn):
    t1 = create_topic(conn, "a"); t2 = create_topic(conn, "b")
    [k1] = add_keywords(conn, t1, ["x"])
    [k2] = add_keywords(conn, t2, ["y"])
    _ipost(conn, k1, "p1"); _ipost(conn, k2, "p2")
    assert {p["id"] for p in list_unreviewed(conn, topic_id=t1, limit=10)} == {"p1"}


def test_list_unreviewed_skips_reviewed(seeded):
    conn, _, kid = seeded
    _ipost(conn, kid, "p1")
    mark_post(conn, "p1", "relevant", "сильно жалуется")
    assert list_unreviewed(conn, topic_id=None, limit=10) == []


def test_get_post(seeded):
    conn, _, kid = seeded
    _ipost(conn, kid, "p1")
    p = get_post(conn, "p1")
    assert p is not None and p["id"] == "p1"
    assert get_post(conn, "nope") is None


def test_mark_post_invalid_status(seeded):
    conn, _, kid = seeded
    _ipost(conn, kid, "p1")
    with pytest.raises(ValueError):
        mark_post(conn, "p1", "garbage")


def test_mark_post_writes_notes_and_time(seeded):
    conn, _, kid = seeded
    _ipost(conn, kid, "p1")
    mark_post(conn, "p1", "relevant", "купит")
    p = get_post(conn, "p1")
    assert p["status"] == "relevant"
    assert p["llm_notes"] == "купит"
    assert p["marked_at"] is not None


def test_valid_statuses_set():
    assert VALID_STATUSES == {"unreviewed", "relevant", "irrelevant", "replied", "skipped"}


def test_search_leads_filters(seeded):
    conn, t, kid = seeded
    _ipost(conn, kid, "p1", text="хочу идею")
    _ipost(conn, kid, "p2", text="что-то другое")
    mark_post(conn, "p1", "relevant")
    mark_post(conn, "p2", "irrelevant")
    rel = search_leads(conn, status="relevant")
    assert [p["id"] for p in rel] == ["p1"]
    q = search_leads(conn, query="другое")
    assert [p["id"] for p in q] == ["p2"]
    by_topic = search_leads(conn, topic_id=t)
    assert {p["id"] for p in by_topic} == {"p1", "p2"}


def test_stats_per_topic(seeded):
    conn, t, kid = seeded
    _ipost(conn, kid, "p1"); _ipost(conn, kid, "p2"); _ipost(conn, kid, "p3")
    mark_post(conn, "p1", "relevant")
    mark_post(conn, "p2", "irrelevant")
    s = stats(conn)
    row = next(r for r in s["per_topic"] if r["id"] == t)
    assert row["total"] == 3
    assert row["relevant"] == 1
    assert row["unreviewed"] == 1
