"""Tests for the scoring formula orchestration."""
from scorer.main import compute_total_score


def test_vip_adds_50():
    """Test that VIP flag adds 50 to the score."""
    assert compute_total_score(vip=True, keyword=0, llm=0) == 50


def test_formula_combines_all_layers():
    """Test that all three layers are combined with correct weights.
    
    vip=True: +50, keyword=60: +18, llm=80: +56 → 124 → capped at 100
    """
    assert compute_total_score(vip=True, keyword=60, llm=80) == 100


def test_no_signals_returns_zero():
    """Test that no signals result in zero score."""
    assert compute_total_score(vip=False, keyword=0, llm=0) == 0


def test_keyword_and_llm_without_vip():
    """Test that keyword and LLM scores are weighted correctly without VIP.
    
    keyword=40: +12, llm=50: +35 → 47
    """
    assert compute_total_score(vip=False, keyword=40, llm=50) == 47


def test_score_never_exceeds_100():
    """Test that combined score never exceeds 100."""
    assert compute_total_score(vip=True, keyword=100, llm=100) == 100


def test_negative_inputs_floored_to_zero():
    """Test that negative inputs are clamped to zero."""
    assert compute_total_score(vip=False, keyword=-50, llm=-50) == 0


def test_over_range_inputs_capped():
    """Test that inputs over 100 are capped at 100."""
    assert compute_total_score(vip=False, keyword=200, llm=300) == 100
