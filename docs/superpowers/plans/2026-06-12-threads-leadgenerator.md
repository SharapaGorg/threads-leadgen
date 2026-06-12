# Threads Lead Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Threads scraper + SQLite + MCP server for SMM lead generation, controlled interactively via Claude Code.

**Architecture:** Three independent processes communicate via SQLite. Scraper crawls Threads via a reverse-engineered API wrapper with anti-ban delays. MCP server exposes tools for topic/keyword management and lead review.

**Tech Stack:** Python 3.11+, `uv`, `mcp` (FastMCP), `threadspy` (with `httpx` fallback), `sqlite3` (stdlib), `pytest`, `pydantic`, `python-dotenv`.

**Reference spec:** `docs/superpowers/specs/2026-06-12-threads-leadgenerator-design.md`

---

## File Structure

```
threads-leadgenerator/
├── pyproject.toml                       # uv project manifest
├── .env.example                         # сэмпл секретов
├── .gitignore                           # уже есть
├── README.md                            # setup + usage
├── .mcp.json                            # MCP-сервер для Claude Code
├── data/                                # gitignored: leads.db, session.json
├── src/threads_leadgen/
│   ├── __init__.py
│   ├── config.py                        # Config dataclass + .env loader
│   ├── db.py                            # schema, queries, контекст-менеджер
│   ├── threads_client.py                # обёртка над реверс-API
│   ├── scraper.py                       # цикл скрапинга
│   └── mcp_server.py                    # FastMCP с тулами
├── scripts/
│   ├── run_scraper.py                   # entry point для воркера
│   └── run_mcp.py                       # entry point для MCP-сервера
└── tests/
    ├── conftest.py                      # фикстуры (in-memory db)
    ├── test_config.py
    ├── test_db_topics.py
    ├── test_db_keywords.py
    ├── test_db_posts.py
    ├── test_scraper.py
    ├── test_mcp_topics.py
    ├── test_mcp_keywords.py
    ├── test_mcp_leads.py
    └── test_threads_client_smoke.py     # требует .env, skip без кред
```

**Принципы:**
- Каждая задача = один коммит.
- TDD везде, где не интеграция с внешним миром (Threads HTTP).
- Файлы маленькие, ответственность одна.

---

## Task 1: Project setup

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/threads_leadgen/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "threads-leadgen"
version = "0.1.0"
description = "Threads scraper + MCP server for SMM/blogger lead generation"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.6.0",
    "python-dotenv>=1.0.0",
    "threadspy>=0.1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.12.0",
    "ruff>=0.5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/threads_leadgen"]
```

- [ ] **Step 2: Create `.env.example`**

```
THREADS_USERNAME=your_instagram_handle
THREADS_PASSWORD=your_password
DB_PATH=./data/leads.db
SESSION_PATH=./data/session.json
SCRAPER_ACTIVE_HOURS=09-23
```

- [ ] **Step 3: Create `README.md`**

````markdown
# threads-leadgen

Локальный скрапер Threads + SQLite + MCP-сервер для генерации лидов из публичных постов. Подробности — в [спеке](docs/superpowers/specs/2026-06-12-threads-leadgenerator-design.md).

## Setup

```bash
uv sync
cp .env.example .env
# отредактируй .env
```

## Запуск

```bash
# Скрапер (запускать вручную или через Task Scheduler)
uv run python scripts/run_scraper.py

# MCP-сервер — обычно поднимается автоматически Claude Code из .mcp.json
uv run python scripts/run_mcp.py
```

## Тесты

```bash
uv run pytest
```
````

- [ ] **Step 4: Create empty packages**

```bash
mkdir -p src/threads_leadgen tests data scripts
touch src/threads_leadgen/__init__.py tests/__init__.py
```

- [ ] **Step 5: Verify uv sync works**

Run: `uv sync`
Expected: succeeds, creates `.venv/`, lock file appears.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example README.md src/threads_leadgen/__init__.py tests/__init__.py uv.lock
git commit -m "feat: project scaffold with uv and dependencies"
```

---

## Task 2: Config module

**Files:**
- Create: `src/threads_leadgen/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
from pathlib import Path
import pytest
from threads_leadgen.config import Config


def test_config_from_env_file(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "THREADS_USERNAME=alice\n"
        "THREADS_PASSWORD=secret\n"
        "DB_PATH=/tmp/leads.db\n"
        "SESSION_PATH=/tmp/session.json\n"
        "SCRAPER_ACTIVE_HOURS=10-22\n"
    )
    cfg = Config.from_env(env)
    assert cfg.threads_username == "alice"
    assert cfg.threads_password == "secret"
    assert cfg.db_path == Path("/tmp/leads.db")
    assert cfg.session_path == Path("/tmp/session.json")
    assert cfg.active_hours_start == 10
    assert cfg.active_hours_end == 22


def test_config_missing_required(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("THREADS_USERNAME", raising=False)
    monkeypatch.delenv("THREADS_PASSWORD", raising=False)
    env = tmp_path / ".env"
    env.write_text("DB_PATH=/tmp/leads.db\n")
    with pytest.raises(RuntimeError, match="THREADS_USERNAME"):
        Config.from_env(env)


def test_config_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("SESSION_PATH", raising=False)
    monkeypatch.delenv("SCRAPER_ACTIVE_HOURS", raising=False)
    env = tmp_path / ".env"
    env.write_text("THREADS_USERNAME=a\nTHREADS_PASSWORD=b\n")
    cfg = Config.from_env(env)
    assert cfg.db_path == Path("./data/leads.db")
    assert cfg.session_path == Path("./data/session.json")
    assert cfg.active_hours_start == 9
    assert cfg.active_hours_end == 23
```

- [ ] **Step 2: Run test, verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: ImportError or ModuleNotFoundError for `threads_leadgen.config`.

- [ ] **Step 3: Implement `config.py`**

```python
# src/threads_leadgen/config.py
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    threads_username: str
    threads_password: str
    db_path: Path
    session_path: Path
    active_hours_start: int
    active_hours_end: int

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Config":
        if env_file is not None:
            load_dotenv(env_file, override=True)
        else:
            load_dotenv()
        hours = os.getenv("SCRAPER_ACTIVE_HOURS", "09-23")
        start, end = hours.split("-")
        return cls(
            threads_username=_required("THREADS_USERNAME"),
            threads_password=_required("THREADS_PASSWORD"),
            db_path=Path(os.getenv("DB_PATH", "./data/leads.db")),
            session_path=Path(os.getenv("SESSION_PATH", "./data/session.json")),
            active_hours_start=int(start),
            active_hours_end=int(end),
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required env var {name} not set")
    return value
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/config.py tests/test_config.py
git commit -m "feat: config loader from .env with defaults"
```

---

## Task 3: DB schema + initialization

**Files:**
- Create: `src/threads_leadgen/db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_db_schema.py`

- [ ] **Step 1: Write shared fixture**

```python
# tests/conftest.py
import sqlite3
import pytest
from threads_leadgen.db import init_db_connection


@pytest.fixture
def conn():
    """In-memory SQLite with schema, foreign keys enabled, row_factory set."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db_connection(conn)
    yield conn
    conn.close()
```

- [ ] **Step 2: Write failing schema test**

```python
# tests/test_db_schema.py
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
```

- [ ] **Step 3: Run, verify fail**

Run: `uv run pytest tests/test_db_schema.py -v`
Expected: ModuleNotFoundError for `threads_leadgen.db`.

- [ ] **Step 4: Implement schema**

```python
# src/threads_leadgen/db.py
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
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/test_db_schema.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/threads_leadgen/db.py tests/conftest.py tests/test_db_schema.py
git commit -m "feat: SQLite schema with topics, keywords, posts"
```

---

## Task 4: DB queries — topics

**Files:**
- Modify: `src/threads_leadgen/db.py` (append)
- Create: `tests/test_db_topics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db_topics.py
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
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_db_topics.py -v`
Expected: ImportError for `create_topic`.

- [ ] **Step 3: Implement queries — append to `db.py`**

```python
# append to src/threads_leadgen/db.py

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
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_db_topics.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/db.py tests/test_db_topics.py
git commit -m "feat: topic CRUD with aggregate counts"
```

---

## Task 5: DB queries — keywords

**Files:**
- Modify: `src/threads_leadgen/db.py` (append)
- Create: `tests/test_db_keywords.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db_keywords.py
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
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_db_keywords.py -v`
Expected: ImportError for `add_keywords`.

- [ ] **Step 3: Implement — append to `db.py`**

```python
# append to src/threads_leadgen/db.py

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
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_db_keywords.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/db.py tests/test_db_keywords.py
git commit -m "feat: keyword CRUD with idempotent insert and scrape priority"
```

---

## Task 6: DB queries — posts

**Files:**
- Modify: `src/threads_leadgen/db.py` (append)
- Create: `tests/test_db_posts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db_posts.py
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
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_db_posts.py -v`
Expected: ImportError for `insert_post`.

- [ ] **Step 3: Implement — append to `db.py`**

```python
# append to src/threads_leadgen/db.py

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
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_db_posts.py -v`
Expected: 11 passed.

- [ ] **Step 5: Run ALL tests**

Run: `uv run pytest -v`
Expected: all green (~23 tests so far).

- [ ] **Step 6: Commit**

```bash
git add src/threads_leadgen/db.py tests/test_db_posts.py
git commit -m "feat: post CRUD, search, and per-topic stats"
```

---

## Task 7: ThreadsClient — interface + spike

This task defines the wrapper interface and a smoke test that talks to real Threads. Implementation may need tweaking depending on which underlying library/endpoint works. Wrapper interface is fixed.

**Files:**
- Create: `src/threads_leadgen/threads_client.py`
- Create: `tests/test_threads_client_smoke.py`

- [ ] **Step 1: Define interface + dataclass**

```python
# src/threads_leadgen/threads_client.py
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class RawPost:
    post_id: str
    author_username: str
    author_followers: int | None
    text: str
    url: str
    posted_at: str          # ISO-8601 UTC
    likes_count: int | None
    replies_count: int | None

    def to_dict(self) -> dict:
        return asdict(self)


class ThreadsAuthError(RuntimeError):
    """Login failed, captcha required, or session invalidated."""


class ThreadsClient:
    """Thin wrapper over a Threads reverse-API implementation.

    Underlying mechanism is chosen at __init__ time. Today: threadspy.
    If it stops working, swap internals — keep the public surface stable:
      - login()
      - search_recent(keyword, limit) -> list[RawPost]
    """

    def __init__(self, username: str, password: str, session_path: Path):
        self.username = username
        self.password = password
        self.session_path = session_path
        self._api = None

    def login(self) -> None:
        try:
            from threadspy import ThreadsAPI
        except ImportError as e:
            raise ThreadsAuthError(
                "threadspy not installed — see Task 7 notes for fallback"
            ) from e

        cached = self._load_session()
        if cached:
            log.info("reusing cached session for %s", self.username)
            self._api = ThreadsAPI(username=self.username, token=cached.get("token"))
        else:
            log.info("logging in fresh as %s", self.username)
            self._api = ThreadsAPI(username=self.username, password=self.password)
            self._save_session({"token": getattr(self._api, "token", None)})

    def search_recent(self, keyword: str, limit: int = 30) -> list[RawPost]:
        if self._api is None:
            raise ThreadsAuthError("call login() first")
        try:
            raw = self._api.search(keyword)
        except AttributeError as e:
            raise NotImplementedError(
                "threadspy build lacks .search(); follow Task 7 fallback"
            ) from e
        except Exception as e:
            raise ThreadsAuthError(f"search failed: {e}") from e
        return [self._normalize(item) for item in (raw or [])[:limit]]

    def _normalize(self, item: dict) -> RawPost:
        user = item.get("user") or {}
        username = user.get("username") or item.get("username") or "unknown"
        code = item.get("code") or item.get("shortcode") or item.get("id")
        return RawPost(
            post_id=str(item.get("id") or item.get("pk") or code),
            author_username=username,
            author_followers=user.get("follower_count"),
            text=item.get("caption", {}).get("text") if isinstance(item.get("caption"), dict)
                 else item.get("text", ""),
            url=f"https://www.threads.net/@{username}/post/{code}",
            posted_at=str(item.get("taken_at") or item.get("created_at") or ""),
            likes_count=item.get("like_count"),
            replies_count=item.get("reply_count") or item.get("text_post_app_info", {}).get("direct_reply_count"),
        )

    def _load_session(self) -> dict | None:
        if not self.session_path.exists():
            return None
        try:
            return json.loads(self.session_path.read_text())
        except Exception:
            return None

    def _save_session(self, data: dict) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(json.dumps(data))
```

- [ ] **Step 2: Smoke test (skipped when no creds)**

```python
# tests/test_threads_client_smoke.py
"""Integration smoke test. Requires real Threads creds in .env.
Run manually: uv run pytest tests/test_threads_client_smoke.py -v -s
"""
import os
import pytest
from pathlib import Path
from threads_leadgen.threads_client import ThreadsClient


pytestmark = pytest.mark.skipif(
    not os.getenv("THREADS_USERNAME") or not os.getenv("THREADS_PASSWORD"),
    reason="needs THREADS_USERNAME and THREADS_PASSWORD in env",
)


def test_login_and_search(tmp_path: Path):
    from dotenv import load_dotenv
    load_dotenv()
    client = ThreadsClient(
        username=os.environ["THREADS_USERNAME"],
        password=os.environ["THREADS_PASSWORD"],
        session_path=tmp_path / "session.json",
    )
    client.login()
    posts = client.search_recent("идеи для контента", limit=5)
    assert isinstance(posts, list)
    if posts:
        p = posts[0]
        assert p.post_id and p.author_username and p.url.startswith("https://")
        print(f"\nGot {len(posts)} posts. First:\n  @{p.author_username}: {p.text[:120]}")
```

- [ ] **Step 3: Run smoke test against real Threads**

Run: `uv run pytest tests/test_threads_client_smoke.py -v -s`

Expected outcomes:
- **PASS:** `threadspy` works → continue to Task 8.
- **FAIL with NotImplementedError ("search lacks"):** `threadspy` API is different in installed version. Read `threadspy` source (`.venv/Lib/site-packages/threadspy/`), find actual search method, adapt `search_recent`. Common names: `search_recent_query`, `search_query`, `text_app_search`.
- **FAIL with ThreadsAuthError:** login broken. Check creds. If reCAPTCHA — log in via browser first, then retry.
- **FAIL with ImportError on threadspy:** library not on PyPI under that name. `uv remove threadspy && uv add threads-net` and adapt the import block in `threads_client.py`. Same wrapper interface stays.
- **All libs broken:** httpx fallback — see Task 7 fallback notes below.

- [ ] **Step 4: If httpx fallback needed**

Replace the body of `login()` and `search_recent()` with direct HTTP to Threads. Cookies extracted from your logged-in browser:

```python
# alternative implementation block
import httpx

def login(self) -> None:
    # Load cookies exported from browser via "EditThisCookie" / "Cookie Editor"
    cookie_file = self.session_path.with_suffix(".cookies.json")
    if not cookie_file.exists():
        raise ThreadsAuthError(
            f"export cookies from threads.net (logged-in) as JSON to {cookie_file}"
        )
    cookies = json.loads(cookie_file.read_text())
    jar = {c["name"]: c["value"] for c in cookies}
    self._api = httpx.Client(
        cookies=jar,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-IG-App-ID": "238260118697367",
            "Accept": "application/json",
        },
        timeout=30,
    )

def search_recent(self, keyword: str, limit: int = 30) -> list[RawPost]:
    resp = self._api.get(
        "https://www.threads.net/api/graphql",
        params={
            "doc_id": "20060666233495418",   # search_text_results — fragile; inspect Network tab to refresh
            "variables": json.dumps({"query": keyword, "count": limit}),
        },
    )
    resp.raise_for_status()
    data = resp.json()
    items = data["data"]["xdt_api__v1__text_app__search__"]["edges"]
    return [self._normalize(e["node"]) for e in items[:limit]]
```

(doc_id rotates — get current value by inspecting network tab on threads.net while typing in search.)

- [ ] **Step 5: Commit working version**

Once smoke test passes (manually or via fallback):

```bash
git add src/threads_leadgen/threads_client.py tests/test_threads_client_smoke.py
git commit -m "feat: ThreadsClient wrapper with smoke test"
```

---

## Task 8: ThreadsClient — probe helper

Add a separate method for "is this keyword alive?" — same call but with small limit and post-counting; used by `probe_keywords` MCP tool.

**Files:**
- Modify: `src/threads_leadgen/threads_client.py` (append method)

- [ ] **Step 1: Append method**

```python
# append to ThreadsClient class
from datetime import datetime, timedelta, timezone

    def probe_volume_7d(self, keyword: str) -> tuple[int, list[str]]:
        """Quick liveness check. Returns (count of last-7d posts, up to 3 sample texts)."""
        posts = self.search_recent(keyword, limit=20)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent = []
        for p in posts:
            try:
                ts = datetime.fromisoformat(p.posted_at)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if ts >= cutoff:
                recent.append(p)
        samples = [p.text[:200] for p in recent[:3]]
        return len(recent), samples
```

(Note: keep the `from datetime import ...` at top of file, not inside the class.)

- [ ] **Step 2: Commit**

```bash
git add src/threads_leadgen/threads_client.py
git commit -m "feat: probe_volume_7d for keyword liveness check"
```

---

## Task 9: Scraper loop

**Files:**
- Create: `src/threads_leadgen/scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Write failing tests with fake client**

```python
# tests/test_scraper.py
from datetime import datetime, timezone
from threads_leadgen.db import create_topic, add_keywords, list_active_keywords
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
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: ImportError for `scrape_once`.

- [ ] **Step 3: Implement scraper**

```python
# src/threads_leadgen/scraper.py
from __future__ import annotations
import logging
import random
import sqlite3
import time
from datetime import datetime
from typing import Callable, Protocol

from .db import (
    list_active_keywords, insert_post, mark_keyword_scraped, connect,
)
from .threads_client import RawPost

log = logging.getLogger(__name__)


class ThreadsClientProto(Protocol):
    def login(self) -> None: ...
    def search_recent(self, keyword: str, limit: int = 30) -> list[RawPost]: ...


def is_active_hour(hour: int, start: int, end: int) -> bool:
    """Inclusive start, exclusive end. Wraps midnight if start > end."""
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def scrape_once(
    conn: sqlite3.Connection,
    client: ThreadsClientProto,
    *,
    per_keyword_limit: int = 30,
    sleep_fn: Callable[[float], None] = time.sleep,
    delay_range: tuple[float, float] = (30.0, 180.0),
) -> dict:
    """Walk every active keyword once. Returns counters."""
    keywords = list_active_keywords(conn)
    inserted = 0
    seen = 0
    errors = 0
    for i, kw in enumerate(keywords):
        if i > 0:
            sleep_fn(random.uniform(*delay_range))
        try:
            raw_posts = client.search_recent(kw["text"], limit=per_keyword_limit)
        except Exception as e:
            log.warning("search failed for %r: %s", kw["text"], e)
            errors += 1
            continue
        for rp in raw_posts:
            seen += 1
            ok = insert_post(
                conn,
                post_id=rp.post_id,
                keyword_id=kw["id"],
                author_username=rp.author_username,
                author_followers=rp.author_followers,
                text=rp.text,
                url=rp.url,
                posted_at=rp.posted_at,
                likes_count=rp.likes_count,
                replies_count=rp.replies_count,
            )
            if ok:
                inserted += 1
        mark_keyword_scraped(conn, kw["id"])
        conn.commit()
    return {"inserted": inserted, "seen": seen, "errors": errors, "keywords": len(keywords)}


def run_forever(
    db_path,
    client: ThreadsClientProto,
    *,
    active_start: int,
    active_end: int,
    cycle_range: tuple[float, float] = (15 * 60, 60 * 60),
    sleep_fn: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = datetime.now,
) -> None:
    """Outer loop — calls scrape_once during active hours."""
    client.login()
    while True:
        now = clock()
        if not is_active_hour(now.hour, active_start, active_end):
            log.info("outside active hours (%d-%d), sleeping 30 min", active_start, active_end)
            sleep_fn(30 * 60)
            continue
        with connect(db_path) as conn:
            result = scrape_once(conn, client, sleep_fn=sleep_fn)
        log.info("cycle done: %s", result)
        sleep_fn(random.uniform(*cycle_range))
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/scraper.py tests/test_scraper.py
git commit -m "feat: scraper loop with anti-ban delays and active-hours gate"
```

---

## Task 10: MCP server skeleton + list_topics

**Files:**
- Create: `src/threads_leadgen/mcp_server.py`
- Create: `tests/test_mcp_topics.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_mcp_topics.py
import json
from pathlib import Path
from threads_leadgen.db import create_topic, add_keywords, init_db, connect
from threads_leadgen.mcp_server import build_tools


def test_list_topics_tool(tmp_path: Path):
    db = tmp_path / "leads.db"
    init_db(db)
    with connect(db) as conn:
        t1 = create_topic(conn, "ideas")
        add_keywords(conn, t1, ["a", "b"])
        create_topic(conn, "reels")
    tools = build_tools(db_path=db, threads_client=None)
    result = tools["list_topics"]()
    assert len(result) == 2
    descs = {r["description"] for r in result}
    assert descs == {"ideas", "reels"}
    ideas = next(r for r in result if r["description"] == "ideas")
    assert ideas["keyword_count"] == 2
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_mcp_topics.py -v`
Expected: ImportError for `build_tools`.

- [ ] **Step 3: Implement server skeleton + tool**

```python
# src/threads_leadgen/mcp_server.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from . import db as dbmod
from .threads_client import ThreadsClient


def build_tools(
    db_path: Path,
    threads_client: ThreadsClient | None,
) -> dict[str, Callable[..., Any]]:
    """Build a dict of bound tool callables.

    Returned plain functions so unit tests can call them without spinning the MCP transport.
    `create_server()` registers the same dict on a FastMCP instance.
    """

    def list_topics() -> list[dict]:
        with dbmod.connect(db_path) as conn:
            return dbmod.list_topics(conn)

    return {
        "list_topics": list_topics,
    }


def create_server(db_path: Path, threads_client: ThreadsClient | None) -> FastMCP:
    mcp = FastMCP("threads-leadgen")
    tools = build_tools(db_path, threads_client)

    @mcp.tool()
    def list_topics() -> list[dict]:
        """Все темы со счётчиками ключевиков и постов."""
        return tools["list_topics"]()

    # дополнительные тулы регистрируются здесь по мере добавления
    return mcp
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_mcp_topics.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/mcp_server.py tests/test_mcp_topics.py
git commit -m "feat: MCP server skeleton with list_topics tool"
```

---

## Task 11: MCP — add_topic + pause/resume

**Files:**
- Modify: `src/threads_leadgen/mcp_server.py`
- Modify: `tests/test_mcp_topics.py` (append)

- [ ] **Step 1: Add failing tests**

```python
# append to tests/test_mcp_topics.py
def test_add_topic_returns_id(tmp_path: Path):
    db = tmp_path / "leads.db"; init_db(db)
    tools = build_tools(db_path=db, threads_client=None)
    tid = tools["add_topic"]("новая тема")
    assert isinstance(tid, int)
    assert tools["list_topics"]()[0]["description"] == "новая тема"


def test_pause_and_resume(tmp_path: Path):
    db = tmp_path / "leads.db"; init_db(db)
    tools = build_tools(db_path=db, threads_client=None)
    tid = tools["add_topic"]("x")
    tools["pause_topic"](tid)
    assert tools["list_topics"]()[0]["paused"] == 1
    tools["resume_topic"](tid)
    assert tools["list_topics"]()[0]["paused"] == 0
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_mcp_topics.py -v`
Expected: KeyError for `add_topic`.

- [ ] **Step 3: Extend `build_tools` and `create_server`**

In `build_tools`, inside the function body, add:

```python
    def add_topic(description: str) -> int:
        with dbmod.connect(db_path) as conn:
            return dbmod.create_topic(conn, description)

    def pause_topic(topic_id: int) -> dict:
        with dbmod.connect(db_path) as conn:
            dbmod.set_topic_paused(conn, topic_id, True)
        return {"ok": True, "topic_id": topic_id, "paused": True}

    def resume_topic(topic_id: int) -> dict:
        with dbmod.connect(db_path) as conn:
            dbmod.set_topic_paused(conn, topic_id, False)
        return {"ok": True, "topic_id": topic_id, "paused": False}

    return {
        "list_topics": list_topics,
        "add_topic": add_topic,
        "pause_topic": pause_topic,
        "resume_topic": resume_topic,
    }
```

(remove the earlier `return {"list_topics": list_topics}` — replace with the new dict)

In `create_server`, register MCP tools:

```python
    @mcp.tool()
    def add_topic(description: str) -> int:
        """Создать тему. Возвращает её id. Ключевики добавляй отдельно через commit_keywords."""
        return tools["add_topic"](description)

    @mcp.tool()
    def pause_topic(topic_id: int) -> dict:
        """Поставить тему на паузу — скрапер перестанет её обходить."""
        return tools["pause_topic"](topic_id)

    @mcp.tool()
    def resume_topic(topic_id: int) -> dict:
        """Снять тему с паузы."""
        return tools["resume_topic"](topic_id)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_mcp_topics.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/mcp_server.py tests/test_mcp_topics.py
git commit -m "feat: MCP tools add_topic, pause_topic, resume_topic"
```

---

## Task 12: MCP — probe_keywords + commit_keywords

**Files:**
- Modify: `src/threads_leadgen/mcp_server.py`
- Create: `tests/test_mcp_keywords.py`

- [ ] **Step 1: Failing tests with fake client**

```python
# tests/test_mcp_keywords.py
import pytest
from pathlib import Path
from threads_leadgen.db import init_db, connect, create_topic
from threads_leadgen.mcp_server import build_tools


class FakeClient:
    def __init__(self, mapping: dict[str, tuple[int, list[str]]]):
        self.mapping = mapping

    def probe_volume_7d(self, keyword: str) -> tuple[int, list[str]]:
        return self.mapping.get(keyword, (0, []))


def test_probe_keywords_returns_volumes(tmp_path: Path):
    db = tmp_path / "leads.db"; init_db(db)
    client = FakeClient({"alive": (42, ["s1", "s2"]), "dead": (0, [])})
    tools = build_tools(db_path=db, threads_client=client)
    result = tools["probe_keywords"](["alive", "dead"])
    assert len(result) == 2
    alive = next(r for r in result if r["keyword"] == "alive")
    assert alive["volume_7d"] == 42 and alive["samples"] == ["s1", "s2"]


def test_commit_keywords_persists(tmp_path: Path):
    db = tmp_path / "leads.db"; init_db(db)
    with connect(db) as c:
        tid = create_topic(c, "x")
    tools = build_tools(db_path=db, threads_client=None)
    ids = tools["commit_keywords"](tid, ["foo", "bar"])
    assert len(ids) == 2
    with connect(db) as c:
        rows = c.execute("SELECT text FROM keywords ORDER BY text").fetchall()
    assert [r["text"] for r in rows] == ["bar", "foo"]


def test_probe_requires_client(tmp_path: Path):
    db = tmp_path / "leads.db"; init_db(db)
    tools = build_tools(db_path=db, threads_client=None)
    with pytest.raises(RuntimeError, match="client"):
        tools["probe_keywords"](["x"])
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_mcp_keywords.py -v`
Expected: KeyError for `probe_keywords`.

- [ ] **Step 3: Extend `build_tools`**

Append to the inner functions, and update the returned dict:

```python
    def probe_keywords(keywords: list[str]) -> list[dict]:
        if threads_client is None:
            raise RuntimeError("threads client not initialised; cannot probe")
        if hasattr(threads_client, "_api") and threads_client._api is None:
            threads_client.login()
        out = []
        for kw in keywords:
            volume, samples = threads_client.probe_volume_7d(kw)
            out.append({"keyword": kw, "volume_7d": volume, "samples": samples})
        return out

    def commit_keywords(topic_id: int, keywords: list[str]) -> list[int]:
        with dbmod.connect(db_path) as conn:
            return dbmod.add_keywords(conn, topic_id, keywords)
```

Add both to the returned dict.

Register in `create_server`:

```python
    @mcp.tool()
    def probe_keywords(keywords: list[str]) -> list[dict]:
        """Прикинуть, сколько постов за 7 дней по каждой фразе + 3 примера. Дёргает Threads — НЕ запускай на 50 фразах сразу."""
        return tools["probe_keywords"](keywords)

    @mcp.tool()
    def commit_keywords(topic_id: int, keywords: list[str]) -> list[int]:
        """Привязать ключевики к теме. Дубликаты игнорятся. Скрапер подхватит со следующего цикла."""
        return tools["commit_keywords"](topic_id, keywords)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_mcp_keywords.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/mcp_server.py tests/test_mcp_keywords.py
git commit -m "feat: MCP tools probe_keywords and commit_keywords"
```

---

## Task 13: MCP — list_unreviewed, get_post, mark_post

**Files:**
- Modify: `src/threads_leadgen/mcp_server.py`
- Create: `tests/test_mcp_leads.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_mcp_leads.py
import pytest
from pathlib import Path
from threads_leadgen.db import (
    init_db, connect, create_topic, add_keywords, insert_post,
)
from threads_leadgen.mcp_server import build_tools


def _seed(db: Path) -> tuple[int, int]:
    init_db(db)
    with connect(db) as c:
        tid = create_topic(c, "ideas")
        [kid] = add_keywords(c, tid, ["foo"])
        insert_post(
            c, post_id="p1", keyword_id=kid, author_username="a",
            author_followers=None, text="want ideas", url="https://t/p1",
            posted_at="2026-06-10T00:00:00+00:00",
            likes_count=0, replies_count=0,
        )
    return tid, kid


def test_list_unreviewed_default_limit(tmp_path: Path):
    db = tmp_path / "leads.db"; _seed(db)
    tools = build_tools(db_path=db, threads_client=None)
    posts = tools["list_unreviewed"]()
    assert len(posts) == 1 and posts[0]["id"] == "p1"


def test_get_post_existing_and_missing(tmp_path: Path):
    db = tmp_path / "leads.db"; _seed(db)
    tools = build_tools(db_path=db, threads_client=None)
    assert tools["get_post"]("p1")["id"] == "p1"
    assert tools["get_post"]("nope") is None


def test_mark_post_writes_status_and_notes(tmp_path: Path):
    db = tmp_path / "leads.db"; _seed(db)
    tools = build_tools(db_path=db, threads_client=None)
    tools["mark_post"]("p1", "relevant", "buyer")
    p = tools["get_post"]("p1")
    assert p["status"] == "relevant" and p["llm_notes"] == "buyer"


def test_mark_post_rejects_unknown_status(tmp_path: Path):
    db = tmp_path / "leads.db"; _seed(db)
    tools = build_tools(db_path=db, threads_client=None)
    with pytest.raises(ValueError):
        tools["mark_post"]("p1", "garbage")
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_mcp_leads.py -v`
Expected: KeyError for `list_unreviewed`.

- [ ] **Step 3: Extend `build_tools`**

```python
    def list_unreviewed(topic_id: int | None = None, limit: int = 30) -> list[dict]:
        with dbmod.connect(db_path) as conn:
            return dbmod.list_unreviewed(conn, topic_id, limit)

    def get_post(post_id: str) -> dict | None:
        with dbmod.connect(db_path) as conn:
            return dbmod.get_post(conn, post_id)

    def mark_post(post_id: str, status: str, why: str | None = None) -> dict:
        with dbmod.connect(db_path) as conn:
            dbmod.mark_post(conn, post_id, status, why)
        return {"ok": True, "post_id": post_id, "status": status}
```

Register MCP tools:

```python
    @mcp.tool()
    def list_unreviewed(topic_id: int | None = None, limit: int = 30) -> list[dict]:
        """Пачка непроверенных постов. Свежие сверху. topic_id опционально."""
        return tools["list_unreviewed"](topic_id, limit)

    @mcp.tool()
    def get_post(post_id: str) -> dict | None:
        """Полные детали поста."""
        return tools["get_post"](post_id)

    @mcp.tool()
    def mark_post(post_id: str, status: str, why: str | None = None) -> dict:
        """Пометить пост. status ∈ {unreviewed, relevant, irrelevant, replied, skipped}. why — заметка для тебя."""
        return tools["mark_post"](post_id, status, why)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_mcp_leads.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/threads_leadgen/mcp_server.py tests/test_mcp_leads.py
git commit -m "feat: MCP tools list_unreviewed, get_post, mark_post"
```

---

## Task 14: MCP — search_leads + stats

**Files:**
- Modify: `src/threads_leadgen/mcp_server.py`
- Modify: `tests/test_mcp_leads.py` (append)

- [ ] **Step 1: Failing tests**

```python
# append to tests/test_mcp_leads.py
def test_search_leads_filter_status(tmp_path: Path):
    db = tmp_path / "leads.db"; _seed(db)
    tools = build_tools(db_path=db, threads_client=None)
    tools["mark_post"]("p1", "relevant", "ok")
    assert len(tools["search_leads"](status="relevant")) == 1
    assert tools["search_leads"](status="irrelevant") == []


def test_stats_basic(tmp_path: Path):
    db = tmp_path / "leads.db"; _seed(db)
    tools = build_tools(db_path=db, threads_client=None)
    s = tools["stats"]()
    assert s["per_topic"][0]["total"] == 1
    assert s["per_topic"][0]["unreviewed"] == 1
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_mcp_leads.py -v`
Expected: KeyError for `search_leads`.

- [ ] **Step 3: Extend `build_tools`**

```python
    def search_leads(
        status: str | None = None,
        topic_id: int | None = None,
        since: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with dbmod.connect(db_path) as conn:
            return dbmod.search_leads(
                conn, status=status, topic_id=topic_id,
                since=since, query=query, limit=limit,
            )

    def stats(since: str | None = None) -> dict:
        with dbmod.connect(db_path) as conn:
            return dbmod.stats(conn, since)
```

MCP registration:

```python
    @mcp.tool()
    def search_leads(
        status: str | None = None,
        topic_id: int | None = None,
        since: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Поиск по уже размеченным постам. since — ISO-дата."""
        return tools["search_leads"](status, topic_id, since, query, limit)

    @mcp.tool()
    def stats(since: str | None = None) -> dict:
        """Сводка по темам: собрано / релевантных / непроверенных / отвечено."""
        return tools["stats"](since)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_mcp_leads.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: all green (~35 tests).

- [ ] **Step 6: Commit**

```bash
git add src/threads_leadgen/mcp_server.py tests/test_mcp_leads.py
git commit -m "feat: MCP tools search_leads and stats"
```

---

## Task 15: Runner scripts + .mcp.json + README finalization

**Files:**
- Create: `scripts/run_scraper.py`
- Create: `scripts/run_mcp.py`
- Create: `.mcp.json`
- Modify: `README.md`

- [ ] **Step 1: Scraper runner**

```python
# scripts/run_scraper.py
"""Standalone scraper. Run manually or via Windows Task Scheduler."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from threads_leadgen.config import Config
from threads_leadgen.db import init_db
from threads_leadgen.scraper import run_forever
from threads_leadgen.threads_client import ThreadsClient


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    cfg = Config.from_env()
    init_db(cfg.db_path)
    client = ThreadsClient(
        username=cfg.threads_username,
        password=cfg.threads_password,
        session_path=cfg.session_path,
    )
    try:
        run_forever(
            db_path=cfg.db_path,
            client=client,
            active_start=cfg.active_hours_start,
            active_end=cfg.active_hours_end,
        )
    except KeyboardInterrupt:
        logging.info("interrupted, exiting cleanly")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: MCP runner**

```python
# scripts/run_mcp.py
"""MCP server entry — wired up via .mcp.json so Claude Code can spawn it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from threads_leadgen.config import Config
from threads_leadgen.db import init_db
from threads_leadgen.mcp_server import create_server
from threads_leadgen.threads_client import ThreadsClient


def main() -> None:
    cfg = Config.from_env()
    init_db(cfg.db_path)
    client = ThreadsClient(
        username=cfg.threads_username,
        password=cfg.threads_password,
        session_path=cfg.session_path,
    )
    # Lazy login: probe_keywords triggers it when first called.
    server = create_server(db_path=cfg.db_path, threads_client=client)
    server.run()  # FastMCP defaults to stdio transport


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: `.mcp.json`**

```json
{
  "mcpServers": {
    "threads-leadgen": {
      "command": "uv",
      "args": ["run", "python", "scripts/run_mcp.py"],
      "cwd": "C:/Dev/Dev_2025/threads-leadgenerator"
    }
  }
}
```

- [ ] **Step 4: Finalize README**

````markdown
# threads-leadgen

Локальный скрапер Threads + SQLite + MCP-сервер для генерации лидов из публичных постов. Подробности — в [спеке](docs/superpowers/specs/2026-06-12-threads-leadgenerator-design.md).

## Setup

```bash
uv sync
cp .env.example .env
# отредактируй .env: впиши свои THREADS_USERNAME и THREADS_PASSWORD
```

## Запуск

### Скрапер
```bash
uv run python scripts/run_scraper.py
```
Активен только 09:00–23:00 локального времени (настраивается в `SCRAPER_ACTIVE_HOURS`). Можно повесить на Windows Task Scheduler с дневным триггером — сам уйдёт спать в 23:00.

### MCP-сервер
Уже подключён через `.mcp.json` — Claude Code поднимет его автоматически при старте сессии в этой папке. Проверить:

```
/mcp
```

Должна появиться запись `threads-leadgen` со статусом `connected` и списком тулов.

## Типичный флоу

```
> добавь тему "поиск идей для контента", прикинь пару фраз и проверь объёмы

(Claude думает, дёргает probe_keywords, отчитывается)

> закоммить ту, что с объёмом > 20

> покажи 30 новых лидов и отметь релевантные

(Claude перебирает list_unreviewed, для каждого mark_post)

> покажи статистику за неделю
```

## Тесты

```bash
uv run pytest
```

Smoke-тест Threads (требует креды) — отдельно:
```bash
uv run pytest tests/test_threads_client_smoke.py -v -s
```
````

- [ ] **Step 5: Verify everything runs**

Run: `uv run pytest -v`
Expected: all tests green.

Run: `uv run python scripts/run_mcp.py` (then Ctrl+C)
Expected: starts, awaits stdio input, exits cleanly on Ctrl+C.

- [ ] **Step 6: Commit + push**

```bash
git add scripts/ .mcp.json README.md
git commit -m "feat: runner scripts, .mcp.json wiring, README usage"
git push
```

---

## Done criteria

- [ ] `uv run pytest` — all green
- [ ] `uv run pytest tests/test_threads_client_smoke.py -v -s` — passes against real Threads
- [ ] `/mcp` in Claude Code shows `threads-leadgen` connected
- [ ] In Claude Code: `list_topics()` returns `[]` (empty DB), no errors
- [ ] Manual probe flow works: add a topic, probe keywords, commit, see them in `list_topics` with `keyword_count > 0`
- [ ] Scraper runs without errors for at least one cycle, post counts increase

## Known follow-ups (deferred)

- VPS deploy (after MVP proves useful)
- Auto-reply via MCP tool
- Multiple donor accounts in rotation
- Thread-reply context (parent post + replies)
- Hashtag/account-based crawling (currently only keyword search)
