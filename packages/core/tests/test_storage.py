"""Tests for token storage."""

import os
import tempfile

import pytest

from gsuite_core.storage import SQLiteTokenStore


class TestSQLiteTokenStore:
    """Tests for SQLite token storage."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def store(self, temp_db):
        """Create a token store with temp database."""
        return SQLiteTokenStore(db_path=temp_db)

    def test_save_and_get_token(self, store):
        """Test saving and retrieving a token."""
        token_data = {
            "token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "scopes": ["scope1", "scope2"],
        }

        store.save_token(token_data)
        retrieved = store.get_token()

        assert retrieved is not None
        assert retrieved["token"] == "access_token_123"
        assert retrieved["refresh_token"] == "refresh_token_456"
        assert retrieved["scopes"] == ["scope1", "scope2"]

    def test_get_nonexistent_token(self, store):
        """Test getting a token that doesn't exist."""
        result = store.get_token("nonexistent_user")
        assert result is None

    def test_exists(self, store):
        """Test exists method."""
        assert store.exists() is False

        store.save_token({"token": "test"})
        assert store.exists() is True

    def test_delete_token(self, store):
        """Test deleting a token."""
        store.save_token({"token": "test"})
        assert store.exists() is True

        result = store.delete_token()
        assert result is True
        assert store.exists() is False

    def test_delete_nonexistent_token(self, store):
        """Test deleting a token that doesn't exist."""
        result = store.delete_token("nonexistent")
        assert result is False

    def test_multiple_users(self, store):
        """Test storing tokens for multiple users."""
        store.save_token({"token": "token_1"}, user_id="user1")
        store.save_token({"token": "token_2"}, user_id="user2")

        assert store.get_token("user1")["token"] == "token_1"
        assert store.get_token("user2")["token"] == "token_2"

    def test_update_token(self, store):
        """Test updating an existing token."""
        store.save_token({"token": "old_token"})
        store.save_token({"token": "new_token"})

        retrieved = store.get_token()
        assert retrieved["token"] == "new_token"
