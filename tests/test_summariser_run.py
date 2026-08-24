"""Tests for the summariser /run orchestration."""
import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCHEMA = Path(__file__).parent.parent / "db" / "schema.sql"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "summariser.db")
    conn = sqlite3.connect(path)
    with open(SCHEMA) as f:
        conn.executescript(f.read())
    conn.execute(
        "INSERT INTO emails (id, thread_id, subject, sender_email, sender_name, "
        "received_at, body_text) VALUES ('e1','t','Subj','a@b.com','A',datetime('now'),'body')"
    )
    conn.execute(
        "INSERT INTO email_scores (email_id, total_score) VALUES ('e1', 90)"
    )
    conn.commit()
    conn.close()
    from shared.config import settings
    monkeypatch.setattr(settings, "db_path", path)
    return path


def _llm_response(text="## 🔴 Action Required\n**Subj** from A — thing."):
    response = MagicMock()
    response.choices[0].message.content = text
    return response


def test_run_passes_explicit_timeout_to_llm(db_path):
    """The digest call must carry its own timeout so it cannot outlive the caller's."""
    from summariser.main import run

    create = MagicMock(return_value=_llm_response())
    with patch("summariser.main.client.chat.completions.create", create), \
         patch("summariser.main.send_summary_email"):
        run()

    assert create.call_args.kwargs.get("timeout"), "no timeout passed to the LLM call"


def test_run_retries_after_a_failed_send(db_path):
    """A summary row left unsent must not block a later retry that day."""
    from summariser.main import run

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO summaries (date, summary_text, email_count, sent_at) "
        "VALUES (?, 'stale text', 1, NULL)",
        (date.today().isoformat(),),
    )
    conn.commit()
    conn.close()

    send = MagicMock()
    with patch("summariser.main.client.chat.completions.create",
               return_value=_llm_response()), \
         patch("summariser.main.send_summary_email", send):
        result = run()

    assert result["status"] == "success"
    send.assert_called_once()


def test_run_skips_when_already_sent_today(db_path):
    """An already-delivered digest must not be sent twice."""
    from summariser.main import run

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO summaries (date, summary_text, email_count, sent_at) "
        "VALUES (?, 'sent text', 1, datetime('now'))",
        (date.today().isoformat(),),
    )
    conn.commit()
    conn.close()

    send = MagicMock()
    with patch("summariser.main.send_summary_email", send):
        result = run()

    assert result["status"] == "skipped"
    send.assert_not_called()
