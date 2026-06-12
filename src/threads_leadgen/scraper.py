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
