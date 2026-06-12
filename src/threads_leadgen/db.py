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
