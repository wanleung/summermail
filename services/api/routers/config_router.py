"""Configuration management endpoints."""
import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.database import get_db_ctx

router = APIRouter(prefix="/config", tags=["config"])


class VipIn(BaseModel):
    """VIP sender input model."""

    pattern: str
    label: str = ""


class KeywordIn(BaseModel):
    """Keyword input model."""

    keyword: str
    weight: int = 5
    match_body: bool = True


@router.get("/vip")
def list_vip():
    """List all VIP senders."""
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT * FROM vip_senders ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/vip")
def add_vip(body: VipIn):
    """Add a new VIP sender pattern."""
    with get_db_ctx() as conn:
        try:
            row_id = conn.execute(
                "INSERT INTO vip_senders (pattern, label) VALUES (?,?)",
                (body.pattern, body.label),
            ).lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Pattern already exists")
        row = conn.execute("SELECT * FROM vip_senders WHERE id=?", (row_id,)).fetchone()
        return dict(row)


@router.delete("/vip/{vip_id}")
def delete_vip(vip_id: int):
    """Delete a VIP sender pattern."""
    with get_db_ctx() as conn:
        cursor = conn.execute("DELETE FROM vip_senders WHERE id=?", (vip_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="VIP not found")
    return {"deleted": vip_id}


@router.get("/keywords")
def list_keywords():
    """List all keywords."""
    with get_db_ctx() as conn:
        rows = conn.execute("SELECT * FROM keywords ORDER BY id").fetchall()
        return [dict(r) for r in rows]


@router.post("/keywords")
def add_keyword(body: KeywordIn):
    """Add a new keyword."""
    with get_db_ctx() as conn:
        try:
            row_id = conn.execute(
                "INSERT INTO keywords (keyword, weight, match_body) VALUES (?,?,?)",
                (body.keyword, body.weight, body.match_body),
            ).lastrowid
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Keyword already exists")
        row = conn.execute("SELECT * FROM keywords WHERE id=?", (row_id,)).fetchone()
        return dict(row)


@router.delete("/keywords/{kw_id}")
def delete_keyword(kw_id: int):
    """Delete a keyword."""
    with get_db_ctx() as conn:
        cursor = conn.execute("DELETE FROM keywords WHERE id=?", (kw_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Keyword not found")
    return {"deleted": kw_id}
