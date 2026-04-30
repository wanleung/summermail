# SummerMail — Gmail Email Summariser

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

## Scoring System

Every fetched email is scored 0–100 for importance using three independent layers. The layers are combined into a single `total_score` that drives digest ordering and urgency badges.

### Formula

```
total_score = min(100, (50 if VIP) + keyword_score × 0.3 + llm_score × 0.7)
```

### Layer 1 — VIP Sender Match (+50 flat bonus)

If the sender's email address matches any entry in your VIP list, the email receives a flat **+50 point bonus** before the other layers are calculated. This guarantees VIP emails always appear near the top of the digest.

VIP patterns support two formats:

| Pattern | Matches |
|---------|---------|
| `boss@company.com` | Exact address only |
| `@company.com` | Any sender at that domain |

Manage your VIP list via the dashboard (**Settings → VIP Senders**) or the REST API (`POST /config/vip`).

### Layer 2 — Keyword Scoring (0–100, weighted ×0.3)

Each keyword in your list has a **weight from 1–10**. When a keyword appears in the subject or body, its weight is added to a running total:

```
keyword_score = min(100, total_matched_weight × 10)
```

- Subject matches are checked first; body matches only count if `match_body` is enabled for that keyword and the subject didn't already match (no double-counting).
- The raw weight total is multiplied by 10 so a single weight-10 keyword already reaches 100.
- This layer contributes up to **30 points** to the final score (`100 × 0.3 = 30`).

Manage keywords via the dashboard (**Settings → Keywords**) or the REST API (`POST /config/keywords`).

**Example keywords to get started:**

| Keyword | Weight | match_body |
|---------|--------|------------|
| `urgent` | 8 | ✓ |
| `invoice` | 7 | ✓ |
| `action required` | 9 | ✓ |
| `newsletter` | 1 | ✗ |

### Layer 3 — LLM Importance Score (0–100, weighted ×0.7)

The LLM receives the email subject and first 500 characters of the body, then returns a JSON score and one-sentence reason:

```json
{"score": 85, "reason": "Requires approval before end of day."}
```

The prompt instructs the LLM to use this scale:

| Score | Meaning |
|-------|---------|
| 0–20 | Spam / newsletter / no action needed |
| 21–49 | FYI / informational |
| 50–69 | May need follow-up |
| 70–100 | Immediate action or response required |

The LLM score contributes up to **70 points** to the final score (`100 × 0.7 = 70`), making it the dominant signal. If the LLM call fails, this layer falls back to 0 and a fallback reason is stored.

The LLM reasoning is stored per-email and visible in the **Email Detail** view on the dashboard.

### Score Bands

The final `total_score` maps to urgency bands used in the digest and dashboard:

| Score | Band | Digest section |
|-------|------|----------------|
| 70–100 | 🔴 Urgent | Action Required |
| 30–69 | 🟠 Normal | Worth Reading |
| 0–29 | ⚪ Low | Low Priority |

### Worked Examples

| Scenario | VIP | Keyword | LLM | Total |
|----------|-----|---------|-----|-------|
| Boss emails "urgent approval needed" | +50 | 80 | 90 | min(100, 50+24+63) = **100** |
| GitHub PR notification | 0 | 30 | 45 | min(100, 0+9+31.5) = **40** |
| Marketing newsletter | 0 | 10 | 5 | min(100, 0+3+3.5) = **6** |
| Unknown sender, high-urgency body | 0 | 0 | 88 | min(100, 0+0+61.6) = **61** |

## Ollama Setup

SummerMail uses [Ollama](https://ollama.com) as the default LLM backend for scoring and summarisation. Ollama can run on the same machine as Docker or on a separate host on your network.

### Install Ollama

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com/download
```

### Pull the model

```bash
ollama pull llama3.2
```

### Allow network access (if Ollama is on a separate host)

By default Ollama only listens on `localhost`. To expose it to other machines on your network, set the environment variable before starting Ollama:

```bash
# Linux (systemd) — add to /etc/systemd/system/ollama.service under [Service]
Environment="OLLAMA_HOST=0.0.0.0"

# Then reload and restart
sudo systemctl daemon-reload
sudo systemctl restart ollama

# macOS / manual start
OLLAMA_HOST=0.0.0.0 ollama serve
```

### Point SummerMail at your Ollama host

In your `.env`, set `OLLAMA_BASE_URL` to your Ollama machine's IP:

```env
# Ollama on a separate host (e.g. 10.100.1.30)
OLLAMA_BASE_URL=http://10.100.1.30:11434

# Ollama on the same machine as Docker (default)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### Verify connectivity

```bash
curl http://<ollama-host>:11434/api/tags
```

You should see a JSON list of your installed models. If `llama3.2` appears, you're ready to go.

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Ollama running with `llama3.2` pulled (see [Ollama Setup](#ollama-setup) above)
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
| `SCHEDULE_TIMEZONE` | `UTC` | IANA timezone for cron (e.g. `Asia/Hong_Kong`) |
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
