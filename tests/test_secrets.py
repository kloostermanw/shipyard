"""Tests for the encrypted SecretStore."""

import pytest

from shipyard.secrets.store import SecretStore, SecretStoreError


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "secrets.enc"


@pytest.fixture
def store(store_path):
    s = SecretStore(path=store_path)
    s.unlock("testpassword")
    return s


def test_create_new_store(store_path):
    """A new store creates the file on unlock."""
    s = SecretStore(path=store_path)
    assert not store_path.exists()
    s.unlock("mypassword")
    assert store_path.exists()
    assert s.is_unlocked
    assert s.list_keys() == []


def test_set_and_get(store):
    store.set("DB_HOST", "localhost")
    assert store.get("DB_HOST") == "localhost"


def test_persistence(store_path):
    """Secrets survive closing and reopening with the same password."""
    s1 = SecretStore(path=store_path)
    s1.unlock("pw123")
    s1.set("KEY_A", "value_a")
    s1.set("KEY_B", "value_b")

    s2 = SecretStore(path=store_path)
    s2.unlock("pw123")
    assert s2.get("KEY_A") == "value_a"
    assert s2.get("KEY_B") == "value_b"


def test_wrong_password(store_path):
    """Wrong password raises SecretStoreError."""
    s1 = SecretStore(path=store_path)
    s1.unlock("correct")
    s1.set("X", "1")

    s2 = SecretStore(path=store_path)
    with pytest.raises(SecretStoreError, match="Wrong password"):
        s2.unlock("wrong")


def test_delete(store):
    store.set("DEL_ME", "bye")
    assert "DEL_ME" in store.list_keys()
    store.delete("DEL_ME")
    assert "DEL_ME" not in store.list_keys()


def test_delete_missing_key(store):
    with pytest.raises(SecretStoreError, match="Secret not found"):
        store.delete("NONEXISTENT")


def test_get_missing_key(store):
    with pytest.raises(SecretStoreError, match="Secret not found"):
        store.get("NONEXISTENT")


def test_list_keys_sorted(store):
    store.set("ZEBRA", "z")
    store.set("ALPHA", "a")
    store.set("MIKE", "m")
    assert store.list_keys() == ["ALPHA", "MIKE", "ZEBRA"]


def test_operations_while_locked(store_path):
    """All operations raise when the store is locked."""
    s = SecretStore(path=store_path)
    assert not s.is_unlocked

    with pytest.raises(SecretStoreError, match="locked"):
        s.get("X")
    with pytest.raises(SecretStoreError, match="locked"):
        s.set("X", "1")
    with pytest.raises(SecretStoreError, match="locked"):
        s.delete("X")
    with pytest.raises(SecretStoreError, match="locked"):
        s.list_keys()
    with pytest.raises(SecretStoreError, match="locked"):
        s.get_all()


def test_get_all(store):
    store.set("A", "1")
    store.set("B", "2")
    assert store.get_all() == {"A": "1", "B": "2"}


def test_overwrite_value(store):
    store.set("KEY", "old")
    store.set("KEY", "new")
    assert store.get("KEY") == "new"
