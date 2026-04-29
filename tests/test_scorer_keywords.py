# tests/test_scorer_keywords.py
import pytest
from scorer.keywords import score_keywords


def _seed_keywords(conn):
    conn.executemany(
        "INSERT INTO keywords (keyword, weight, match_body) VALUES (?, ?, ?)",
        [("urgent", 8, True), ("invoice", 6, True), ("deadline", 7, False)],
    )
    conn.commit()


def test_subject_keyword_match(tmp_db):
    _seed_keywords(tmp_db)
    score = score_keywords("Urgent: please review", "", tmp_db)
    assert score > 0


def test_body_keyword_match(tmp_db):
    _seed_keywords(tmp_db)
    score = score_keywords("Meeting notes", "Please pay the invoice by Friday", tmp_db)
    assert score > 0


def test_subject_only_keyword_not_matched_in_body(tmp_db):
    _seed_keywords(tmp_db)
    # 'deadline' has match_body=False — only subject counts
    score_body_only = score_keywords("Nothing here", "The deadline is tomorrow", tmp_db)
    score_subject = score_keywords("The deadline is tomorrow", "", tmp_db)
    assert score_body_only == 0
    assert score_subject > 0


def test_no_match_returns_zero(tmp_db):
    _seed_keywords(tmp_db)
    assert score_keywords("Hello", "How are you?", tmp_db) == 0


def test_score_capped_at_100(tmp_db):
    # Add many high-weight keywords that all match
    for i in range(20):
        tmp_db.execute(
            "INSERT INTO keywords (keyword, weight, match_body) VALUES (?, 10, 1)",
            (f"keyword{i}",),
        )
    tmp_db.commit()
    subject = " ".join(f"keyword{i}" for i in range(20))
    assert score_keywords(subject, "", tmp_db) == 100
