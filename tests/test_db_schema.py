def test_schema_creates_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"topics", "keywords", "posts"}.issubset(names)


def test_topics_columns(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(topics)").fetchall()}
    assert cols == {"id", "description", "paused", "created_at"}


def test_keywords_unique_per_topic(conn):
    import pytest, sqlite3
    conn.execute(
        "INSERT INTO topics (description, created_at) VALUES ('t', '2026-01-01')"
    )
    conn.execute("INSERT INTO keywords (topic_id, text) VALUES (1, 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO keywords (topic_id, text) VALUES (1, 'x')")


def test_posts_primary_key_post_id(conn):
    import pytest, sqlite3
    conn.execute("INSERT INTO topics (description, created_at) VALUES ('t', '2026-01-01')")
    conn.execute("INSERT INTO keywords (topic_id, text) VALUES (1, 'x')")
    conn.execute(
        "INSERT INTO posts (id, keyword_id, author_username, text, url, posted_at, fetched_at) "
        "VALUES ('p1', 1, 'a', 't', 'u', '2026-01-01', '2026-01-01')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO posts (id, keyword_id, author_username, text, url, posted_at, fetched_at) "
            "VALUES ('p1', 1, 'a', 't', 'u', '2026-01-01', '2026-01-01')"
        )
