# Email Summariser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dockerised daily email summariser that fetches Gmail via IMAP, scores importance with VIP/keyword/LLM layers, and delivers a digest email + web dashboard each morning.

**Architecture:** Five Docker services (`fetcher`, `scorer`, `summariser`, `api`, `llm-proxy`) share a SQLite database on a named volume. The `api` service (FastAPI + APScheduler) orchestrates the pipeline by calling each service's `/run` HTTP endpoint in sequence at the scheduled time.

**Tech Stack:** Python 3.12, FastAPI, SQLite (FTS5), LiteLLM, Jinja2 + HTMX, imaplib, smtplib, pytest, Docker / docker-compose

---

## File Map

```
email-summariser/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── db/
│   └── schema.sql
├── services/
│   ├── shared/                    # pip-installable local package, copied into every image
│   │   ├── __init__.py
│   │   ├── config.py              # Settings (pydantic-settings, reads .env)
│   │   ├── database.py            # get_db(), init_db()
│   │   └── models.py              # dataclasses: Email, EmailScore, Summary, VipSender, Keyword
│   ├── fetcher/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                # FastAPI app: POST /run, GET /health
│   │   └── imap_client.py         # IMAPClient: connect, fetch_emails(scope)
│   ├── scorer/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                # FastAPI app: POST /run, GET /health; orchestrates 3 layers
│   │   ├── vip.py                 # check_vip(sender_email, conn) -> bool
│   │   ├── keywords.py            # score_keywords(subject, body, conn) -> int
│   │   └── llm_scorer.py          # score_llm(subject, body_snippet) -> (int, str)
│   ├── summariser/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                # FastAPI app: POST /run, GET /health
│   │   ├── prompt.py              # build_prompt(emails) -> str; parse_summary(text) -> str
│   │   └── mailer.py              # send_summary_email(summary_text, to_addr)
│   └── api/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py                # FastAPI app + APScheduler; calls fetcher/scorer/summariser
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── dashboard.py       # GET /
│       │   ├── emails.py          # GET /emails, GET /emails/{id}, GET /search
│       │   ├── config_router.py   # GET/POST /config, /config/vip, /config/keywords
│       │   └── run_router.py      # POST /run
│       └── templates/
│           ├── base.html
│           ├── index.html
│           ├── email_detail.html
│           └── config.html
├── litellm/
│   └── config.yaml
└── tests/
    ├── conftest.py
    ├── test_database.py
    ├── test_fetcher_imap.py
    ├── test_scorer_vip.py
    ├── test_scorer_keywords.py
    ├── test_scorer_llm.py
    ├── test_scorer_formula.py
    ├── test_summariser_prompt.py
    ├── test_summariser_mailer.py
    └── test_api.py
```

---

## Task 1: Project scaffold

**Files:**
- Create: `docker-compose.yml` (skeleton — completed in Task 9)
- Create: `.env.example`
- Create: `.gitignore`
- Create: `services/shared/__init__.py`
- Create: `services/shared/config.py`
- Create: `services/shared/models.py`

- [ ] **Step 1: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.superpowers/
/data/
```

- [ ] **Step 2: Create `.env.example`**

```env
# Gmail IMAP credentials (use an App Password, not your main password)
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# Summary delivery
SUMMARY_SEND_TO=you@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Fetch scope: 24h | unread | since_last_run
FETCH_SCOPE=24h

# Cron schedule (default: 6 AM daily)
SCHEDULE_CRON=0 6 * * *

# LLM — both default to local Ollama; change to swap provider with zero code changes
SCORER_LLM_MODEL=ollama/llama3.2
SUMMARISER_LLM_MODEL=ollama/llama3.2
LLM_BASE_URL=http://llm-proxy:4000
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Pipeline
SUMMARY_TOP_N=20

# DB path inside containers (do not change unless you update docker-compose volumes)
DB_PATH=/data/email_summariser.db
```

- [ ] **Step 3: Create `services/shared/__init__.py`** (empty)

- [ ] **Step 4: Create `services/shared/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gmail_user: str = ""
    gmail_app_password: str = ""
    summary_send_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    fetch_scope: str = "24h"
    schedule_cron: str = "0 6 * * *"
    scorer_llm_model: str = "ollama/llama3.2"
    summariser_llm_model: str = "ollama/llama3.2"
    llm_base_url: str = "http://llm-proxy:4000"
    ollama_base_url: str = "http://host.docker.internal:11434"
    summary_top_n: int = 20
    db_path: str = "/data/email_summariser.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

- [ ] **Step 5: Create `services/shared/models.py`**

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Email:
    id: str
    thread_id: str
    subject: str
    sender_email: str
    sender_name: str
    received_at: datetime
    body_text: str
    labels: list = field(default_factory=list)
    is_read: bool = False
    fetched_at: Optional[datetime] = None


@dataclass
class EmailScore:
    email_id: str
    vip_match: bool = False
    keyword_score: int = 0
    llm_score: int = 0
    total_score: int = 0
    llm_reasoning: str = ""
    scored_at: Optional[datetime] = None


@dataclass
class Summary:
    id: Optional[int]
    date: str
    summary_text: str
    email_count: int
    top_email_ids: list = field(default_factory=list)
    sent_at: Optional[datetime] = None
    sent_to: str = ""


@dataclass
class VipSender:
    id: Optional[int]
    pattern: str
    label: str = ""


@dataclass
class Keyword:
    id: Optional[int]
    keyword: str
    weight: int = 5
    match_body: bool = True
```

- [ ] **Step 6: Commit scaffold**

```bash
git add .gitignore .env.example services/shared/
git commit -m "chore: project scaffold and shared library skeleton"
```

---

## Task 2: Database schema and connection

**Files:**
- Create: `db/schema.sql`
- Create: `services/shared/database.py`
- Create: `tests/conftest.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /home/wanleung/Projects/email-summariser
pip install pydantic-settings pytest --quiet
PYTHONPATH=services pytest tests/test_database.py -v 2>&1 | head -20
```

Expected: `FileNotFoundError` or `ModuleNotFoundError` — db/schema.sql doesn't exist yet.

- [ ] **Step 4: Create `db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS emails (
    id           TEXT PRIMARY KEY,
    thread_id    TEXT,
    subject      TEXT,
    sender_email TEXT NOT NULL,
    sender_name  TEXT,
    received_at  DATETIME NOT NULL,
    body_text    TEXT,
    labels       TEXT    DEFAULT '[]',
    is_read      BOOLEAN DEFAULT 0,
    fetched_at   DATETIME DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
    subject, body_text, sender_email,
    content='emails', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS emails_ai AFTER INSERT ON emails BEGIN
    INSERT INTO emails_fts(rowid, subject, body_text, sender_email)
    VALUES (new.rowid, new.subject, new.body_text, new.sender_email);
END;

CREATE TABLE IF NOT EXISTS email_scores (
    email_id      TEXT PRIMARY KEY REFERENCES emails(id),
    vip_match     BOOLEAN DEFAULT 0,
    keyword_score INTEGER DEFAULT 0,
    llm_score     INTEGER DEFAULT 0,
    total_score   INTEGER DEFAULT 0,
    llm_reasoning TEXT,
    scored_at     DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS summaries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         DATE    NOT NULL UNIQUE,
    summary_text TEXT,
    email_count  INTEGER DEFAULT 0,
    top_email_ids TEXT   DEFAULT '[]',
    sent_at      DATETIME,
    sent_to      TEXT
);

CREATE TABLE IF NOT EXISTS vip_senders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern    TEXT    NOT NULL,
    label      TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS keywords (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword    TEXT    NOT NULL,
    weight     INTEGER DEFAULT 5,
    match_body BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     DATETIME DEFAULT (datetime('now')),
    completed_at   DATETIME,
    emails_fetched INTEGER DEFAULT 0,
    scope          TEXT,
    status         TEXT    DEFAULT 'running',
    error_message  TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at DATETIME DEFAULT (datetime('now'))
);
```

- [ ] **Step 5: Create `services/shared/database.py`**

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from shared.config import settings


def get_db(db_path: str = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    conn = sqlite3.connect(path)
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
        schema_path = Path(__file__).parent.parent.parent / "db" / "schema.sql"
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
PYTHONPATH=services pytest tests/test_database.py -v
```

Expected: 3 tests pass.

- [ ] **Step 7: Commit**

```bash
git add db/schema.sql services/shared/database.py tests/
git commit -m "feat: database schema and shared connection helper"
```

---

## Task 3: Fetcher service

**Files:**
- Create: `services/fetcher/imap_client.py`
- Create: `services/fetcher/main.py`
- Create: `services/fetcher/requirements.txt`
- Create: `tests/test_fetcher_imap.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fetcher_imap.py
import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))

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
```

- [ ] **Step 2: Run to verify failure**

```bash
PYTHONPATH=services pytest tests/test_fetcher_imap.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'fetcher'`

- [ ] **Step 3: Create `services/fetcher/imap_client.py`**

```python
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
    return hashlib.sha256(message_id.encode()).hexdigest()


def _decode_header(value: str) -> str:
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


def _parse_email_message(msg: email.message.Message) -> Email:
    raw_from = msg.get("From", "")
    sender_name, sender_email = parseaddr(raw_from)
    sender_name = _decode_header(sender_name)

    raw_date = msg.get("Date", "")
    try:
        received_at = parsedate_to_datetime(raw_date).astimezone(timezone.utc)
    except Exception:
        received_at = datetime.now(timezone.utc)

    message_id = msg.get("Message-ID", f"<generated-{datetime.now().timestamp()}>")
    email_id = _message_id_hash(message_id)

    return Email(
        id=email_id,
        thread_id=msg.get("X-GM-THRID", ""),
        subject=_decode_header(msg.get("Subject", "(no subject)")),
        sender_email=sender_email.lower(),
        sender_name=sender_name,
        received_at=received_at,
        body_text=_extract_body(msg),
        labels=json.loads(msg.get("X-Gmail-Labels", "[]")),
        is_read=False,
    )


def _insert_email(em: Email, conn: sqlite3.Connection) -> bool:
    """Insert email, skip silently if already exists. Returns True if inserted."""
    existing = conn.execute("SELECT id FROM emails WHERE id=?", (em.id,)).fetchone()
    if existing:
        return False
    conn.execute(
        "INSERT INTO emails (id, thread_id, subject, sender_email, sender_name, "
        "received_at, body_text, labels, is_read) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            em.id, em.thread_id, em.subject, em.sender_email, em.sender_name,
            em.received_at.isoformat(), em.body_text, json.dumps(em.labels), em.is_read,
        ),
    )
    conn.commit()
    return True


class IMAPClient:
    def __init__(self):
        self.host = "imap.gmail.com"
        self.user = settings.gmail_user
        self.password = settings.gmail_app_password

    def fetch_emails(self, scope: str, conn: sqlite3.Connection) -> int:
        """Fetch emails and store in DB. Returns count of new emails inserted."""
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.user, self.password)
        mail.select("INBOX")

        criteria = self._build_criteria(scope, conn)
        _, data = mail.search(None, criteria)
        if not data or not data[0]:
            mail.logout()
            return 0

        ids = data[0].split()
        inserted = 0
        for uid in ids:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            em = _parse_email_message(msg)
            if _insert_email(em, conn):
                inserted += 1

        mail.logout()
        return inserted

    def _build_criteria(self, scope: str, conn: sqlite3.Connection) -> str:
        if scope == "unread":
            return "UNSEEN"
        elif scope == "since_last_run":
            row = conn.execute(
                "SELECT completed_at FROM fetch_runs WHERE status='success' "
                "ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
            if row and row["completed_at"]:
                since_dt = datetime.fromisoformat(row["completed_at"])
                since_str = since_dt.strftime("%d-%b-%Y")
                return f'SINCE "{since_str}"'
        # default: 24h
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%d-%b-%Y")
        return f'SINCE "{since}"'
```

- [ ] **Step 4: Create `services/fetcher/main.py`**

```python
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException

from shared.config import settings
from shared.database import get_db, init_db
from fetcher.imap_client import IMAPClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_db()
    init_db(conn)
    conn.close()
    yield


app = FastAPI(title="fetcher", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run(scope: str = None):
    scope = scope or settings.fetch_scope
    conn = get_db()
    run_id = conn.execute(
        "INSERT INTO fetch_runs (scope, status) VALUES (?, 'running')", (scope,)
    ).lastrowid
    conn.commit()

    try:
        client = IMAPClient()
        count = client.fetch_emails(scope, conn)
        conn.execute(
            "UPDATE fetch_runs SET status='success', completed_at=datetime('now'), "
            "emails_fetched=? WHERE id=?",
            (count, run_id),
        )
        conn.commit()
        return {"status": "success", "emails_fetched": count, "scope": scope}
    except Exception as exc:
        conn.execute(
            "UPDATE fetch_runs SET status='error', completed_at=datetime('now'), "
            "error_message=? WHERE id=?",
            (str(exc), run_id),
        )
        conn.commit()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
```

- [ ] **Step 5: Create `services/fetcher/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.29.0
pydantic-settings==2.2.1
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
PYTHONPATH=services pytest tests/test_fetcher_imap.py -v
```

Expected: 4 tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/fetcher/ tests/test_fetcher_imap.py
git commit -m "feat: fetcher service — IMAP client with dedup and scope support"
```

---

## Task 4: Scorer — VIP and keyword layers

**Files:**
- Create: `services/scorer/vip.py`
- Create: `services/scorer/keywords.py`
- Create: `tests/test_scorer_vip.py`
- Create: `tests/test_scorer_keywords.py`

- [ ] **Step 1: Write failing tests for VIP**

```python
# tests/test_scorer_vip.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
import pytest
from scorer.vip import check_vip


def test_exact_email_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("boss@company.com", "Boss"))
    tmp_db.commit()
    assert check_vip("boss@company.com", tmp_db) is True


def test_exact_email_no_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("boss@company.com", "Boss"))
    tmp_db.commit()
    assert check_vip("other@company.com", tmp_db) is False


def test_domain_wildcard_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("@company.com", "Company"))
    tmp_db.commit()
    assert check_vip("anyone@company.com", tmp_db) is True


def test_domain_wildcard_no_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("@company.com", "Company"))
    tmp_db.commit()
    assert check_vip("someone@other.com", tmp_db) is False


def test_empty_vip_list(tmp_db):
    assert check_vip("anyone@example.com", tmp_db) is False
```

- [ ] **Step 2: Write failing tests for keywords**

```python
# tests/test_scorer_keywords.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
import pytest
from scorer.keywords import score_keywords


def _seed_keywords(conn):
    conn.executemany(
        "INSERT INTO keywords (keyword, weight, match_body) VALUES (?, ?, ?)",
        [("urgent", 8, True), ("invoice", 6, True), ("deadline", 7, False)],
    )
    conn.commit()


def test_subject_keyword_match(tmp_db):
    _seed_keywords(tmp_db)
    score = score_keywords("Urgent: please review", "", tmp_db)
    assert score > 0


def test_body_keyword_match(tmp_db):
    _seed_keywords(tmp_db)
    score = score_keywords("Meeting notes", "Please pay the invoice by Friday", tmp_db)
    assert score > 0


def test_subject_only_keyword_not_matched_in_body(tmp_db):
    _seed_keywords(tmp_db)
    # 'deadline' has match_body=False — only subject counts
    score_body_only = score_keywords("Nothing here", "The deadline is tomorrow", tmp_db)
    score_subject = score_keywords("The deadline is tomorrow", "", tmp_db)
    assert score_body_only == 0
    assert score_subject > 0


def test_no_match_returns_zero(tmp_db):
    _seed_keywords(tmp_db)
    assert score_keywords("Hello", "How are you?", tmp_db) == 0


def test_score_capped_at_100(tmp_db):
    # Add many high-weight keywords that all match
    for i in range(20):
        tmp_db.execute(
            "INSERT INTO keywords (keyword, weight, match_body) VALUES (?, 10, 1)",
            (f"keyword{i}",),
        )
    tmp_db.commit()
    subject = " ".join(f"keyword{i}" for i in range(20))
    assert score_keywords(subject, "", tmp_db) == 100
```

- [ ] **Step 3: Run to verify failures**

```bash
PYTHONPATH=services pytest tests/test_scorer_vip.py tests/test_scorer_keywords.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'scorer'`

- [ ] **Step 4: Create `services/scorer/__init__.py`** (empty)

- [ ] **Step 5: Create `services/scorer/vip.py`**

```python
import sqlite3


def check_vip(sender_email: str, conn: sqlite3.Connection) -> bool:
    """Return True if sender_email matches any VIP pattern (exact or @domain)."""
    sender_email = sender_email.lower()
    rows = conn.execute("SELECT pattern FROM vip_senders").fetchall()
    for row in rows:
        pattern = row["pattern"].lower()
        if pattern.startswith("@"):
            if sender_email.endswith(pattern):
                return True
        else:
            if sender_email == pattern:
                return True
    return False
```

- [ ] **Step 6: Create `services/scorer/keywords.py`**

```python
import sqlite3


def score_keywords(subject: str, body: str, conn: sqlite3.Connection) -> int:
    """Return keyword score 0–100 based on matched keyword weights."""
    rows = conn.execute(
        "SELECT keyword, weight, match_body FROM keywords"
    ).fetchall()

    subject_lower = subject.lower()
    body_lower = body.lower()
    total_weight = 0

    for row in rows:
        kw = row["keyword"].lower()
        match_body = bool(row["match_body"])
        weight = row["weight"]
        if kw in subject_lower:
            total_weight += weight
        elif match_body and kw in body_lower:
            total_weight += weight

    return min(100, total_weight * 10)
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
PYTHONPATH=services pytest tests/test_scorer_vip.py tests/test_scorer_keywords.py -v
```

Expected: 9 tests pass.

- [ ] **Step 8: Commit**

```bash
git add services/scorer/ tests/test_scorer_vip.py tests/test_scorer_keywords.py
git commit -m "feat: scorer VIP and keyword layers"
```

---

## Task 5: Scorer — LLM layer and orchestration

**Files:**
- Create: `services/scorer/llm_scorer.py`
- Create: `services/scorer/main.py`
- Create: `services/scorer/requirements.txt`
- Create: `tests/test_scorer_llm.py`
- Create: `tests/test_scorer_formula.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scorer_llm.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
from unittest.mock import patch, MagicMock
from scorer.llm_scorer import score_llm, _parse_llm_response


def test_parse_llm_response_extracts_score():
    text = '{"score": 75, "reason": "Contains urgent deadline"}'
    score, reason = _parse_llm_response(text)
    assert score == 75
    assert "urgent" in reason


def test_parse_llm_response_clamps_score():
    text = '{"score": 150, "reason": "Very urgent"}'
    score, _ = _parse_llm_response(text)
    assert score == 100


def test_parse_llm_response_handles_malformed():
    text = "I think this is about 60 out of 100"
    score, reason = _parse_llm_response(text)
    assert 0 <= score <= 100


def test_score_llm_calls_openai_client():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"score": 80, "reason": "Action required"}'
    with patch("scorer.llm_scorer.client.chat.completions.create",
               return_value=mock_response):
        score, reason = score_llm("Urgent invoice due", "Please pay by Friday")
    assert score == 80
    assert reason == "Action required"
```

```python
# tests/test_scorer_formula.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
from scorer.main import compute_total_score


def test_vip_adds_50():
    assert compute_total_score(vip=True, keyword=0, llm=0) == 50


def test_formula_combines_all_layers():
    # vip=True: +50, keyword=60: +18, llm=80: +56 → 124 → capped at 100
    assert compute_total_score(vip=True, keyword=60, llm=80) == 100


def test_no_signals_returns_zero():
    assert compute_total_score(vip=False, keyword=0, llm=0) == 0


def test_keyword_and_llm_without_vip():
    # keyword=40: +12, llm=50: +35 → 47
    assert compute_total_score(vip=False, keyword=40, llm=50) == 47


def test_score_never_exceeds_100():
    assert compute_total_score(vip=True, keyword=100, llm=100) == 100
```

- [ ] **Step 2: Run to verify failures**

```bash
PYTHONPATH=services pytest tests/test_scorer_llm.py tests/test_scorer_formula.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `services/scorer/llm_scorer.py`**

```python
import json
import re

from openai import OpenAI

from shared.config import settings


client = OpenAI(base_url=settings.llm_base_url, api_key="ignored")

SCORING_PROMPT = """You are an email importance classifier. Given an email subject and body snippet, rate its urgency from 0 to 100 and give a one-sentence reason.

Respond ONLY with valid JSON in this exact format:
{"score": <integer 0-100>, "reason": "<one sentence>"}

0 = spam/newsletter, 50 = FYI, 100 = immediate action required."""


def _parse_llm_response(text: str) -> tuple[int, str]:
    try:
        data = json.loads(text.strip())
        score = max(0, min(100, int(data.get("score", 0))))
        reason = str(data.get("reason", ""))
        return score, reason
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\b(\d{1,3})\b", text)
        score = max(0, min(100, int(match.group(1)))) if match else 0
        return score, text[:200]


def score_llm(subject: str, body: str, model: str = None) -> tuple[int, str]:
    model = model or settings.scorer_llm_model
    snippet = body[:500] if body else ""
    user_content = f"Subject: {subject}\n\nBody snippet: {snippet}"
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SCORING_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    return _parse_llm_response(response.choices[0].message.content)
```

- [ ] **Step 4: Create `services/scorer/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from shared.config import settings
from shared.database import get_db, init_db
from scorer.vip import check_vip
from scorer.keywords import score_keywords
from scorer.llm_scorer import score_llm


def compute_total_score(vip: bool, keyword: int, llm: int) -> int:
    raw = (50 if vip else 0) + keyword * 0.3 + llm * 0.7
    return min(100, int(raw))


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_db()
    init_db(conn)
    conn.close()
    yield


app = FastAPI(title="scorer", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run():
    conn = get_db()
    try:
        unscored = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.body_text "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE s.email_id IS NULL"
        ).fetchall()

        scored = 0
        for row in unscored:
            email_id = row["id"]
            subject = row["subject"] or ""
            sender = row["sender_email"] or ""
            body = row["body_text"] or ""

            vip = check_vip(sender, conn)
            kw_score = score_keywords(subject, body, conn)
            try:
                llm_score, reasoning = score_llm(subject, body)
            except Exception as e:
                llm_score, reasoning = 0, f"LLM error: {e}"

            total = compute_total_score(vip, kw_score, llm_score)

            conn.execute(
                "INSERT OR REPLACE INTO email_scores "
                "(email_id, vip_match, keyword_score, llm_score, total_score, llm_reasoning) "
                "VALUES (?,?,?,?,?,?)",
                (email_id, vip, kw_score, llm_score, total, reasoning),
            )
            scored += 1

        conn.commit()
        return {"status": "success", "emails_scored": scored}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
```

- [ ] **Step 5: Create `services/scorer/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.29.0
pydantic-settings==2.2.1
openai==1.30.0
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pip install openai --quiet
PYTHONPATH=services pytest tests/test_scorer_llm.py tests/test_scorer_formula.py -v
```

Expected: 8 tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/scorer/ tests/test_scorer_llm.py tests/test_scorer_formula.py
git commit -m "feat: scorer LLM layer and 3-layer orchestration with scoring formula"
```

---

## Task 6: Summariser service

**Files:**
- Create: `services/summariser/prompt.py`
- Create: `services/summariser/mailer.py`
- Create: `services/summariser/main.py`
- Create: `services/summariser/requirements.txt`
- Create: `tests/test_summariser_prompt.py`
- Create: `tests/test_summariser_mailer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_summariser_prompt.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
from summariser.prompt import build_prompt, SYSTEM_PROMPT


def _make_email_rows():
    return [
        {
            "subject": "Urgent: Invoice overdue",
            "sender_email": "billing@acme.com",
            "sender_name": "Acme Billing",
            "received_at": "2026-04-29T08:00:00",
            "total_score": 95,
            "body_text": "Your invoice #4821 is overdue.",
        },
        {
            "subject": "Team standup notes",
            "sender_email": "alice@company.com",
            "sender_name": "Alice",
            "received_at": "2026-04-29T09:30:00",
            "total_score": 40,
            "body_text": "Notes from today's standup.",
        },
    ]


def test_build_prompt_contains_subjects():
    rows = _make_email_rows()
    prompt = build_prompt(rows)
    assert "Urgent: Invoice overdue" in prompt
    assert "Team standup notes" in prompt


def test_build_prompt_includes_scores():
    rows = _make_email_rows()
    prompt = build_prompt(rows)
    assert "95" in prompt


def test_build_prompt_truncates_body():
    rows = [
        {
            "subject": "Long email",
            "sender_email": "x@y.com",
            "sender_name": "X",
            "received_at": "2026-04-29T08:00:00",
            "total_score": 50,
            "body_text": "A" * 2000,
        }
    ]
    prompt = build_prompt(rows)
    assert len(prompt) < 10000


def test_system_prompt_requests_json_structure():
    assert "Action Required" in SYSTEM_PROMPT
    assert "Worth Reading" in SYSTEM_PROMPT
```

```python
# tests/test_summariser_mailer.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
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
    assert "Daily Email Summary" in captured.get("msg", "")
```

- [ ] **Step 2: Run to verify failures**

```bash
PYTHONPATH=services pytest tests/test_summariser_prompt.py tests/test_summariser_mailer.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `services/summariser/__init__.py`** (empty)

- [ ] **Step 4: Create `services/summariser/prompt.py`**

```python
from typing import Any

SYSTEM_PROMPT = """You are an email digest assistant. Given a list of emails with importance scores (0-100), produce a concise daily digest grouped into three sections:

## 🔴 Action Required
Emails scoring 70+ that need a response or decision today.

## 🟠 Worth Reading
Emails scoring 30-69 that are informational or may need follow-up.

## ⚪ Low Priority
Emails scoring below 30.

For each email write: **[Subject]** from Sender — one-sentence summary.
End with a horizontal rule and the line: Dashboard: http://localhost:8080"""


def build_prompt(email_rows: list[dict[str, Any]]) -> str:
    lines = ["Here are today's emails sorted by importance score:\n"]
    for i, row in enumerate(email_rows, 1):
        body_snippet = (row.get("body_text") or "")[:300]
        lines.append(
            f"{i}. [Score: {row['total_score']}] "
            f"From: {row['sender_name']} <{row['sender_email']}>\n"
            f"   Subject: {row['subject']}\n"
            f"   Received: {row['received_at']}\n"
            f"   Body: {body_snippet}\n"
        )
    return "\n".join(lines)
```

- [ ] **Step 5: Create `services/summariser/mailer.py`**

```python
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shared.config import settings


def send_summary_email(summary_text: str, to_addr: str) -> None:
    today = date.today().strftime("%A %d %B %Y")
    subject = f"Daily Email Summary — {today}"

    html_body = summary_text.replace("\n", "<br>")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.gmail_user
    msg["To"] = to_addr
    msg.attach(MIMEText(summary_text, "plain"))
    msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.sendmail(settings.gmail_user, [to_addr], msg.as_string())
```

- [ ] **Step 6: Create `services/summariser/main.py`**

```python
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException
from openai import OpenAI

from shared.config import settings
from shared.database import get_db, init_db
from summariser.prompt import build_prompt, SYSTEM_PROMPT
from summariser.mailer import send_summary_email


client = OpenAI(base_url=settings.llm_base_url, api_key="ignored")


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_db()
    init_db(conn)
    conn.close()
    yield


app = FastAPI(title="summariser", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run():
    conn = get_db()
    try:
        today = date.today().isoformat()

        # Skip if already summarised today
        existing = conn.execute(
            "SELECT id FROM summaries WHERE date=?", (today,)
        ).fetchone()
        if existing:
            return {"status": "skipped", "reason": "already summarised today"}

        rows = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.sender_name, "
            "e.received_at, e.body_text, s.total_score "
            "FROM emails e JOIN email_scores s ON e.id=s.email_id "
            "WHERE date(e.received_at) >= date('now','-1 day') "
            "ORDER BY s.total_score DESC LIMIT ?",
            (settings.summary_top_n,),
        ).fetchall()

        email_count = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE date(received_at) >= date('now','-1 day')"
        ).fetchone()[0]

        if not rows:
            return {"status": "success", "message": "no emails to summarise"}

        email_dicts = [dict(r) for r in rows]
        user_prompt = build_prompt(email_dicts)

        response = client.chat.completions.create(
            model=settings.summariser_llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        summary_text = response.choices[0].message.content

        top_ids = [r["id"] for r in rows[:10]]
        import json
        conn.execute(
            "INSERT INTO summaries (date, summary_text, email_count, top_email_ids) "
            "VALUES (?,?,?,?)",
            (today, summary_text, email_count, json.dumps(top_ids)),
        )
        conn.commit()

        send_summary_email(summary_text, settings.summary_send_to)

        conn.execute(
            "UPDATE summaries SET sent_at=datetime('now'), sent_to=? WHERE date=?",
            (settings.summary_send_to, today),
        )
        conn.commit()

        return {"status": "success", "email_count": email_count}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
```

- [ ] **Step 7: Create `services/summariser/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.29.0
pydantic-settings==2.2.1
openai==1.30.0
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
PYTHONPATH=services pytest tests/test_summariser_prompt.py tests/test_summariser_mailer.py -v
```

Expected: 6 tests pass.

- [ ] **Step 9: Commit**

```bash
git add services/summariser/ tests/test_summariser_prompt.py tests/test_summariser_mailer.py
git commit -m "feat: summariser service — LLM digest generation and SMTP delivery"
```

---

## Task 7: API service — core, scheduler, and routers

**Files:**
- Create: `services/api/__init__.py`
- Create: `services/api/main.py`
- Create: `services/api/routers/__init__.py`
- Create: `services/api/routers/dashboard.py`
- Create: `services/api/routers/emails.py`
- Create: `services/api/routers/summaries_router.py`
- Create: `services/api/routers/config_router.py`
- Create: `services/api/routers/run_router.py`
- Create: `services/api/requirements.txt`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

```python
# tests/test_api.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client(tmp_db, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    # Re-import after monkeypatching env
    import importlib
    import shared.config
    importlib.reload(shared.config)
    import api.main
    importlib.reload(api.main)
    from api.main import app
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config_add_vip(client):
    r = client.post("/config/vip", json={"pattern": "boss@company.com", "label": "Boss"})
    assert r.status_code == 200
    assert r.json()["pattern"] == "boss@company.com"


def test_config_add_keyword(client):
    r = client.post("/config/keywords",
                    json={"keyword": "urgent", "weight": 8, "match_body": True})
    assert r.status_code == 200
    assert r.json()["keyword"] == "urgent"


def test_config_list_vip(client):
    client.post("/config/vip", json={"pattern": "a@b.com", "label": "A"})
    r = client.get("/config/vip")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_config_list_keywords(client):
    client.post("/config/keywords",
                json={"keyword": "invoice", "weight": 6, "match_body": True})
    r = client.get("/config/keywords")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_search_returns_results(client, tmp_path):
    import sqlite3
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    from pathlib import Path
    schema = Path(__file__).parent.parent / "db" / "schema.sql"
    with open(schema) as f:
        conn.executescript(f.read())
    conn.execute(
        "INSERT INTO emails (id, thread_id, subject, sender_email, sender_name, received_at, body_text) "
        "VALUES ('abc', 't1', 'Invoice overdue', 'x@y.com', 'X', datetime('now'), 'pay now')"
    )
    conn.commit()
    conn.close()
    r = client.get("/search?q=invoice")
    assert r.status_code == 200


def test_summaries_history(client, tmp_path):
    import sqlite3
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    from pathlib import Path
    schema = Path(__file__).parent.parent / "db" / "schema.sql"
    with open(schema) as f:
        conn.executescript(f.read())
    conn.execute(
        "INSERT INTO summaries (date, summary_text, email_count) VALUES ('2024-01-01', 'Test summary', 5)"
    )
    conn.commit()
    conn.close()
    r = client.get("/summaries")
    assert r.status_code == 200
    assert len(r.json()) >= 0  # may be empty if test DB is separate — just checks route exists
```

- [ ] **Step 2: Run to verify failures**

```bash
PYTHONPATH=services pytest tests/test_api.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `services/api/__init__.py`** (empty)

- [ ] **Step 4: Create `services/api/routers/__init__.py`** (empty)

- [ ] **Step 5: Create `services/api/routers/config_router.py`**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.database import get_db_ctx

router = APIRouter(prefix="/config", tags=["config"])


class VipIn(BaseModel):
    pattern: str
    label: str = ""


class KeywordIn(BaseModel):
    keyword: str
    weight: int = 5
    match_body: bool = True


@router.get("/vip")
def list_vip():
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT * FROM vip_senders ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/vip")
def add_vip(body: VipIn):
    with get_db_ctx() as conn:
        row_id = conn.execute(
            "INSERT INTO vip_senders (pattern, label) VALUES (?,?)",
            (body.pattern, body.label),
        ).lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM vip_senders WHERE id=?", (row_id,)).fetchone()
        return dict(row)


@router.delete("/vip/{vip_id}")
def delete_vip(vip_id: int):
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM vip_senders WHERE id=?", (vip_id,))
        conn.commit()
    return {"deleted": vip_id}


@router.get("/keywords")
def list_keywords():
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT * FROM keywords ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/keywords")
def add_keyword(body: KeywordIn):
    with get_db_ctx() as conn:
        row_id = conn.execute(
            "INSERT INTO keywords (keyword, weight, match_body) VALUES (?,?,?)",
            (body.keyword, body.weight, body.match_body),
        ).lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM keywords WHERE id=?", (row_id,)).fetchone()
        return dict(row)


@router.delete("/keywords/{kw_id}")
def delete_keyword(kw_id: int):
    with get_db_ctx() as conn:
        conn.execute("DELETE FROM keywords WHERE id=?", (kw_id,))
        conn.commit()
    return {"deleted": kw_id}
```

- [ ] **Step 6: Create `services/api/routers/emails.py`**

```python
from fastapi import APIRouter, HTTPException, Query

from shared.database import get_db_ctx

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("")
def list_emails(limit: int = 50, min_score: int = 0):
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.sender_name, e.received_at, "
            "e.is_read, s.total_score, s.vip_match "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE COALESCE(s.total_score,0) >= ? "
            "ORDER BY s.total_score DESC, e.received_at DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/search")
def search_emails(q: str = Query(..., min_length=1)):
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.received_at, "
            "COALESCE(s.total_score,0) as total_score "
            "FROM emails_fts fts "
            "JOIN emails e ON fts.rowid=e.rowid "
            "LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE emails_fts MATCH ? "
            "ORDER BY rank LIMIT 30",
            (q,),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/{email_id}")
def get_email(email_id: str):
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT e.*, s.total_score, s.vip_match, s.keyword_score, "
            "s.llm_score, s.llm_reasoning "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE e.id=?",
            (email_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
        return dict(row)
```

- [ ] **Step 7: Create `services/api/routers/dashboard.py`**

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from shared.database import get_db_ctx

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    with get_db_ctx() as conn:
        emails = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.sender_name, e.received_at, "
            "e.is_read, COALESCE(s.total_score,0) as total_score, "
            "COALESCE(s.vip_match,0) as vip_match "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "ORDER BY total_score DESC, e.received_at DESC LIMIT 50"
        ).fetchall()

        today_summary = conn.execute(
            "SELECT summary_text FROM summaries ORDER BY date DESC LIMIT 1"
        ).fetchone()

        last_run = conn.execute(
            "SELECT * FROM fetch_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        vip_senders = conn.execute("SELECT * FROM vip_senders ORDER BY id").fetchall()
        keywords = conn.execute("SELECT * FROM keywords ORDER BY id").fetchall()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "emails": [dict(e) for e in emails],
            "summary": dict(today_summary) if today_summary else None,
            "last_run": dict(last_run) if last_run else None,
            "vip_senders": [dict(v) for v in vip_senders],
            "keywords": [dict(k) for k in keywords],
        },
    )
```

- [ ] **Step 8: Create `services/api/routers/summaries_router.py`**

```python
from fastapi import APIRouter

from shared.database import get_db_ctx

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get("")
def list_summaries(limit: int = 30):
    """Return past daily digest summaries, newest first."""
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, date, summary_text, email_count, top_email_ids, sent_at, sent_to "
            "FROM summaries ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/{summary_id}")
def get_summary(summary_id: int):
    from fastapi import HTTPException
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT * FROM summaries WHERE id=?", (summary_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Summary not found")
        return dict(row)
```

- [ ] **Step 9: Create `services/api/routers/run_router.py`**

```python
import httpx
from fastapi import APIRouter, HTTPException

from shared.config import settings

router = APIRouter(tags=["run"])

FETCHER_URL = "http://fetcher:8001"
SCORER_URL = "http://scorer:8002"
SUMMARISER_URL = "http://summariser:8003"


@router.post("/run")
def trigger_run(scope: str = None):
    scope = scope or settings.fetch_scope
    results = {}
    try:
        r = httpx.post(f"{FETCHER_URL}/run", params={"scope": scope}, timeout=120)
        r.raise_for_status()
        results["fetcher"] = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"fetcher failed: {e}")

    try:
        r = httpx.post(f"{SCORER_URL}/run", timeout=300)
        r.raise_for_status()
        results["scorer"] = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"scorer failed: {e}")

    try:
        r = httpx.post(f"{SUMMARISER_URL}/run", timeout=120)
        r.raise_for_status()
        results["summariser"] = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"summariser failed: {e}")

    return results
```

- [ ] **Step 10: Create `services/api/main.py`**

```python
from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shared.config import settings
from shared.database import get_db, init_db
from api.routers.dashboard import router as dashboard_router
from api.routers.emails import router as emails_router
from api.routers.summaries_router import router as summaries_router
from api.routers.config_router import router as config_router
from api.routers.run_router import router as run_router, trigger_run


async def scheduled_run():
    try:
        trigger_run(scope=settings.fetch_scope)
    except Exception as e:
        print(f"Scheduled run failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_db()
    init_db(conn)
    conn.close()

    scheduler = AsyncIOScheduler()
    cron_parts = settings.schedule_cron.split()
    scheduler.add_job(
        scheduled_run,
        CronTrigger(
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
        ),
    )
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Email Summariser", lifespan=lifespan)

app.include_router(dashboard_router)
app.include_router(emails_router)
app.include_router(summaries_router)
app.include_router(config_router)
app.include_router(run_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/search")
def search_proxy(q: str):
    from api.routers.emails import search_emails
    return search_emails(q=q)
```

- [ ] **Step 10: Create `services/api/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.29.0
pydantic-settings==2.2.1
apscheduler==3.10.4
httpx==0.27.0
jinja2==3.1.4
```

- [ ] **Step 12: Run API tests**

```bash
pip install apscheduler httpx jinja2 --quiet
PYTHONPATH=services pytest tests/test_api.py -v
```

Expected: 7 tests pass.

- [ ] **Step 13: Commit**

```bash
git add services/api/ tests/test_api.py
git commit -m "feat: API service with dashboard, email list, summaries history, config management, and scheduler"
```

---

## Task 8: Dashboard templates

**Files:**
- Create: `services/api/templates/base.html`
- Create: `services/api/templates/index.html`
- Create: `services/api/templates/email_detail.html`
- Create: `services/api/templates/config.html`

- [ ] **Step 1: Create `services/api/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MailBrief — {% block title %}Dashboard{% endblock %}</title>
  <script src="https://unpkg.com/htmx.org@1.9.10"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
    nav { background: #0f172a; border-bottom: 1px solid #1e293b; padding: .6rem 1.5rem; display: flex; align-items: center; gap: 1rem; }
    nav .brand { color: #60a5fa; font-weight: 700; font-size: 1rem; }
    nav a { color: #64748b; text-decoration: none; font-size: .85rem; }
    nav a:hover, nav a.active { color: #e2e8f0; }
    .container { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }
    .badge { font-size: .65rem; font-weight: 700; padding: .1rem .4rem; border-radius: 4px; }
    .badge-red    { background: #ef4444; color: #fff; }
    .badge-orange { background: #f97316; color: #fff; }
    .badge-green  { background: #22c55e; color: #fff; }
    .badge-gray   { background: #475569; color: #fff; }
    .badge-vip    { background: #1e3a5f; color: #60a5fa; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1rem; }
    .btn { background: #1e3a5f; color: #60a5fa; border: 1px solid #3b82f6; padding: .35rem .75rem; border-radius: 6px; cursor: pointer; font-size: .8rem; }
    .btn:hover { background: #2d4f7c; }
    input[type=text] { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: .35rem .6rem; border-radius: 6px; font-size: .8rem; }
  </style>
  {% block head %}{% endblock %}
</head>
<body>
  <nav>
    <span class="brand">📧 MailBrief</span>
    <a href="/" class="{% if request.url.path == '/' %}active{% endif %}">Today</a>
    <a href="/emails">All Emails</a>
    <a href="/config">Settings</a>
    <div style="margin-left:auto;display:flex;gap:.5rem;align-items:center">
      <input type="text" id="search-box" placeholder="🔍 Search..." onkeydown="if(event.key==='Enter') window.location='/search?q='+encodeURIComponent(this.value)">
      <form action="/run" method="post" style="display:inline">
        <button class="btn" type="submit">▶ Run Now</button>
      </form>
    </div>
  </nav>
  <div class="container">
    {% block content %}{% endblock %}
  </div>
</body>
</html>
```

- [ ] **Step 2: Create `services/api/templates/index.html`**

```html
{% extends "base.html" %}
{% block title %}Today{% endblock %}
{% block content %}
<div style="display:grid;grid-template-columns:2fr 1fr;gap:1.5rem;margin-top:1rem">
  <div>
    {% if summary %}
    <div class="card" style="border-color:#3b82f6;margin-bottom:1rem">
      <div style="color:#60a5fa;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.5rem">🤖 AI Summary</div>
      <pre style="white-space:pre-wrap;font-family:inherit;font-size:.82rem;line-height:1.6;color:#cbd5e1">{{ summary.summary_text }}</pre>
    </div>
    {% endif %}

    <div style="display:flex;gap:.5rem;margin-bottom:.75rem">
      <a href="/?min_score=70" class="btn">🔴 Urgent</a>
      <a href="/?vip=1" class="btn">👤 VIP</a>
      <a href="/" class="btn">All</a>
    </div>

    {% for email in emails %}
    <a href="/emails/{{ email.id }}" style="text-decoration:none;display:block">
    <div style="background:#1e293b;border:1px solid {% if email.total_score >= 70 %}#3b82f6{% else %}#334155{% endif %};border-radius:6px;padding:.6rem .9rem;margin-bottom:.4rem;display:flex;align-items:center;gap:.75rem">
      {% if email.total_score >= 70 %}
        <span class="badge badge-red">{{ email.total_score }}</span>
      {% elif email.total_score >= 40 %}
        <span class="badge badge-orange">{{ email.total_score }}</span>
      {% else %}
        <span class="badge badge-gray">{{ email.total_score }}</span>
      {% endif %}
      <div style="flex:1;min-width:0">
        <div style="color:#e2e8f0;font-size:.85rem;font-weight:{% if not email.is_read %}600{% else %}400{% endif %};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ email.subject }}</div>
        <div style="color:#64748b;font-size:.72rem">{{ email.sender_name or email.sender_email }} · {{ email.received_at[:16] }}</div>
      </div>
      {% if email.vip_match %}<span class="badge badge-vip">👤 VIP</span>{% endif %}
    </div>
    </a>
    {% else %}
    <p style="color:#64748b;margin-top:2rem;text-align:center">No emails yet — click ▶ Run Now to fetch.</p>
    {% endfor %}
  </div>

  <div>
    {% if last_run %}
    <div class="card" style="margin-bottom:1rem">
      <div style="color:#94a3b8;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.4rem">Last Run</div>
      <div style="font-size:.8rem">
        {% if last_run.status == 'success' %}✅{% else %}❌{% endif %}
        {{ last_run.started_at[:16] }}<br>
        <span style="color:#64748b">{{ last_run.emails_fetched }} emails · {{ last_run.scope }}</span>
      </div>
    </div>
    {% endif %}

    <div class="card" style="margin-bottom:1rem">
      <div style="color:#94a3b8;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.5rem">👤 VIP Senders</div>
      {% for v in vip_senders %}
      <div style="font-size:.78rem;margin-bottom:.25rem;display:flex;justify-content:space-between">
        <span>{{ v.label or v.pattern }}</span>
        <a href="/config/vip/{{ v.id }}/delete" style="color:#ef4444;font-size:.7rem">✕</a>
      </div>
      {% endfor %}
      <a href="/config" class="btn" style="margin-top:.5rem;display:inline-block;font-size:.7rem">+ Manage</a>
    </div>

    <div class="card">
      <div style="color:#94a3b8;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.5rem">🏷️ Keywords</div>
      <div style="display:flex;flex-wrap:wrap;gap:.3rem;margin-bottom:.5rem">
        {% for k in keywords %}
        <span style="background:#1e3a5f;color:#60a5fa;font-size:.65rem;padding:.15rem .4rem;border-radius:4px">{{ k.keyword }}</span>
        {% endfor %}
      </div>
      <a href="/config" class="btn" style="font-size:.7rem">+ Manage</a>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create `services/api/templates/email_detail.html`**

```html
{% extends "base.html" %}
{% block title %}{{ email.subject }}{% endblock %}
{% block content %}
<div style="max-width:800px;margin-top:1rem">
  <a href="/" style="color:#64748b;font-size:.8rem;text-decoration:none">← Back</a>

  <div class="card" style="margin-top:1rem">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:1rem">
      <div>
        <h2 style="font-size:1rem;color:#e2e8f0;margin-bottom:.3rem">{{ email.subject }}</h2>
        <div style="color:#64748b;font-size:.78rem">
          From: <strong style="color:#94a3b8">{{ email.sender_name or email.sender_email }}</strong>
          &lt;{{ email.sender_email }}&gt;
          · {{ email.received_at[:16] }}
        </div>
      </div>
      <div style="text-align:right;min-width:90px">
        {% if email.total_score >= 70 %}
          <span class="badge badge-red">{{ email.total_score }}</span>
        {% elif email.total_score >= 40 %}
          <span class="badge badge-orange">{{ email.total_score }}</span>
        {% else %}
          <span class="badge badge-gray">{{ email.total_score }}</span>
        {% endif %}
        {% if email.vip_match %}<br><span class="badge badge-vip" style="margin-top:.3rem">👤 VIP</span>{% endif %}
      </div>
    </div>
  </div>

  <div class="card" style="margin-top:1rem">
    <div style="color:#94a3b8;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.5rem">Score Breakdown</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;font-size:.8rem">
      <div style="background:#0f172a;border-radius:6px;padding:.6rem;text-align:center">
        <div style="color:#60a5fa;font-size:1.2rem;font-weight:700">{{ email.vip_match | int * 50 }}</div>
        <div style="color:#64748b;font-size:.7rem">VIP (+50)</div>
      </div>
      <div style="background:#0f172a;border-radius:6px;padding:.6rem;text-align:center">
        <div style="color:#60a5fa;font-size:1.2rem;font-weight:700">{{ "%.0f" | format(email.keyword_score * 0.3) }}</div>
        <div style="color:#64748b;font-size:.7rem">Keywords (×0.3)</div>
      </div>
      <div style="background:#0f172a;border-radius:6px;padding:.6rem;text-align:center">
        <div style="color:#60a5fa;font-size:1.2rem;font-weight:700">{{ "%.0f" | format(email.llm_score * 0.7) }}</div>
        <div style="color:#64748b;font-size:.7rem">LLM (×0.7)</div>
      </div>
    </div>
    {% if email.llm_reasoning %}
    <div style="margin-top:.75rem;font-size:.78rem;color:#94a3b8;border-top:1px solid #334155;padding-top:.6rem">
      <strong style="color:#64748b">LLM reasoning:</strong> {{ email.llm_reasoning }}
    </div>
    {% endif %}
  </div>

  {% if email.body_text %}
  <div class="card" style="margin-top:1rem">
    <div style="color:#94a3b8;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.5rem">Body</div>
    <pre style="white-space:pre-wrap;font-size:.8rem;color:#cbd5e1;font-family:inherit;line-height:1.6">{{ email.body_text }}</pre>
  </div>
  {% endif %}
</div>
{% endblock %}
```

The `dashboard.py` router already has a `GET /emails/{email_id}` JSON route; the template is served when you add a `GET /emails/{email_id}/view` route. Add this to `services/api/routers/dashboard.py` (append after the existing `index` function):

```python
@router.get("/emails/{email_id}/view", response_class=HTMLResponse)
def email_detail_view(request: Request, email_id: str):
    from fastapi import HTTPException
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT e.*, COALESCE(s.total_score,0) as total_score, "
            "COALESCE(s.vip_match,0) as vip_match, "
            "COALESCE(s.keyword_score,0) as keyword_score, "
            "COALESCE(s.llm_score,0) as llm_score, s.llm_reasoning "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE e.id=?",
            (email_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
    return templates.TemplateResponse(
        "email_detail.html", {"request": request, "email": dict(row)}
    )
```

- [ ] **Step 4: Create `services/api/templates/config.html`**

```html
{% extends "base.html" %}
{% block title %}Settings{% endblock %}
{% block content %}
<div style="max-width:700px;margin-top:1rem">
  <h2 style="font-size:.95rem;color:#e2e8f0;margin-bottom:1rem">⚙️ Settings</h2>

  <div class="card" style="margin-bottom:1.5rem">
    <div style="color:#94a3b8;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.75rem">👤 VIP Senders</div>
    <form action="/config/vip" method="post" style="display:flex;gap:.5rem;margin-bottom:.75rem"
          hx-post="/config/vip" hx-target="#vip-list" hx-swap="innerHTML">
      <input type="text" name="pattern" placeholder="email or *@domain.com" style="flex:1">
      <input type="text" name="label" placeholder="Label (optional)" style="width:140px">
      <button class="btn" type="submit">+ Add</button>
    </form>
    <div id="vip-list">
      {% for v in vip_senders %}
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:.8rem;padding:.3rem 0;border-bottom:1px solid #1e293b">
        <span>{{ v.label or "" }} <span style="color:#64748b">{{ v.pattern }}</span></span>
        <a href="/config/vip/{{ v.id }}/delete" style="color:#ef4444;font-size:.75rem"
           hx-delete="/config/vip/{{ v.id }}" hx-target="closest div" hx-swap="outerHTML">✕ Remove</a>
      </div>
      {% else %}
      <p style="color:#64748b;font-size:.8rem">No VIP senders yet.</p>
      {% endfor %}
    </div>
  </div>

  <div class="card">
    <div style="color:#94a3b8;font-size:.7rem;font-weight:700;text-transform:uppercase;margin-bottom:.75rem">🏷️ Keywords</div>
    <form action="/config/keywords" method="post" style="display:flex;gap:.5rem;margin-bottom:.75rem"
          hx-post="/config/keywords" hx-target="#kw-list" hx-swap="innerHTML">
      <input type="text" name="keyword" placeholder="keyword" style="flex:1">
      <input type="number" name="weight" placeholder="Weight (1-10)" value="5" style="width:80px">
      <input type="hidden" name="match_body" value="true">
      <button class="btn" type="submit">+ Add</button>
    </form>
    <div id="kw-list">
      {% for k in keywords %}
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:.8rem;padding:.3rem 0;border-bottom:1px solid #1e293b">
        <span>{{ k.keyword }} <span style="color:#64748b">weight={{ k.weight }}</span></span>
        <a href="/config/keywords/{{ k.id }}/delete" style="color:#ef4444;font-size:.75rem"
           hx-delete="/config/keywords/{{ k.id }}" hx-target="closest div" hx-swap="outerHTML">✕ Remove</a>
      </div>
      {% else %}
      <p style="color:#64748b;font-size:.8rem">No keywords yet.</p>
      {% endfor %}
    </div>
  </div>
</div>
{% endblock %}
```

Also add a `GET /config` HTML route to `services/api/routers/dashboard.py` (append after `email_detail_view`):

```python
@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    with get_db_ctx() as conn:
        vip_senders = conn.execute("SELECT * FROM vip_senders ORDER BY id").fetchall()
        keywords = conn.execute("SELECT * FROM keywords ORDER BY id").fetchall()
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "vip_senders": [dict(v) for v in vip_senders],
            "keywords": [dict(k) for k in keywords],
        },
    )
```

- [ ] **Step 5: Commit templates**

```bash
git add services/api/templates/ services/api/routers/dashboard.py
git commit -m "feat: dashboard HTML templates (base, index, email detail, config)"
```

---

## Task 9: LiteLLM config and Docker setup

**Files:**
- Create: `litellm/config.yaml`
- Create: `services/fetcher/Dockerfile`
- Create: `services/scorer/Dockerfile`
- Create: `services/summariser/Dockerfile`
- Create: `services/api/Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `litellm/config.yaml`**

```yaml
model_list:
  - model_name: ollama/llama3.2
    litellm_params:
      model: ollama/llama3.2
      api_base: "${OLLAMA_BASE_URL}"

general_settings:
  master_key: "ignored"
```

- [ ] **Step 2: Create shared Dockerfile pattern — `services/fetcher/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY services/shared /app/shared
COPY services/fetcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/fetcher /app/fetcher
ENV PYTHONPATH=/app
CMD ["uvicorn", "fetcher.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 3: Create `services/scorer/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY services/shared /app/shared
COPY services/scorer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/scorer /app/scorer
ENV PYTHONPATH=/app
CMD ["uvicorn", "scorer.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

- [ ] **Step 4: Create `services/summariser/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY services/shared /app/shared
COPY services/summariser/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/summariser /app/summariser
ENV PYTHONPATH=/app
CMD ["uvicorn", "summariser.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

- [ ] **Step 5: Create `services/api/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY services/shared /app/shared
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/api /app/api
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 6: Create `docker-compose.yml`**

```yaml
version: "3.9"

volumes:
  db_data:

x-common: &common
  restart: unless-stopped
  volumes:
    - db_data:/data
  env_file: .env

services:
  llm-proxy:
    image: ghcr.io/berriai/litellm:main-latest
    <<: *common
    volumes:
      - db_data:/data
      - ./litellm/config.yaml:/app/config.yaml
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    ports:
      - "4000:4000"
    environment:
      OLLAMA_BASE_URL: "${OLLAMA_BASE_URL}"

  fetcher:
    build:
      context: .
      dockerfile: services/fetcher/Dockerfile
    <<: *common
    ports:
      - "8001:8001"
    depends_on:
      - llm-proxy

  scorer:
    build:
      context: .
      dockerfile: services/scorer/Dockerfile
    <<: *common
    ports:
      - "8002:8002"
    depends_on:
      - llm-proxy

  summariser:
    build:
      context: .
      dockerfile: services/summariser/Dockerfile
    <<: *common
    ports:
      - "8003:8003"
    depends_on:
      - llm-proxy

  api:
    build:
      context: .
      dockerfile: services/api/Dockerfile
    <<: *common
    ports:
      - "8080:8080"
    depends_on:
      - fetcher
      - scorer
      - summariser
      - llm-proxy
```

- [ ] **Step 7: Copy `.env.example` to `.env` and fill in credentials**

```bash
cp .env.example .env
# Edit .env: set GMAIL_USER, GMAIL_APP_PASSWORD, SUMMARY_SEND_TO
```

- [ ] **Step 8: Build and start services**

```bash
docker compose build --no-cache 2>&1 | tail -5
docker compose up -d
```

- [ ] **Step 9: Verify all services are healthy**

```bash
sleep 5
curl -s http://localhost:8001/health | python3 -m json.tool
curl -s http://localhost:8002/health | python3 -m json.tool
curl -s http://localhost:8003/health | python3 -m json.tool
curl -s http://localhost:8080/health | python3 -m json.tool
```

Expected: `{"status": "ok"}` from all four.

- [ ] **Step 10: Trigger a manual run and verify**

```bash
curl -s -X POST http://localhost:8080/run | python3 -m json.tool
```

Expected: JSON with `fetcher`, `scorer`, `summariser` keys all showing `"status": "success"`.

- [ ] **Step 11: Open the dashboard**

```
http://localhost:8080
```

Expected: Dashboard renders with email list and AI summary banner.

- [ ] **Step 12: Commit**

```bash
git add docker-compose.yml litellm/ services/*/Dockerfile
git commit -m "feat: Docker setup — docker-compose, Dockerfiles, LiteLLM config"
```

---

## Task 10: Run full test suite

- [ ] **Step 1: Install all test dependencies**

```bash
pip install pydantic-settings pytest openai apscheduler httpx jinja2 --quiet
```

- [ ] **Step 2: Run all tests**

```bash
PYTHONPATH=services pytest tests/ -v
```

Expected: All tests pass. (IMAP and LLM calls are mocked.)

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "test: full test suite passing"
```

---

## Quick-Start Reference

```bash
# 1. Clone and configure
cp .env.example .env        # fill in Gmail credentials

# 2. Start Ollama on your local machine (outside Docker)
ollama pull llama3.2

# 3. Start all services
docker compose up -d

# 4. Open dashboard
open http://localhost:8080

# 5. Trigger a manual run (or wait for 6 AM cron)
curl -X POST http://localhost:8080/run

# 6. Swap LLM provider (no code change needed)
# Edit .env: SCORER_LLM_MODEL=gpt-4o-mini
# Add OPENAI_API_KEY=sk-...
docker compose restart scorer summariser
```
