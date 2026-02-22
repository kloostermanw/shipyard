"""Encrypted key-value secret store using Fernet + PBKDF2."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


_DEFAULT_PATH = Path("~/.config/shipyard/secrets.enc")
_SALT_LENGTH = 16
_PBKDF2_ITERATIONS = 480_000


class SecretStoreError(Exception):
    """Raised on wrong password, locked access, or corrupt data."""


class SecretStore:
    """Encrypted key-value store backed by a single file.

    File format: <16-byte salt><fernet-encrypted JSON dict>
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = (path or _DEFAULT_PATH).expanduser()
        self._secrets: dict[str, str] = {}
        self._fernet: Fernet | None = None
        self._salt: bytes = b""

    @property
    def is_unlocked(self) -> bool:
        return self._fernet is not None

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    def unlock(self, password: str) -> None:
        """Derive key from password and decrypt the store.

        Creates a new empty store if the file does not exist.
        """
        if self._path.exists():
            raw = self._path.read_bytes()
            if len(raw) < _SALT_LENGTH:
                raise SecretStoreError("Corrupt secret store (file too short)")
            salt = raw[:_SALT_LENGTH]
            encrypted = raw[_SALT_LENGTH:]
            key = self._derive_key(password, salt)
            fernet = Fernet(key)
            try:
                decrypted = fernet.decrypt(encrypted)
            except InvalidToken:
                raise SecretStoreError("Wrong password")
            try:
                data = json.loads(decrypted)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise SecretStoreError("Corrupt secret store (invalid data)")
            self._secrets = data
            self._salt = salt
            self._fernet = fernet
        else:
            # New store — generate fresh salt
            salt = os.urandom(_SALT_LENGTH)
            key = self._derive_key(password, salt)
            self._salt = salt
            self._fernet = Fernet(key)
            self._secrets = {}
            self._save()

    def _require_unlocked(self) -> None:
        if not self.is_unlocked:
            raise SecretStoreError("Secret store is locked")

    def get(self, key: str) -> str:
        self._require_unlocked()
        if key not in self._secrets:
            raise SecretStoreError(f"Secret not found: {key}")
        return self._secrets[key]

    def set(self, key: str, value: str) -> None:
        self._require_unlocked()
        self._secrets[key] = value
        self._save()

    def delete(self, key: str) -> None:
        self._require_unlocked()
        if key not in self._secrets:
            raise SecretStoreError(f"Secret not found: {key}")
        del self._secrets[key]
        self._save()

    def list_keys(self) -> list[str]:
        self._require_unlocked()
        return sorted(self._secrets.keys())

    def get_all(self) -> dict[str, str]:
        self._require_unlocked()
        return dict(self._secrets)

    def _save(self) -> None:
        assert self._fernet is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._secrets).encode()
        encrypted = self._fernet.encrypt(payload)
        self._path.write_bytes(self._salt + encrypted)
