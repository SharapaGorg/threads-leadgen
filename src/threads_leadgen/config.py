import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    # Reserved for a future programmatic-login path; today auth uses cookies.
    threads_username: str
    threads_password: str
    db_path: Path
    session_path: Path
    active_hours_start: int
    active_hours_end: int

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Config":
        if env_file is not None:
            load_dotenv(env_file, override=True)
        else:
            load_dotenv()
        hours = os.getenv("SCRAPER_ACTIVE_HOURS", "09-23")
        start, end = hours.split("-")
        return cls(
            threads_username=os.getenv("THREADS_USERNAME", ""),
            threads_password=os.getenv("THREADS_PASSWORD", ""),
            db_path=Path(os.getenv("DB_PATH", "./data/leads.db")),
            session_path=Path(os.getenv("SESSION_PATH", "./data/session.json")),
            active_hours_start=int(start),
            active_hours_end=int(end),
        )
