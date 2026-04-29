import os
import sqlite3
import pytest
from pathlib import Path


SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


def pytest_configure(config):
    """Set environment variables before any modules are imported."""
    os.environ.setdefault("GMAIL_USER", "test@example.com")
    os.environ.setdefault("GMAIL_APP_PASSWORD", "test-password-1234")
    os.environ.setdefault("SUMMARY_SEND_TO", "recipient@example.com")


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    yield conn
    conn.close()
