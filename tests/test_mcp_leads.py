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
