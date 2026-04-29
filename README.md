# MailBrief — Gmail Email Summariser

A self-hosted daily email digest for Gmail. Fetches your inbox via IMAP, scores each email by importance, generates an AI summary, and delivers it to your inbox every morning. Includes a live web dashboard.

## Features

- **3-layer importance scoring** — VIP sender matching, keyword weights, LLM reasoning
- **AI digest** — LLM-generated daily summary of your top emails
- **Web dashboard** — Browse, filter, and search emails with live score badges
- **Swap LLMs freely** — Starts with local Ollama; switch to OpenAI/Anthropic via `.env`
- **Fully self-hosted** — One `docker compose up -d` to run everything

## Architecture

```
Gmail IMAP
    │
    ▼
┌──────────┐   ┌──────────┐   ┌─────────────┐
│  fetcher  │──▶│  scorer  │──▶│ summariser  │
│  :8001   │   │  :8002   │   │    :8003    │
└──────────┘   └──────────┘   └─────────────┘
                                      │
                                      ▼ SMTP
┌──────────┐   ┌──────────────────────────┐
│llm-proxy │   │          api              │
│  :4000   │   │         :8080             │
│(LiteLLM) │   │  dashboard + scheduler    │
└──────────┘   └──────────────────────────┘
                        │
                        ▼
                SQLite (shared volume)
```

| Service | Port | Role |
|---------|------|------|
| `fetcher` | 8001 | IMAP fetch, deduplication, FTS5 indexing |
| `scorer` | 8002 | VIP + keyword + LLM scoring |
| `summariser` | 8003 | LLM digest generation + SMTP delivery |
| `api` | 8080 | Web dashboard, REST API, cron scheduler |
| `llm-proxy` | 4000 | LiteLLM proxy (Ollama / OpenAI / Anthropic) |

## Scoring Formula

```
total_score = (vip ? 50 : 0) + keyword_score×0.3 + llm_score×0.7
```

- **VIP match** (+50) — exact email or wildcard domain (e.g. `*@github.com`)
- **Keyword score** (0–100, weighted ×0.3) — configurable keywords with 1–10 weights
- **LLM score** (0–100, weighted ×0.7) — LLM judges urgency from subject + body snippet

## Quick Start

### Prerequisites

- Docker + Docker Compose
- [Ollama](https://ollama.com) running locally with `llama3.2` pulled
- Gmail [App Password](https://support.google.com/accounts/answer/185833) (not your main password)

### 1. Configure

```bash
cp .env.example .env
```

Edit `.env` — at minimum set:

```env
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
SUMMARY_SEND_TO=you@gmail.com
```

### 2. Start

```bash
docker compose up -d
```

### 3. Open the dashboard

```
http://localhost:8080
```

### 4. Trigger a manual run

```bash
curl -X POST http://localhost:8080/run
```

Or click **▶ Run Now** in the dashboard.

The scheduler runs automatically at **6 AM daily** by default (configurable via `SCHEDULE_CRON`).

## Configuration

All configuration is via `.env`. Copy `.env.example` as a starting point.

| Variable | Default | Description |
|----------|---------|-------------|
| `GMAIL_USER` | — | Gmail address |
| `GMAIL_APP_PASSWORD` | — | Gmail App Password |
| `SUMMARY_SEND_TO` | — | Address to receive daily digest |
| `FETCH_SCOPE` | `24h` | `24h`, `unread`, or `since_last_run` |
| `SCHEDULE_CRON` | `0 6 * * *` | Cron expression for daily run |
| `SUMMARY_TOP_N` | `20` | Max emails included in digest |
| `SCORER_LLM_MODEL` | `ollama/llama3.2` | LLM model for scoring |
| `SUMMARISER_LLM_MODEL` | `ollama/llama3.2` | LLM model for digest |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama base URL |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |

## Swapping LLM Providers

No code changes needed — just update `.env` and restart the affected services:

```bash
# Use OpenAI
SCORER_LLM_MODEL=gpt-4o-mini
SUMMARISER_LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

docker compose restart scorer summariser
```

Supported providers: Ollama, OpenAI, Anthropic, Groq, and [anything LiteLLM supports](https://docs.litellm.ai/docs/providers).

## Dashboard

The web dashboard at `http://localhost:8080` lets you:

- **Today** — Browse scored emails with urgency badges (🔴 ≥70, 🟠 ≥40, ⚫ <40)
- **Filter** — Show only urgent (≥70) or VIP emails
- **Search** — Full-text search across all email subjects and bodies
- **Email detail** — View score breakdown (VIP / keyword / LLM reasoning)
- **Settings** — Add/remove VIP senders and scoring keywords
- **▶ Run Now** — Trigger an immediate fetch-score-summarise cycle

## REST API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/run` | Trigger full pipeline |
| `GET` | `/emails` | List emails (with filters) |
| `GET` | `/emails/{id}` | Email detail (JSON) |
| `GET` | `/search?q=...` | Full-text search |
| `GET` | `/summaries` | Summary history |
| `GET/POST` | `/config/vip` | List / add VIP senders |
| `DELETE` | `/config/vip/{id}` | Remove VIP sender |
| `GET/POST` | `/config/keywords` | List / add keywords |
| `DELETE` | `/config/keywords/{id}` | Remove keyword |

## Project Structure

```
email-summariser/
├── docker-compose.yml
├── .env.example
├── litellm/
│   └── config.yaml            # LiteLLM model routing
├── db/
│   └── schema.sql             # SQLite schema (FTS5, triggers)
├── services/
│   ├── shared/
│   │   ├── config.py          # Pydantic settings (loaded from .env)
│   │   └── database.py        # SQLite helper + init_db
│   ├── fetcher/               # IMAP fetch service
│   ├── scorer/                # 3-layer scoring service
│   ├── summariser/            # Digest + mailer service
│   └── api/                   # Dashboard + REST API + scheduler
│       └── templates/         # Jinja2 + htmx HTML templates
└── tests/                     # 53 unit tests (all mocked)
```

## Development

```bash
# Install test dependencies
pip install -r services/api/requirements.txt  # or any service

# Run tests
python3 -m pytest tests/ -v

# Run a single service locally (requires .env to be sourced)
export $(cat .env | xargs)
uvicorn api.main:app --reload --port 8080
```

Tests use mocked IMAP and LLM clients — no live credentials needed.

## License

GNU General Public License v3.0 or later — see [LICENSE](LICENSE) for details.
