"""Token storage in the operating system's keyring."""

import contextlib
import json
from typing import Any

import keyring
from keyring.errors import PasswordDeleteError

from gsuite_core.storage.base import TokenStore

# Windows Credential Manager caps an entry at 2560 bytes of UTF-16, which a
# token with many scopes exceeds, so a token is split across entries.
_CHUNK_CHARS = 1000
_INDEX = "__accounts__"


class KeyringTokenStore(TokenStore):
    """Tokens encrypted at rest by the OS: Keychain, Credential Manager, Secret Service.

    Needs ``gsuite-sdk[keyring]`` and a keyring backend, which a desktop
    session has and a headless server or container usually doesn't. Select it
    with ``GSUITE_TOKEN_STORAGE=keyring`` or pass it to ``GoogleAuth``.
    """

    def __init__(self, service_name: str = "gsuite-sdk"):
        """Initialize the keyring token store.

        Args:
            service_name: The keyring service the entries are filed under
        """
        self.service_name = service_name

    def _index(self) -> dict[str, int]:
        """How many entries each stored token spans, by user ID."""
        raw = keyring.get_password(self.service_name, _INDEX)
        index: dict[str, int] = json.loads(raw) if raw else {}
        return index

    def _save_index(self, index: dict[str, int]) -> None:
        keyring.set_password(self.service_name, _INDEX, json.dumps(index, sort_keys=True))

    def _drop(self, user_id: str, chunks: range) -> None:
        for i in chunks:
            # an entry already gone means the index was ahead of the keyring
            with contextlib.suppress(PasswordDeleteError):
                keyring.delete_password(self.service_name, f"{user_id}:{i}")

    def get_token(self, user_id: str = "default") -> dict[str, Any] | None:
        """Retrieve stored token data."""
        count = self._index().get(user_id)
        if not count:
            return None
        parts = [keyring.get_password(self.service_name, f"{user_id}:{i}") for i in range(count)]
        if any(part is None for part in parts):
            return None  # entries removed by hand: there is no usable token
        token: dict[str, Any] = json.loads("".join(part or "" for part in parts))
        return token

    def save_token(self, token_data: dict[str, Any], user_id: str = "default") -> None:
        """Store token data."""
        payload = json.dumps(token_data, separators=(",", ":"))
        chunks = [payload[i : i + _CHUNK_CHARS] for i in range(0, len(payload), _CHUNK_CHARS)]
        index = self._index()
        previous = index.get(user_id, 0)
        for i, chunk in enumerate(chunks):
            keyring.set_password(self.service_name, f"{user_id}:{i}", chunk)
        self._drop(user_id, range(len(chunks), previous))
        index[user_id] = len(chunks)
        self._save_index(index)

    def delete_token(self, user_id: str = "default") -> bool:
        """Delete stored token."""
        index = self._index()
        count = index.pop(user_id, None)
        if count is None:
            return False
        self._drop(user_id, range(count))
        self._save_index(index)
        return True

    def exists(self, user_id: str = "default") -> bool:
        """Check if token exists."""
        return user_id in self._index()

    def list_users(self) -> list[str]:
        """The user IDs with a stored token, sorted."""
        return sorted(self._index())
