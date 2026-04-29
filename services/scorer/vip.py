"""VIP sender matching module."""
import sqlite3


def check_vip(sender_email: str, conn: sqlite3.Connection) -> bool:
    """Return True if sender_email matches any VIP pattern (exact or @domain).
    
    Args:
        sender_email: Email address to check
        conn: SQLite connection to vip_senders table
        
    Returns:
        True if the sender matches a VIP pattern, False otherwise
    """
    sender_email = sender_email.lower()
    rows = conn.execute("SELECT pattern FROM vip_senders").fetchall()
    for row in rows:
        pattern = row["pattern"].lower()
        if pattern.startswith("@"):
            if sender_email.endswith(pattern):
                return True
        else:
            if sender_email == pattern:
                return True
    return False
