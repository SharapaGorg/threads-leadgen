from pathlib import Path
import pytest
from threads_leadgen.config import Config


def test_config_from_env_file(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "THREADS_USERNAME=alice\n"
        "THREADS_PASSWORD=secret\n"
        "DB_PATH=/tmp/leads.db\n"
        "SESSION_PATH=/tmp/session.json\n"
        "SCRAPER_ACTIVE_HOURS=10-22\n"
    )
    cfg = Config.from_env(env)
    assert cfg.threads_username == "alice"
    assert cfg.threads_password == "secret"
    assert cfg.db_path == Path("/tmp/leads.db")
    assert cfg.session_path == Path("/tmp/session.json")
    assert cfg.active_hours_start == 10
    assert cfg.active_hours_end == 22


def test_config_missing_required(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("THREADS_USERNAME", raising=False)
    monkeypatch.delenv("THREADS_PASSWORD", raising=False)
    env = tmp_path / ".env"
    env.write_text("DB_PATH=/tmp/leads.db\n")
    with pytest.raises(RuntimeError, match="THREADS_USERNAME"):
        Config.from_env(env)


def test_config_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("SESSION_PATH", raising=False)
    monkeypatch.delenv("SCRAPER_ACTIVE_HOURS", raising=False)
    env = tmp_path / ".env"
    env.write_text("THREADS_USERNAME=a\nTHREADS_PASSWORD=b\n")
    cfg = Config.from_env(env)
    assert cfg.db_path == Path("./data/leads.db")
    assert cfg.session_path == Path("./data/session.json")
    assert cfg.active_hours_start == 9
    assert cfg.active_hours_end == 23
