from threads_leadgen.db import (
    create_topic, add_keywords, list_active_keywords,
    update_keyword_probe, mark_keyword_scraped, set_topic_paused,
)


def test_add_keywords_returns_ids(conn):
    t = create_topic(conn, "x")
    ids = add_keywords(conn, t, ["a", "b", "c"])
    assert len(ids) == 3
    assert len(set(ids)) == 3


def test_add_keywords_idempotent(conn):
    t = create_topic(conn, "x")
    ids1 = add_keywords(conn, t, ["a", "b"])
    ids2 = add_keywords(conn, t, ["b", "c"])
    # 'b' should reuse its id
    assert ids1[1] == ids2[0]
    rows = conn.execute("SELECT text FROM keywords ORDER BY text").fetchall()
    assert [r["text"] for r in rows] == ["a", "b", "c"]


def test_list_active_keywords_excludes_paused_topics(conn):
    t1 = create_topic(conn, "a")
    t2 = create_topic(conn, "b")
    add_keywords(conn, t1, ["x"])
    add_keywords(conn, t2, ["y"])
    set_topic_paused(conn, t2, True)
    active = list_active_keywords(conn)
    texts = [k["text"] for k in active]
    assert texts == ["x"]


def test_list_active_keywords_orders_by_last_scraped(conn):
    t = create_topic(conn, "x")
    ids = add_keywords(conn, t, ["fresh", "old"])
    conn.execute(
        "UPDATE keywords SET last_scraped_at = '2026-06-12' WHERE id = ?", (ids[1],)
    )
    active = list_active_keywords(conn)
    # never-scraped first, then oldest scraped
    assert active[0]["text"] == "fresh"
    assert active[1]["text"] == "old"


def test_update_keyword_probe_and_last_scraped(conn):
    t = create_topic(conn, "x")
    [kid] = add_keywords(conn, t, ["a"])
    update_keyword_probe(conn, kid, 42)
    mark_keyword_scraped(conn, kid)
    row = conn.execute(
        "SELECT probed_volume_7d, last_scraped_at FROM keywords WHERE id=?", (kid,)
    ).fetchone()
    assert row["probed_volume_7d"] == 42
    assert row["last_scraped_at"] is not None
