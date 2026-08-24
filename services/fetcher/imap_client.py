import email
import email.header
import hashlib
import imaplib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from shared.config import settings
from shared.models import Email


def _message_id_hash(message_id: str) -> str:
    """Generate deterministic SHA-256 hash of a message ID."""
    return hashlib.sha256(message_id.encode()).hexdigest()


def _decode_header(value: str) -> str:
    """Decode email header value, handling MIME-encoded text."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace") if payload else ""
        return ""
    payload = msg.get_payload(decode=True)
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace") if payload else ""


def _parse_email_message(msg: email.message.Message, is_read: bool = False) -> Email:
    """Parse email message into Email dataclass."""
    raw_from = msg.get("From", "")
    sender_name, sender_email = parseaddr(raw_from)
    sender_name = _decode_header(sender_name)

    raw_date = msg.get("Date", "")
    try:
        received_at = parsedate_to_datetime(raw_date).astimezone(timezone.utc)
    except Exception:
        received_at = datetime.now(timezone.utc)

    message_id = msg.get("Message-ID", "")
    if not message_id:
        stable = f"{sender_email}|{raw_date}|{msg.get('Subject', '')}"
        message_id = f"<generated-{hashlib.sha256(stable.encode()).hexdigest()}>"
    email_id = _message_id_hash(message_id)

    raw_labels = msg.get("X-Gmail-Labels", "")
    labels = [lbl.strip() for lbl in raw_labels.split(",") if lbl.strip()]

    return Email(
        id=email_id,
        thread_id=msg.get("X-GM-THRID", ""),
        subject=_decode_header(msg.get("Subject", "(no subject)")),
        sender_email=sender_email.lower(),
        sender_name=sender_name,
        received_at=received_at,
        body_text=_extract_body(msg),
        labels=labels,
        is_read=is_read,
    )


def _insert_email(em: Email, conn: sqlite3.Connection) -> bool:
    """Insert email into database, skip silently if already exists. Returns True if inserted."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO emails (id, thread_id, subject, sender_email, sender_name, "
        "received_at, body_text, labels, is_read) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            em.id, em.thread_id, em.subject, em.sender_email, em.sender_name,
            em.received_at.isoformat(), em.body_text, json.dumps(em.labels), em.is_read,
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def _last_successful_run(conn: sqlite3.Connection) -> Optional[datetime]:
    """Return the completion time of the last successful fetch, as UTC."""
    row = conn.execute(
        "SELECT completed_at FROM fetch_runs WHERE status='success' "
        "ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    if not row or not row["completed_at"]:
        return None
    parsed = datetime.fromisoformat(row["completed_at"])
    # SQLite datetime('now') is UTC but naive
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class IMAPClient:
    """IMAP client for fetching emails from Gmail."""

    def __init__(self):
        """Initialize IMAP client with Gmail credentials from settings."""
        self.host = "imap.gmail.com"
        self.user = settings.gmail_user
        self.password = settings.gmail_app_password.get_secret_value()

    def fetch_emails(self, scope: str, conn: sqlite3.Connection) -> int:
        """Fetch emails and store in DB. Returns count of new emails inserted."""
        mail = imaplib.IMAP4_SSL(self.host)
        try:
            mail.login(self.user, self.password)
            mail.select("INBOX")
            cutoff = self._window_start(scope, conn)
            _, data = mail.search(None, self._build_criteria(scope, cutoff))
            if not data or not data[0]:
                return 0

            ids = data[0].split()
            inserted = 0
            for uid in ids:
                # BODY.PEEK[] fetches full message without marking it as read
                # FLAGS fetches current read/seen status
                _, msg_data = mail.fetch(uid, "(FLAGS BODY.PEEK[])")
                flags_raw = msg_data[0][0]  # e.g. b'1 (FLAGS (\\Seen) BODY.PEEK[] ...'
                is_read = b"\\Seen" in flags_raw
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                em = _parse_email_message(msg, is_read=is_read)
                # IMAP SINCE has date-only granularity, so it over-returns by up
                # to a day; trim to the window actually asked for.
                if cutoff and em.received_at < cutoff:
                    continue
                if _insert_email(em, conn):
                    inserted += 1

            return inserted
        finally:
            mail.logout()

    def _window_start(self, scope: str, conn: sqlite3.Connection) -> Optional[datetime]:
        """Return the earliest received_at to accept, or None for no time bound."""
        if scope == "unread":
            return None
        if scope == "since_last_run":
            last = _last_successful_run(conn)
            if last:
                return last
        return datetime.now(timezone.utc) - timedelta(hours=24)

    def _build_criteria(self, scope: str, cutoff: Optional[datetime]) -> str:
        """Build IMAP search criteria for the given scope and window start."""
        if scope == "unread" or cutoff is None:
            return "UNSEEN"
        return f'SINCE "{cutoff.strftime("%d-%b-%Y")}"'
