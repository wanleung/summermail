"""Tests for the scorer /run orchestration."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

SCHEMA = Path(__file__).parent.parent / "db" / "schema.sql"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Isolated on-disk DB so run() can open and close its own connection."""
    path = str(tmp_path / "scorer.db")
    conn = sqlite3.connect(path)
    with open(SCHEMA) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    from shared.config import settings
    monkeypatch.setattr(settings, "db_path", path)
    return path


def _add_email(path, email_id, subject):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO emails (id, thread_id, subject, sender_email, sender_name, "
        "received_at, body_text) VALUES (?,?,?,?,?,datetime('now'),?)",
        (email_id, "t", subject, "someone@example.com", "Someone", "body"),
    )
    conn.commit()
    conn.close()


def _scores(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = {r["email_id"]: dict(r) for r in conn.execute("SELECT * FROM email_scores")}
    conn.close()
    return rows


def test_run_does_not_persist_score_when_llm_fails(db_path):
    """An LLM outage must leave the email unscored so a later run retries it."""
    from scorer.main import run

    _add_email(db_path, "e1", "Anything")
    with patch("scorer.main.score_llm", side_effect=Exception("Connection refused")):
        result = run()

    assert _scores(db_path) == {}
    assert result["emails_scored"] == 0
    assert result["emails_failed"] == 1


def test_run_persists_successes_alongside_failures(db_path):
    """A single email's LLM failure must not discard the scores that did succeed."""
    from scorer.main import run

    _add_email(db_path, "ok", "Good one")
    _add_email(db_path, "bad", "Bad one")

    def flaky(subject, body, model=None):
        if subject == "Bad one":
            raise Exception("timeout")
        return 80, "urgent"

    with patch("scorer.main.score_llm", side_effect=flaky):
        result = run()

    scores = _scores(db_path)
    assert "ok" in scores and scores["ok"]["llm_score"] == 80
    assert "bad" not in scores
    assert result["emails_scored"] == 1
    assert result["emails_failed"] == 1
