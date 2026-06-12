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
