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

    return mcp
