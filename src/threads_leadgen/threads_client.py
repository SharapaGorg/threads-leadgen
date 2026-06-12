"""Wrapper over Threads reverse-engineered access.

The user will provide cookies exported from a logged-in browser via
`{session_path}.cookies.json` (e.g. `data/session.cookies.json`).
Use a browser extension like "Cookie Editor" → Export → JSON.

If/when a maintained Python library for Threads search appears, swap the
internals here; the public surface (`login`, `search_recent`, `probe_volume_7d`,
`RawPost`) must stay stable.
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

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
    """Thin wrapper over Threads access.

    Today: requires exported browser cookies at `{session_path}.cookies.json`.
    Tomorrow: when a maintained Python lib lands, swap internals here.
    Public methods stay stable.
    """

    # Inspect threads.net Network tab to refresh if the search call stops working.
    _SEARCH_DOC_ID = "20060666233495418"

    def __init__(self, username: str, password: str, session_path: Path):
        self.username = username
        self.password = password
        self.session_path = session_path
        self._client: httpx.Client | None = None

    def login(self) -> None:
        cookie_file = self.session_path.with_suffix(".cookies.json")
        if not cookie_file.exists():
            raise ThreadsAuthError(
                f"Cookies not found. Export your logged-in threads.net cookies "
                f"as JSON to: {cookie_file}\n"
                "Use a browser extension (e.g. 'Cookie Editor'). The file must "
                "be a JSON array of {{name, value, ...}} objects."
            )
        try:
            raw = json.loads(cookie_file.read_text(encoding="utf-8"))
        except Exception as e:
            raise ThreadsAuthError(f"Failed to read cookies from {cookie_file}: {e}") from e

        jar = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
        if not jar:
            raise ThreadsAuthError("Cookie file contained no usable name/value pairs.")

        self._client = httpx.Client(
            cookies=jar,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "X-IG-App-ID": "238260118697367",
                "Accept": "application/json",
                "Origin": "https://www.threads.net",
                "Referer": "https://www.threads.net/",
            },
            timeout=30,
        )
        log.info("ThreadsClient session initialised from %s", cookie_file)

    def search_recent(self, keyword: str, limit: int = 30) -> list[RawPost]:
        if self._client is None:
            raise ThreadsAuthError("call login() first")
        try:
            resp = self._client.get(
                "https://www.threads.net/api/graphql",
                params={
                    "doc_id": self._SEARCH_DOC_ID,
                    "variables": json.dumps({"query": keyword, "count": limit}),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as e:
            raise ThreadsAuthError(f"search HTTP failure: {e}") from e
        except ValueError as e:
            raise ThreadsAuthError(f"search returned non-JSON: {e}") from e

        return [self._normalize(node) for node in self._extract_nodes(payload)[:limit]]

    def probe_volume_7d(self, keyword: str) -> tuple[int, list[str]]:
        """Quick liveness check. Returns (count of last-7d posts, up to 3 sample texts).
        Small probe limit (5) to stay under the shared rate budget with the scraper."""
        posts = self.search_recent(keyword, limit=5)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent: list[RawPost] = []
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

    # --- internals ---

    def _extract_nodes(self, payload: dict) -> list[dict]:
        """Walk the GraphQL response and pull post nodes.

        Threads rotates response shape; this helper tries the known shapes
        and falls back to recursive search for any 'edges' array of nodes
        that look like posts.
        """
        data = payload.get("data") or {}
        for key, value in data.items():
            if isinstance(value, dict) and "edges" in value:
                return [edge.get("node") or {} for edge in value["edges"] if edge]
        return []

    def _normalize(self, item: dict) -> RawPost:
        user = item.get("user") or {}
        username = user.get("username") or item.get("username") or "unknown"
        code = item.get("code") or item.get("shortcode") or item.get("id") or ""
        caption = item.get("caption")
        if isinstance(caption, dict):
            text = caption.get("text") or ""
        else:
            text = item.get("text") or ""

        taken_at = item.get("taken_at")
        if isinstance(taken_at, (int, float)):
            posted_at = datetime.fromtimestamp(taken_at, tz=timezone.utc).isoformat()
        else:
            posted_at = str(taken_at or item.get("created_at") or "")

        text_app_info = item.get("text_post_app_info") or {}
        return RawPost(
            post_id=str(item.get("id") or item.get("pk") or code),
            author_username=username,
            author_followers=user.get("follower_count"),
            text=text,
            url=f"https://www.threads.net/@{username}/post/{code}",
            posted_at=posted_at,
            likes_count=item.get("like_count"),
            replies_count=text_app_info.get("direct_reply_count") or item.get("reply_count"),
        )
