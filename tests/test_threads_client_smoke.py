"""Integration smoke test. Requires real Threads creds AND exported cookies.

Run manually after exporting cookies:
    uv run pytest tests/test_threads_client_smoke.py -v -s
"""
import os
from pathlib import Path
import pytest

from threads_leadgen.threads_client import ThreadsClient, ThreadsAuthError


pytestmark = pytest.mark.skipif(
    not (os.getenv("THREADS_USERNAME") and os.getenv("THREADS_PASSWORD")),
    reason="needs THREADS_USERNAME and THREADS_PASSWORD in env",
)


def test_login_and_search(tmp_path: Path):
    from dotenv import load_dotenv
    load_dotenv()
    session_path = tmp_path / "session.json"
    client = ThreadsClient(
        username=os.environ["THREADS_USERNAME"],
        password=os.environ["THREADS_PASSWORD"],
        session_path=session_path,
    )
    try:
        client.login()
    except ThreadsAuthError as e:
        pytest.skip(f"login skipped — likely no cookies exported yet: {e}")

    posts = client.search_recent("идеи для контента", limit=5)
    assert isinstance(posts, list)
    if posts:
        p = posts[0]
        assert p.post_id and p.author_username and p.url.startswith("https://")
        print(f"\nGot {len(posts)} posts. First:\n  @{p.author_username}: {p.text[:120]}")
    else:
        pytest.skip("no posts returned — keyword may be dead or doc_id rotated")
