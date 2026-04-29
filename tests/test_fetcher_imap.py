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
