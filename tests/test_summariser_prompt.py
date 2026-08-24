"""Tests for the summariser prompt building."""
from summariser.prompt import build_prompt, build_system_prompt


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
    prompt = build_system_prompt()
    assert "Action Required" in prompt
    assert "Worth Reading" in prompt


def test_build_prompt_empty_list():
    prompt = build_prompt([])
    assert "today's emails" in prompt


def test_build_prompt_none_body():
    rows = [{
        "subject": "X", "sender_email": "x@y.com",
        "sender_name": "X", "received_at": "2026-04-29T08:00:00",
        "total_score": 50, "body_text": None,
    }]
    prompt = build_prompt(rows)
    assert "Body:" in prompt


def test_system_prompt_uses_configured_dashboard_url(monkeypatch):
    """The digest footer link must follow the configured dashboard URL, not a hardcoded port."""
    from shared.config import settings
    from summariser.prompt import build_system_prompt

    monkeypatch.setattr(settings, "dashboard_url", "http://localhost:18001")
    assert "http://localhost:18001" in build_system_prompt()
