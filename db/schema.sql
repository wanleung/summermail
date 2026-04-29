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
