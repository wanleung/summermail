# Email Summariser — Design Spec

**Date:** 2026-04-29  
**Status:** Approved

---

## Problem

A high-volume Gmail inbox makes it hard to identify important emails daily. Gmail's built-in filters are insufficient for getting a full picture. A daily morning summary with AI-assisted prioritisation would help triage what matters before starting work.

---

## Goals

- Fetch emails from Gmail via IMAP each morning
- Score emails by importance using three layers: VIP senders, keyword rules, and LLM judgment
- Generate a structured AI digest grouped by urgency/topic
- Deliver the digest as a summary email back to the inbox
- Provide a local web dashboard for interactive review and config management
- Expose an MCP server (Phase 2) for AI assistant integration

---

## Non-Goals (Phase 1)

- Mobile app
- Multi-user / multi-mailbox support
- Automatic email actions (reply, archive, label)
- MCP server (deferred to Phase 2)

---

## Architecture

Five Docker services in `docker-compose.yml`, sharing a SQLite database on a named volume.

```
fetcher ──→ scorer ──→ summariser
                            │
                    ┌───────┴──────────┐
                    │   shared DB      │
                    │  (SQLite vol.)   │
                    └───────┬──────────┘
                            │
                          api  ←── browser (dashboard)
                       llm-proxy ←── scorer + summariser
```

### Services

| Service | Image base | Role |
|---|---|---|
| `fetcher` | `python:3.12-slim` | IMAP fetch → DB |
| `scorer` | `python:3.12-slim` | 3-layer importance scoring |
| `summariser` | `python:3.12-slim` | LLM digest + send email |
| `api` | `python:3.12-slim` | FastAPI web dashboard |
| `llm-proxy` | `ghcr.io/berriai/litellm` | LLM abstraction (Ollama → any provider) |

The `api` service uses APScheduler to run the pipeline at the configured time: it calls `fetcher → scorer → summariser` in sequence via internal HTTP `/run` endpoints. Each pipeline service exposes a `/run` endpoint and does nothing else (no cron inside containers). `api` and `llm-proxy` are always-on.

### Phase 2 addition

A sixth service `mcp` (Python) will expose an MCP server that reads from the same DB, allowing AI assistants (GitHub Copilot, Claude) to query email summaries and scores directly.

---

## Data Model

SQLite database (`email_summariser.db`) on a Docker named volume, mounted into all services.

### `emails`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | SHA256 of Message-ID header |
| `thread_id` | TEXT | Gmail thread grouping |
| `subject` | TEXT | |
| `sender_email` | TEXT | |
| `sender_name` | TEXT | |
| `received_at` | DATETIME | |
| `body_text` | TEXT | Stripped plain text |
| `labels` | JSON | Gmail labels array |
| `is_read` | BOOL | |
| `fetched_at` | DATETIME | |

FTS5 virtual table on `(subject, body_text, sender_email)` for full-text search.

### `email_scores`

| Column | Type | Notes |
|---|---|---|
| `email_id` | TEXT PK/FK | → emails.id (one score row per email) |
| `vip_match` | BOOL | Matched a VIP sender rule |
| `keyword_score` | INT | 0–100, sum of matched keyword weights |
| `llm_score` | INT | 0–100, LLM urgency rating |
| `total_score` | INT | `vip×50 + keyword×0.3 + llm×0.7` |
| `llm_reasoning` | TEXT | LLM explanation string |
| `scored_at` | DATETIME | |

### `summaries`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `date` | DATE | Unique per day |
| `summary_text` | TEXT | LLM-generated Markdown digest |
| `email_count` | INT | Total emails in window |
| `top_email_ids` | JSON | List of featured email IDs |
| `sent_at` | DATETIME | NULL if not yet sent |
| `sent_to` | TEXT | Recipient address |

### `vip_senders`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `pattern` | TEXT | Full email or `@domain.com` wildcard |
| `label` | TEXT | Human label, e.g. "boss" |
| `created_at` | DATETIME | |

### `keywords`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `keyword` | TEXT | Case-insensitive |
| `weight` | INT | 1–10 (contributes to keyword_score) |
| `match_body` | BOOL | If false, subject-only |
| `created_at` | DATETIME | |

### `fetch_runs`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `started_at` | DATETIME | |
| `completed_at` | DATETIME | |
| `emails_fetched` | INT | |
| `scope` | TEXT | `24h` / `unread` / `since_last_run` |
| `status` | TEXT | `success` / `error` |
| `error_message` | TEXT | NULL on success |

### `config`

Key-value store for runtime settings. Populated from `.env` on first run; overridable via API.

---

## Scoring Pipeline

Three layers applied in sequence for each unscored email:

1. **VIP check** — `sender_email` matched against `vip_senders.pattern`. Match sets `vip_match=true`, contributing +50 to `total_score`.
2. **Keyword scan** — subject and (optionally) body checked against all `keywords`. `keyword_score = min(100, sum_of_matched_weights × 10)`.
3. **LLM score** — subject + first 500 chars of body sent to `llm-proxy`. Prompt asks for urgency rating 0–100 and a one-sentence reason. Response stored as `llm_score` + `llm_reasoning`.

**Formula:** `total_score = (vip_match ? 50 : 0) + keyword_score × 0.3 + llm_score × 0.7`

Maximum possible: 50 + 30 + 70 = 150 (scores above 100 treated as 100 in UI).

---

## LLM Proxy (LiteLLM)

All LLM calls go through the `llm-proxy` service (LiteLLM), providing a single OpenAI-compatible endpoint. Swapping models requires only a `.env` change — no code changes.

```
# Phase 1 — local Ollama
LLM_MODEL=ollama/llama3.2
LLM_BASE_URL=http://llm-proxy:4000
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Phase 2 — any provider
LLM_MODEL=gpt-4o-mini          # OpenAI
LLM_MODEL=claude-haiku-4-5     # Anthropic
```

The `scorer` uses a lightweight model for per-email scoring (speed matters for 20–100 emails). The `summariser` uses a capable model for the final digest (quality matters more than speed).  Both models are configurable independently via `SCORER_LLM_MODEL` and `SUMMARISER_LLM_MODEL`.

---

## Fetch Scope

Configurable via `FETCH_SCOPE` env var:

| Value | Behaviour |
|---|---|
| `24h` | All emails received in last 24 hours |
| `unread` | All currently unread emails |
| `since_last_run` | Emails received after latest `fetch_runs.completed_at` |

Default: `24h`. The API exposes a `/run` endpoint to trigger a manual fetch with an optional scope override.

---

## Summary Email Format

The `summariser` constructs a structured Markdown prompt with the top-N scored emails (default `SUMMARY_TOP_N=20`) and asks the LLM to produce a digest in this structure:

```
## 🔴 Action Required (N)
- **[Subject]** from Sender — one-line summary

## 🟠 Worth Reading (N)
...

## ⚪ Low Priority (N)
...

---
Full list: http://localhost:8080
```

Sent via SMTP (Gmail App Password) to `SUMMARY_SEND_TO`.

---

## Web Dashboard (FastAPI + Jinja2 / HTMX)

Always-on at `http://localhost:8080`. Server-side rendered with HTMX for interactivity — no separate frontend build step.

**Pages / endpoints:**

| Route | Description |
|---|---|
| `GET /` | Today's dashboard: AI banner, email list, right panel |
| `GET /emails` | Paginated email list with score filters |
| `GET /emails/{id}` | Email detail with LLM reasoning |
| `GET /summaries` | History of past daily digests |
| `GET /config` | VIP senders + keywords management |
| `POST /config/vip` | Add/remove VIP sender |
| `POST /config/keywords` | Add/remove keyword |
| `POST /run` | Trigger manual pipeline run |
| `GET /search?q=` | FTS5 full-text search |

---

## Project Structure

```
email-summariser/
├── docker-compose.yml
├── .env.example
├── db/
│   └── schema.sql              # SQLite schema + FTS5 setup
├── services/
│   ├── shared/                 # Shared Python library (DB access, models)
│   │   ├── database.py
│   │   ├── models.py
│   │   └── config.py
│   ├── fetcher/
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   └── imap_client.py
│   ├── scorer/
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── vip.py
│   │   ├── keywords.py
│   │   └── llm_scorer.py
│   ├── summariser/
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── prompt.py
│   │   └── mailer.py
│   └── api/
│       ├── Dockerfile
│       ├── main.py
│       ├── routers/
│       └── templates/
├── litellm/
│   └── config.yaml
└── docs/
    └── superpowers/specs/
        └── 2026-04-29-email-summariser-design.md
```

---

## Configuration (.env)

```env
# Gmail IMAP
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# Summary delivery
SUMMARY_SEND_TO=you@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587

# Fetch
FETCH_SCOPE=24h               # 24h | unread | since_last_run
SCHEDULE_CRON=0 6 * * *      # 6 AM daily

# LLM
SCORER_LLM_MODEL=ollama/llama3.2
SUMMARISER_LLM_MODEL=ollama/llama3.2
LLM_BASE_URL=http://llm-proxy:4000
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Pipeline
SUMMARY_TOP_N=20
```

---

## Phase 2: MCP Server

A sixth Docker service exposing an MCP-compatible server. Tools:

- `get_today_summary` — returns today's digest text
- `list_important_emails` — returns top-N emails with scores
- `search_emails(query)` — FTS5 search
- `get_email(id)` — full email + score + reasoning

Reads from the same SQLite volume. No changes to existing services.

---

## Testing Strategy

- **Unit tests** per service: scorer logic (VIP/keyword/LLM mocking), fetcher dedup logic, summariser prompt construction
- **Integration tests**: pipeline end-to-end with a local IMAP mock (GreenMail or `imaptest`)
- **API tests**: FastAPI `TestClient` for all routes
- All tests run in CI via `pytest` inside Docker

---

## Open Questions / Future Considerations

- Gmail OAuth2 vs App Password: App Password is simpler for Phase 1; OAuth2 can be added without schema changes
- Email threading: currently stored flat; thread grouping can be added to the dashboard later
- Attachment handling: out of scope for Phase 1; body_text stores text content only
- PostgreSQL + pgvector migration: the `shared/database.py` abstraction layer is designed so migration is a config swap, not a rewrite
