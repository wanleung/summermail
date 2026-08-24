"""Tests for LLM-based email scoring."""
from unittest.mock import patch, MagicMock

from scorer.llm_scorer import score_llm, _parse_llm_response


def test_parse_llm_response_extracts_score():
    """Test that _parse_llm_response extracts score and reason from valid JSON."""
    text = '{"score": 75, "reason": "Contains urgent deadline"}'
    score, reason = _parse_llm_response(text)
    assert score == 75
    assert "urgent" in reason


def test_parse_llm_response_clamps_score():
    """Test that scores above 100 are clamped to 100."""
    text = '{"score": 150, "reason": "Very urgent"}'
    score, _ = _parse_llm_response(text)
    assert score == 100


def test_parse_llm_response_handles_malformed():
    """Test that malformed JSON falls back to regex extraction."""
    text = "I think this is about 60 out of 100"
    score, reason = _parse_llm_response(text)
    assert 0 <= score <= 100


def test_score_llm_calls_openai_client():
    """Test that score_llm calls the OpenAI client and returns parsed response."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '{"score": 80, "reason": "Action required"}'
    with patch("scorer.llm_scorer.client.chat.completions.create",
               return_value=mock_response):
        score, reason = score_llm("Urgent invoice due", "Please pay by Friday")
    assert score == 80
    assert reason == "Action required"


def test_score_llm_propagates_connection_error():
    """Test that connection errors are propagated."""
    with patch("scorer.llm_scorer.client.chat.completions.create",
               side_effect=Exception("Connection refused")):
        try:
            score_llm("Subject", "Body")
            assert False, "Expected exception to be raised"
        except Exception as e:
            assert "Connection refused" in str(e)


def test_parse_llm_response_handles_fenced_json():
    """Markdown code fences around the JSON must not defeat parsing."""
    text = '```json\n{"score": 85, "reason": "Payment overdue"}\n```'
    score, reason = _parse_llm_response(text)
    assert score == 85
    assert reason == "Payment overdue"


def test_parse_llm_response_strips_thinking_block():
    """A reasoning model's <think> block must not leak into the score."""
    text = '<think>Maybe 12 out of 100? No.</think>{"score": 90, "reason": "Outage"}'
    score, reason = _parse_llm_response(text)
    assert score == 90
    assert reason == "Outage"


def test_parse_llm_response_extracts_json_after_prose():
    """A number in leading prose must not be mistaken for the score."""
    text = 'Here is my rating out of 100:\n{"score": 30, "reason": "Newsletter"}'
    score, reason = _parse_llm_response(text)
    assert score == 30
    assert reason == "Newsletter"
