import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


def get_db(db_path: str = None) -> sqlite3.Connection:
    if db_path is None:
        from shared.config import settings  # deferred: only needed when db_path not supplied
        db_path = settings.db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db_ctx(db_path: str = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that opens a connection, yields it, then closes it."""
    conn = get_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection, schema_path: str = None) -> None:
    if schema_path is None:
        # Try two levels up first (works in Docker: /app/shared -> /app/db)
        _this_dir = Path(__file__).parent
        schema_path = _this_dir.parent / "db" / "schema.sql"
        # Fallback: three levels up for local dev (services/shared -> services -> project_root/db)
        if not schema_path.exists():
            schema_path = _this_dir.parent.parent / "db" / "schema.sql"
    with open(schema_path) as f:
        conn.executescript(f.read())
