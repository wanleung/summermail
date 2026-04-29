"""Keyword scoring module."""
import sqlite3


def score_keywords(subject: str, body: str, conn: sqlite3.Connection) -> int:
    """Return keyword score 0–100 based on matched keyword weights.
    
    Args:
        subject: Email subject line
        body: Email body text
        conn: SQLite connection to keywords table
        
    Returns:
        Integer score between 0 and 100. Keywords matching in subject are always
        counted. Keywords with match_body=True are also counted if found in body.
        Total weight is multiplied by 10 and capped at 100.
    """
    rows = conn.execute(
        "SELECT keyword, weight, match_body FROM keywords"
    ).fetchall()

    subject_lower = subject.lower()
    body_lower = body.lower()
    total_weight = 0

    for row in rows:
        kw = row["keyword"].lower()
        match_body = bool(row["match_body"])
        weight = row["weight"]
        if weight is None:
            continue
        if kw in subject_lower:
            total_weight += weight
        elif match_body and kw in body_lower:  # subject takes priority; no double-counting
            total_weight += weight

    # weights are 1–10; multiply by 10 to scale to 0–100
    return min(100, max(0, total_weight * 10))
