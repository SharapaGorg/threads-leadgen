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
