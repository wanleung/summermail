"""Prompt building for email digest generation."""
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
    """Build a user prompt from email rows for the LLM.
    
    Args:
        email_rows: List of email dictionaries with keys:
            - subject: Email subject
            - sender_email: Sender email address
            - sender_name: Sender display name
            - received_at: ISO datetime string
            - total_score: Importance score (0-100)
            - body_text: Email body text
            
    Returns:
        Formatted prompt string containing all email information
    """
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
