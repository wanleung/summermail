"""LLM-based email importance scoring using OpenAI API."""
import json
import re
from typing import Optional

from openai import OpenAI


# Module-level client placeholder; actual initialization deferred
_client: Optional[OpenAI] = None

SCORING_PROMPT = """You are an email importance classifier. Given an email subject and body snippet, rate its urgency from 0 to 100 and give a one-sentence reason.

Respond ONLY with valid JSON in this exact format:
{"score": <integer 0-100>, "reason": "<one sentence>"}

0 = spam/newsletter, 50 = FYI, 100 = immediate action required."""


def _get_client() -> OpenAI:
    """Lazily initialize and return the OpenAI client.
    
    This deferred initialization prevents import-time failures when
    environment variables are absent or config is not yet initialized.
    """
    global _client
    if _client is None:
        from shared.config import settings
        _client = OpenAI(base_url=settings.llm_base_url, api_key="ignored")
    return _client


class _ClientProxy:
    """Proxy object that delegates to the lazily-initialized client.
    
    Allows tests to patch `scorer.llm_scorer.client` even though the
    actual client is created lazily inside _get_client().
    """

    def __getattr__(self, name):
        """Delegate attribute access to the actual client."""
        return getattr(_get_client(), name)


# Expose module-level 'client' for test patching
client = _ClientProxy()


def _parse_llm_response(text: str) -> tuple[int, str]:
    """Parse LLM response and extract score (0-100) and reason.
    
    Attempts to parse JSON first. If that fails, falls back to regex
    extraction of a number from the text.
    
    Args:
        text: Raw response text from the LLM
        
    Returns:
        Tuple of (score, reason) where score is 0-100 and reason is a string
    """
    try:
        data = json.loads(text.strip())
        score = max(0, min(100, int(data.get("score", 0))))
        reason = str(data.get("reason", ""))
        return score, reason
    except (json.JSONDecodeError, ValueError):
        # Fallback: try to extract a number from the text
        match = re.search(r"\b(\d{1,3})\b", text)
        score = max(0, min(100, int(match.group(1)))) if match else 0
        return score, text[:200]


def score_llm(subject: str, body: str, model: str = None) -> tuple[int, str]:
    """Score email importance using an LLM.
    
    Args:
        subject: Email subject line
        body: Email body text
        model: LLM model to use; defaults to settings.scorer_llm_model
        
    Returns:
        Tuple of (score, reasoning) where score is 0-100
    """
    from shared.config import settings

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
