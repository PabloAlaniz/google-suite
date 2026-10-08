"""SQLite token storage implementation."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from gsuite_core.storage.base import TokenStore


class SQLiteTokenStore(TokenStore):
    """
    SQLite-based token storage for local development.

    Stores OAuth tokens in a local SQLite database file.
    """

    def __init__(self, db_path: str = "tokens.db"):
        """
        Initialize SQLite token store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """A connection that commits on success and is always closed.

        ``with sqlite3.connect(...)`` only commits or rolls back; it leaves the
        connection open until garbage collection, which on Windows keeps the
        database file locked (it can't be deleted or replaced meanwhile).
        """
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tokens table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    user_id TEXT PRIMARY KEY,
                    token_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def get_token(self, user_id: str = "default") -> dict[str, Any] | None:
        """Retrieve stored token data."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT token_data FROM tokens WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if row:
                return json.loads(row[0])
            return None

    def save_token(self, token_data: dict[str, Any], user_id: str = "default") -> None:
        """Store token data."""
        token_json = json.dumps(token_data)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tokens (user_id, token_data, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    token_data = excluded.token_data,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (user_id, token_json),
            )

    def delete_token(self, user_id: str = "default") -> bool:
        """Delete stored token."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM tokens WHERE user_id = ?", (user_id,))
            return cursor.rowcount > 0

    def exists(self, user_id: str = "default") -> bool:
        """Check if token exists."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT 1 FROM tokens WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None
