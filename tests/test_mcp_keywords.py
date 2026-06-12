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
