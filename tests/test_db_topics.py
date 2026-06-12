from threads_leadgen.db import create_topic, list_topics, set_topic_paused


def test_create_topic_returns_id(conn):
    topic_id = create_topic(conn, "поиск идей для контента")
    assert isinstance(topic_id, int) and topic_id > 0


def test_list_topics_with_counts(conn):
    t1 = create_topic(conn, "идеи")
    t2 = create_topic(conn, "разбор рилсов")
    conn.execute("INSERT INTO keywords (topic_id, text) VALUES (?, 'x')", (t1,))
    conn.execute("INSERT INTO keywords (topic_id, text) VALUES (?, 'y')", (t1,))
    conn.execute(
        "INSERT INTO posts (id, keyword_id, author_username, text, url, posted_at, fetched_at, status) "
        "VALUES ('p1', 1, 'a', 't', 'u', '2026-01-01', '2026-01-01', 'unreviewed')"
    )
    conn.execute(
        "INSERT INTO posts (id, keyword_id, author_username, text, url, posted_at, fetched_at, status) "
        "VALUES ('p2', 1, 'a', 't', 'u', '2026-01-01', '2026-01-01', 'relevant')"
    )
    topics = list_topics(conn)
    assert len(topics) == 2
    first = next(t for t in topics if t["id"] == t1)
    assert first["keyword_count"] == 2
    assert first["posts_unreviewed"] == 1
    assert first["posts_relevant"] == 1
    second = next(t for t in topics if t["id"] == t2)
    assert second["keyword_count"] == 0


def test_pause_resume_topic(conn):
    t = create_topic(conn, "x")
    set_topic_paused(conn, t, True)
    row = conn.execute("SELECT paused FROM topics WHERE id=?", (t,)).fetchone()
    assert row["paused"] == 1
    set_topic_paused(conn, t, False)
    row = conn.execute("SELECT paused FROM topics WHERE id=?", (t,)).fetchone()
    assert row["paused"] == 0
