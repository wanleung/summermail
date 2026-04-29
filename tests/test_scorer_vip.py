# tests/test_scorer_vip.py
import pytest
from scorer.vip import check_vip


def test_exact_email_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("boss@company.com", "Boss"))
    tmp_db.commit()
    assert check_vip("boss@company.com", tmp_db) is True


def test_exact_email_no_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("boss@company.com", "Boss"))
    tmp_db.commit()
    assert check_vip("other@company.com", tmp_db) is False


def test_domain_wildcard_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("@company.com", "Company"))
    tmp_db.commit()
    assert check_vip("anyone@company.com", tmp_db) is True


def test_domain_wildcard_no_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("@company.com", "Company"))
    tmp_db.commit()
    assert check_vip("someone@other.com", tmp_db) is False


def test_empty_vip_list(tmp_db):
    assert check_vip("anyone@example.com", tmp_db) is False


def test_case_insensitive_match(tmp_db):
    tmp_db.execute("INSERT INTO vip_senders (pattern, label) VALUES (?, ?)",
                   ("boss@company.com", "Boss"))
    tmp_db.commit()
    assert check_vip("BOSS@COMPANY.COM", tmp_db) is True
    assert check_vip("Boss@Company.Com", tmp_db) is True
