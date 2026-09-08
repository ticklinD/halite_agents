"""
Secret storage via `keyring` (§5, §7.1).
Falls back to `cryptography` Fernet encrypted file when keyring
backend is unavailable (headless Linux, etc.) — with a visible warning.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from halite.config.settings import CONFIG_DIR

_SERVICE_NAME = "halite"
_ENCRYPTED_FILE = CONFIG_DIR / "secrets.enc"
_FERNET_KEY_FILE = CONFIG_DIR / ".secrets_key"

_keyring_available: bool | None = None
_fernet_available: bool | None = None


def _check_keyring() -> bool:
    """Detect whether keyring has a usable backend."""
    global _keyring_available
    if _keyring_available is not None:
        return _keyring_available
    try:
        import keyring
        # Test that the backend actually works, not just that it's importable
        test_key = "__halite_test__"
        keyring.set_password(_SERVICE_NAME, test_key, "probe")
        val = keyring.get_password(_SERVICE_NAME, test_key)
        if val == "probe":
            keyring.delete_password(_SERVICE_NAME, test_key)
            _keyring_available = True
        else:
            _keyring_available = False
    except Exception:
        _keyring_available = False
    return _keyring_available


def _get_fernet():
    """Get or create a Fernet cipher for the fallback encrypted file."""
    global _fernet_available
    if _fernet_available is False:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        _fernet_available = False
        return None

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if _FERNET_KEY_FILE.exists():
        key = _FERNET_KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        _FERNET_KEY_FILE.write_bytes(key)
        # Restrict permissions on the key file
        _FERNET_KEY_FILE.chmod(0o600)

    _fernet_available = True
    return Fernet(key)


def _fernet_store(key: str, value: str) -> None:
    """Store via Fernet encrypted file."""
    fernet = _get_fernet()
    if fernet is None:
        raise RuntimeError("Fernet fallback unavailable — cryptography package not installed")

    store: dict[str, str] = {}
    if _ENCRYPTED_FILE.exists():
        encrypted = _ENCRYPTED_FILE.read_bytes()
        decrypted = fernet.decrypt(encrypted)
        store = json.loads(decrypted.decode())

    store[key] = value
    encrypted = fernet.encrypt(json.dumps(store).encode())
    _ENCRYPTED_FILE.write_bytes(encrypted)
    _ENCRYPTED_FILE.chmod(0o600)


def _fernet_retrieve(key: str) -> str | None:
    """Retrieve from Fernet encrypted file."""
    fernet = _get_fernet()
    if fernet is None:
        return None

    if not _ENCRYPTED_FILE.exists():
        return None

    encrypted = _ENCRYPTED_FILE.read_bytes()
    decrypted = fernet.decrypt(encrypted)
    store: dict[str, str] = json.loads(decrypted.decode())
    return store.get(key)


def store_secret(key: str, value: str) -> None:
    """Store a secret. Uses OS keychain if available, Fernet fallback otherwise."""
    if _check_keyring():
        import keyring
        keyring.set_password(_SERVICE_NAME, key, value)
    else:
        _fernet_store(key, value)


def retrieve_secret(key: str) -> str | None:
    """Retrieve a secret. Returns None if not found."""
    if _check_keyring():
        import keyring
        return keyring.get_password(_SERVICE_NAME, key)
    else:
        return _fernet_retrieve(key)


def delete_secret(key: str) -> bool:
    """Delete a secret. Returns True if deleted."""
    if _check_keyring():
        import keyring
        try:
            keyring.delete_password(_SERVICE_NAME, key)
            return True
        except keyring.errors.PasswordDeleteError:
            return False
    else:
        fernet = _get_fernet()
        if fernet is None or not _ENCRYPTED_FILE.exists():
            return False
        encrypted = _ENCRYPTED_FILE.read_bytes()
        decrypted = fernet.decrypt(encrypted)
        store: dict[str, str] = json.loads(decrypted.decode())
        if key in store:
            del store[key]
            encrypted = fernet.encrypt(json.dumps(store).encode())
            _ENCRYPTED_FILE.write_bytes(encrypted)
            return True
        return False


def get_secret_backend_info() -> str:
    """Return a human-readable description of the active secret backend."""
    if _check_keyring():
        import keyring
        return f"keyring (backend: {keyring.get_keyring().__class__.__name__})"
    elif _get_fernet() is not None:
        return "Fernet encrypted file (OS keychain unavailable — weaker storage, see logs)"
    else:
        return "NONE (no keyring or cryptography package)"
