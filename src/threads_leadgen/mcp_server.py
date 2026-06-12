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

    def probe_keywords(keywords: list[str]) -> list[dict]:
        if threads_client is None:
            raise RuntimeError("threads client not initialised; cannot probe")
        if hasattr(threads_client, "_client") and threads_client._client is None:
            threads_client.login()
        out = []
        for kw in keywords:
            volume, samples = threads_client.probe_volume_7d(kw)
            out.append({"keyword": kw, "volume_7d": volume, "samples": samples})
        return out

    def commit_keywords(topic_id: int, keywords: list[str]) -> list[int]:
        with dbmod.connect(db_path) as conn:
            return dbmod.add_keywords(conn, topic_id, keywords)

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

    return {
        "list_topics": list_topics,
        "add_topic": add_topic,
        "pause_topic": pause_topic,
        "resume_topic": resume_topic,
        "probe_keywords": probe_keywords,
        "commit_keywords": commit_keywords,
        "list_unreviewed": list_unreviewed,
        "get_post": get_post,
        "mark_post": mark_post,
    }


def create_server(db_path: Path, threads_client: ThreadsClient | None) -> FastMCP:
    mcp = FastMCP("threads-leadgen")
    tools = build_tools(db_path, threads_client)

    @mcp.tool()
    def list_topics() -> list[dict]:
        """Все темы со счётчиками ключевиков и постов."""
        return tools["list_topics"]()

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

    @mcp.tool()
    def probe_keywords(keywords: list[str]) -> list[dict]:
        """Прикинуть, сколько постов за 7 дней по каждой фразе + 3 примера. Дёргает Threads — НЕ запускай на 50 фразах сразу."""
        return tools["probe_keywords"](keywords)

    @mcp.tool()
    def commit_keywords(topic_id: int, keywords: list[str]) -> list[int]:
        """Привязать ключевики к теме. Дубликаты игнорятся. Скрапер подхватит со следующего цикла."""
        return tools["commit_keywords"](topic_id, keywords)

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

    return mcp
