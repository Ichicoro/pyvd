from __future__ import annotations
import secrets
import sqlite3

_db_path: str = "pyvd.db"


def init(path: str) -> None:
    global _db_path
    _db_path = path
    with sqlite3.connect(_db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                user_id INTEGER PRIMARY KEY,
                api_key  TEXT NOT NULL
            )
        """)
        conn.commit()


def get_or_create_api_key(user_id: int) -> tuple[str, bool]:
    """Return (key, created). created=True when a new key was generated."""
    with sqlite3.connect(_db_path) as conn:
        row = conn.execute(
            "SELECT api_key FROM api_keys WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return row[0], False
        key = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO api_keys (user_id, api_key) VALUES (?, ?)", (user_id, key)
        )
        conn.commit()
        return key, True


def get_user_id_by_api_key(api_key: str) -> int | None:
    with sqlite3.connect(_db_path) as conn:
        row = conn.execute(
            "SELECT user_id FROM api_keys WHERE api_key = ?", (api_key,)
        ).fetchone()
        return row[0] if row else None


def reset_api_key(user_id: int) -> str:
    key = secrets.token_urlsafe(32)
    with sqlite3.connect(_db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO api_keys (user_id, api_key) VALUES (?, ?)",
            (user_id, key),
        )
        conn.commit()
    return key
