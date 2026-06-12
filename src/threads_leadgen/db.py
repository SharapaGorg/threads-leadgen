import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    description   TEXT NOT NULL,
    paused        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keywords (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id            INTEGER NOT NULL REFERENCES topics(id),
    text                TEXT NOT NULL,
    probed_volume_7d    INTEGER,
    last_scraped_at     TEXT,
    enabled             INTEGER NOT NULL DEFAULT 1,
    UNIQUE(topic_id, text)
);

CREATE TABLE IF NOT EXISTS posts (
    id                  TEXT PRIMARY KEY,
    keyword_id          INTEGER NOT NULL REFERENCES keywords(id),
    author_username     TEXT NOT NULL,
    author_followers    INTEGER,
    text                TEXT NOT NULL,
    url                 TEXT NOT NULL,
    posted_at           TEXT NOT NULL,
    likes_count         INTEGER,
    replies_count       INTEGER,
    fetched_at          TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'unreviewed',
    llm_notes           TEXT,
    marked_at           TEXT
);

CREATE INDEX IF NOT EXISTS posts_status_idx ON posts(status);
CREATE INDEX IF NOT EXISTS posts_keyword_idx ON posts(keyword_id);
"""


def init_db_connection(conn: sqlite3.Connection) -> None:
    """Apply schema to an existing connection (used in tests and prod)."""
    conn.executescript(SCHEMA)


def init_db(db_path: Path) -> None:
    """Open file-backed SQLite, ensure schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db_connection(conn)


@contextmanager
def connect(db_path: Path):
    """Yield a connection with sane defaults; commits on exit."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_topic(conn: sqlite3.Connection, description: str) -> int:
    cur = conn.execute(
        "INSERT INTO topics (description, created_at) VALUES (?, ?)",
        (description, now_iso()),
    )
    return cur.lastrowid


def list_topics(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            t.id, t.description, t.paused, t.created_at,
            COUNT(DISTINCT k.id) AS keyword_count,
            SUM(CASE WHEN p.status = 'unreviewed' THEN 1 ELSE 0 END) AS posts_unreviewed,
            SUM(CASE WHEN p.status = 'relevant'   THEN 1 ELSE 0 END) AS posts_relevant
        FROM topics t
        LEFT JOIN keywords k ON k.topic_id = t.id
        LEFT JOIN posts    p ON p.keyword_id = k.id
        GROUP BY t.id
        ORDER BY t.id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def set_topic_paused(conn: sqlite3.Connection, topic_id: int, paused: bool) -> None:
    conn.execute("UPDATE topics SET paused = ? WHERE id = ?", (int(paused), topic_id))


def add_keywords(conn: sqlite3.Connection, topic_id: int, keywords: list[str]) -> list[int]:
    ids: list[int] = []
    for text in keywords:
        try:
            cur = conn.execute(
                "INSERT INTO keywords (topic_id, text) VALUES (?, ?)",
                (topic_id, text),
            )
            ids.append(cur.lastrowid)
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM keywords WHERE topic_id = ? AND text = ?",
                (topic_id, text),
            ).fetchone()
            ids.append(row["id"])
    return ids


def list_active_keywords(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT k.id, k.text, k.topic_id
        FROM keywords k
        JOIN topics t ON t.id = k.topic_id
        WHERE k.enabled = 1 AND t.paused = 0
        ORDER BY k.last_scraped_at IS NULL DESC, k.last_scraped_at ASC, k.id ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def update_keyword_probe(conn: sqlite3.Connection, keyword_id: int, volume: int) -> None:
    conn.execute(
        "UPDATE keywords SET probed_volume_7d = ? WHERE id = ?",
        (volume, keyword_id),
    )


def mark_keyword_scraped(conn: sqlite3.Connection, keyword_id: int) -> None:
    conn.execute(
        "UPDATE keywords SET last_scraped_at = ? WHERE id = ?",
        (now_iso(), keyword_id),
    )


VALID_STATUSES = {"unreviewed", "relevant", "irrelevant", "replied", "skipped"}


def insert_post(
    conn: sqlite3.Connection,
    *,
    post_id: str,
    keyword_id: int,
    author_username: str,
    author_followers: int | None,
    text: str,
    url: str,
    posted_at: str,
    likes_count: int | None,
    replies_count: int | None,
) -> bool:
    """Return True if inserted, False if already existed (PK collision)."""
    try:
        conn.execute(
            """
            INSERT INTO posts (
                id, keyword_id, author_username, author_followers,
                text, url, posted_at, likes_count, replies_count, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id, keyword_id, author_username, author_followers,
                text, url, posted_at, likes_count, replies_count, now_iso(),
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def list_unreviewed(
    conn: sqlite3.Connection, topic_id: int | None, limit: int
) -> list[dict]:
    if topic_id is None:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status = 'unreviewed' "
            "ORDER BY posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT p.* FROM posts p
            JOIN keywords k ON k.id = p.keyword_id
            WHERE p.status = 'unreviewed' AND k.topic_id = ?
            ORDER BY p.posted_at DESC LIMIT ?
            """,
            (topic_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_post(conn: sqlite3.Connection, post_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    return dict(row) if row else None


def mark_post(
    conn: sqlite3.Connection,
    post_id: str,
    status: str,
    why: str | None = None,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    conn.execute(
        "UPDATE posts SET status = ?, llm_notes = ?, marked_at = ? WHERE id = ?",
        (status, why, now_iso(), post_id),
    )


def search_leads(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    topic_id: int | None = None,
    since: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[dict]:
    sql = "SELECT p.* FROM posts p JOIN keywords k ON k.id = p.keyword_id WHERE 1=1"
    args: list = []
    if status:
        sql += " AND p.status = ?"
        args.append(status)
    if topic_id is not None:
        sql += " AND k.topic_id = ?"
        args.append(topic_id)
    if since:
        sql += " AND p.posted_at >= ?"
        args.append(since)
    if query:
        sql += " AND p.text LIKE ?"
        args.append(f"%{query}%")
    sql += " ORDER BY p.posted_at DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def stats(conn: sqlite3.Connection, since: str | None = None) -> dict:
    sql = """
        SELECT
            t.id, t.description,
            COUNT(p.id) AS total,
            SUM(CASE WHEN p.status = 'relevant'   THEN 1 ELSE 0 END) AS relevant,
            SUM(CASE WHEN p.status = 'unreviewed' THEN 1 ELSE 0 END) AS unreviewed,
            SUM(CASE WHEN p.status = 'replied'    THEN 1 ELSE 0 END) AS replied
        FROM topics t
        LEFT JOIN keywords k ON k.topic_id = t.id
        LEFT JOIN posts    p ON p.keyword_id = k.id
    """
    args: list = []
    if since:
        sql += " AND (p.posted_at IS NULL OR p.posted_at >= ?)"
        args.append(since)
    sql += " GROUP BY t.id ORDER BY t.id"
    rows = conn.execute(sql, args).fetchall()
    return {"per_topic": [dict(r) for r in rows]}
