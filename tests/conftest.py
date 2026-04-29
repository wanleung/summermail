import sqlite3
import pytest
from pathlib import Path


SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


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
