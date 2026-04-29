"""Database connection and initialization module."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from shared.config import settings


def get_db(db_path: str = None) -> sqlite3.Connection:
    """
    Get a connection to the SQLite database.
    
    Args:
        db_path: Optional path to database file. If not provided, uses settings.db_path.
    
    Returns:
        sqlite3.Connection: A connection object with row factory set to sqlite3.Row.
    """
    path = db_path or settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db_ctx(db_path: str = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that opens a database connection, yields it, then closes it.
    
    Usage:
        with get_db_ctx() as conn:
            conn.execute("SELECT * FROM emails")
    
    Args:
        db_path: Optional path to database file. If not provided, uses settings.db_path.
    
    Yields:
        sqlite3.Connection: A database connection.
    """
    conn = get_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection, schema_path: str = None) -> None:
    """
    Initialize the database by executing the schema SQL file.
    
    Args:
        conn: sqlite3.Connection to execute schema against.
        schema_path: Optional path to schema.sql. If not provided, uses default location.
    """
    if schema_path is None:
        schema_path = Path(__file__).parent.parent.parent / "db" / "schema.sql"
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.commit()
