# tests/test_database.py
import sqlite3
import pytest
from shared.database import init_db, get_db


def test_init_db_creates_all_tables(tmp_db):
    conn = tmp_db
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "emails" in tables
    assert "email_scores" in tables
    assert "summaries" in tables
    assert "vip_senders" in tables
    assert "keywords" in tables
    assert "fetch_runs" in tables
    assert "config" in tables


def test_fts5_table_exists(tmp_db):
    result = tmp_db.execute(
        "SELECT name FROM sqlite_master WHERE name='emails_fts'"
    ).fetchone()
    assert result is not None


def test_insert_email(tmp_db):
    tmp_db.execute(
        "INSERT INTO emails (id, thread_id, subject, sender_email, sender_name, received_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        ("msg-001", "thread-1", "Test subject", "alice@example.com", "Alice"),
    )
    tmp_db.commit()
    row = tmp_db.execute("SELECT subject FROM emails WHERE id='msg-001'").fetchone()
    assert row["subject"] == "Test subject"
