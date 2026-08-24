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
        _client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.litellm_master_key.get_secret_value(),
        )
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


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```[a-zA-Z]*\n?|```")
_JSON_OBJ_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _load_score(candidate: str) -> tuple[int, str] | None:
    """Parse one JSON candidate into (score, reason), or None if it isn't valid."""
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        score = max(0, min(100, int(data.get("score", 0))))
    except (TypeError, ValueError):
        return None
    return score, str(data.get("reason", ""))


def _parse_llm_response(text: str) -> tuple[int, str]:
    """Parse LLM response and extract score (0-100) and reason.

    Reasoning models wrap output in <think> blocks and many models wrap JSON in
    markdown fences or surrounding prose; all three are stripped before parsing.
    Only if no JSON object can be found does this fall back to pulling a bare
    number out of the text.

    Args:
        text: Raw response text from the LLM

    Returns:
        Tuple of (score, reason) where score is 0-100 and reason is a string
    """
    cleaned = _FENCE_RE.sub("", _THINK_RE.sub("", text or "")).strip()

    parsed = _load_score(cleaned)
    if parsed is not None:
        return parsed

    # JSON embedded in prose: take the first object that parses
    for match in _JSON_OBJ_RE.finditer(cleaned):
        parsed = _load_score(match.group(0))
        if parsed is not None:
            return parsed

    # Last resort: extract a bare number from the text
    match = re.search(r"\b(\d{1,3})\b", cleaned)
    score = max(0, min(100, int(match.group(1)))) if match else 0
    return score, cleaned[:200]


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
        timeout=settings.scorer_llm_timeout,
    )

    return _parse_llm_response(response.choices[0].message.content)
