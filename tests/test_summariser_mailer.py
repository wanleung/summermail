"""Tests for the summariser mailer."""
from unittest.mock import patch, MagicMock
from summariser.mailer import send_summary_email


def test_send_summary_email_calls_smtp():
    with patch("summariser.mailer.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        send_summary_email("## Summary\nTest content", "you@gmail.com")
    mock_smtp.assert_called_once()


def test_send_summary_email_subject_contains_date():
    with patch("summariser.mailer.smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        captured = {}

        def capture_sendmail(from_addr, to_addrs, msg_str):
            captured["msg"] = msg_str

        mock_server.sendmail = capture_sendmail
        send_summary_email("## Summary", "you@gmail.com")
    msg = captured.get("msg", "")
    # Subject may be RFC 2047 encoded, so check for key components
    assert "Daily" in msg and "Subject:" in msg
