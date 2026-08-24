# tests/test_fetcher_imap.py
import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
import sys, os

from fetcher.imap_client import IMAPClient, _message_id_hash, _parse_email_message


def test_message_id_hash_is_deterministic():
    h1 = _message_id_hash("<msg-001@gmail.com>")
    h2 = _message_id_hash("<msg-001@gmail.com>")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_message_id_hash_differs_for_different_ids():
    h1 = _message_id_hash("<msg-001@gmail.com>")
    h2 = _message_id_hash("<msg-002@gmail.com>")
    assert h1 != h2


def test_parse_email_message_extracts_fields():
    import email
    raw = (
        "From: Alice <alice@example.com>\r\n"
        "Subject: Hello world\r\n"
        "Message-ID: <unique-id-123@mail>\r\n"
        "Date: Tue, 29 Apr 2026 06:00:00 +0000\r\n"
        "Content-Type: text/plain\r\n\r\n"
        "This is the body."
    )
    msg = email.message_from_string(raw)
    result = _parse_email_message(msg)
    assert result.subject == "Hello world"
    assert result.sender_email == "alice@example.com"
    assert result.sender_name == "Alice"
    assert result.body_text == "This is the body."
    assert result.id == _message_id_hash("<unique-id-123@mail>")


def test_imap_client_deduplicates_by_id(tmp_db):
    """Inserting the same message twice should not raise and should store only once."""
    from fetcher.imap_client import _insert_email
    import email as emaillib
    raw = (
        "From: Bob <bob@example.com>\r\nSubject: Dup\r\n"
        "Message-ID: <dup@mail>\r\nDate: Tue, 29 Apr 2026 06:00:00 +0000\r\n"
        "Content-Type: text/plain\r\n\r\nBody"
    )
    msg = emaillib.message_from_string(raw)
    from fetcher.imap_client import _parse_email_message
    em = _parse_email_message(msg)
    _insert_email(em, tmp_db)
    _insert_email(em, tmp_db)  # second insert — must not raise
    count = tmp_db.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    assert count == 1


def _raw_message(msg_id, date_str):
    return (
        f"From: Carol <carol@example.com>\r\nSubject: S\r\n"
        f"Message-ID: <{msg_id}@mail>\r\nDate: {date_str}\r\n"
        "Content-Type: text/plain\r\n\r\nBody"
    ).encode()


def test_fetch_emails_excludes_messages_older_than_the_24h_window(tmp_db, monkeypatch):
    """IMAP SINCE is date-only, so results must be filtered to the real 24h window."""
    from email.utils import format_datetime
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    recent = format_datetime(now - timedelta(hours=2))
    old = format_datetime(now - timedelta(hours=40))

    mail = MagicMock()
    mail.search.return_value = ("OK", [b"1 2"])
    mail.fetch.side_effect = [
        ("OK", [(b"1 (FLAGS (\\Seen) BODY[] {10}", _raw_message("recent", recent))]),
        ("OK", [(b"2 (FLAGS () BODY[] {10}", _raw_message("old", old))]),
    ]

    monkeypatch.setenv("GMAIL_USER", "test@example.com")
    with patch("imaplib.IMAP4_SSL", return_value=mail):
        inserted = IMAPClient().fetch_emails("24h", tmp_db)

    subjects = tmp_db.execute("SELECT id FROM emails").fetchall()
    assert inserted == 1
    assert len(subjects) == 1
    assert subjects[0]["id"] == _message_id_hash("<recent@mail>")
