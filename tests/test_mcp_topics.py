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
