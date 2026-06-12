import sqlite3
import pytest
from threads_leadgen.db import init_db_connection


@pytest.fixture
def conn():
    """In-memory SQLite with schema, foreign keys enabled, row_factory set."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db_connection(conn)
    yield conn
    conn.close()
