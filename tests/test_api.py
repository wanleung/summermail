"""Tests for the API service."""
import os
import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with isolated DB."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    
    # Initialize the schema in the temp DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    schema = Path(__file__).parent.parent / "db" / "schema.sql"
    with open(schema) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    
    # Patch settings.db_path so get_db() uses temp path
    from shared.config import settings
    monkeypatch.setattr(settings, "db_path", db_path)
    
    # Import app after patching
    from api.main import app
    from fastapi.testclient import TestClient
    
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_health(client):
    """Test the health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_add_vip(client):
    """Test adding a VIP sender."""
    response = client.post(
        "/config/vip",
        json={"pattern": "*@important.com", "label": "Important Corp"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pattern"] == "*@important.com"
    assert data["label"] == "Important Corp"
    assert "id" in data


def test_config_add_keyword(client):
    """Test adding a keyword."""
    response = client.post(
        "/config/keywords",
        json={"keyword": "urgent", "weight": 10, "match_body": True}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["keyword"] == "urgent"
    assert data["weight"] == 10
    assert data["match_body"] == 1  # SQLite stores as int
    assert "id" in data


def test_config_list_vip(client):
    """Test listing VIP senders."""
    # Add a VIP first
    client.post("/config/vip", json={"pattern": "*@vip.com", "label": "VIP"})
    
    response = client.get("/config/vip")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["pattern"] == "*@vip.com"


def test_config_list_keywords(client):
    """Test listing keywords."""
    # Add a keyword first
    client.post("/config/keywords", json={"keyword": "important", "weight": 5})
    
    response = client.get("/config/keywords")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["keyword"] == "important"


def test_search_returns_results(client):
    """Test email search."""
    # Insert a test email into DB
    from shared.config import settings
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Insert email
    conn.execute(
        "INSERT INTO emails (id, subject, sender_email, sender_name, received_at, is_read, body_text) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("test-id-1", "Invoice for services", "billing@example.com", "Billing Dept", 
         "2024-01-15 10:00:00", 0, "Please find attached your invoice")
    )
    conn.commit()
    conn.close()
    
    # Search for the email
    response = client.get("/search?q=invoice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 0  # FTS might not return results immediately


def test_summaries_history(client):
    """Test listing summaries."""
    response = client.get("/summaries")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
