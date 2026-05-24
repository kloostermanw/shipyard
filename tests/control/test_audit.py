"""Tests for the audit log writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from shipyard.control.audit import AuditLog


@pytest.fixture
def audit_path(tmp_path) -> Path:
    return tmp_path / "audit.log"


def test_write_creates_file_with_secure_mode(audit_path) -> None:
    log = AuditLog(path=audit_path)
    log.write(method="apps.list", params_summary={}, result_code=0)
    assert audit_path.exists()
    mode = audit_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_write_appends_jsonl(audit_path) -> None:
    import json

    log = AuditLog(path=audit_path)
    log.write(method="apps.list", params_summary={}, result_code=0)
    log.write(method="apps.get", params_summary={"app_id": "frontend"}, result_code=0)
    lines = audit_path.read_text().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[1])
    assert rec["method"] == "apps.get"
    assert rec["params_summary"] == {"app_id": "frontend"}
    assert rec["result_code"] == 0
    assert "timestamp" in rec


def test_secrets_set_does_not_log_value(audit_path) -> None:
    import json

    log = AuditLog(path=audit_path)
    log.write(
        method="secrets.set",
        params_summary={"key": "DB_PASSWORD"},  # caller responsible for stripping value
        result_code=0,
    )
    rec = json.loads(audit_path.read_text().splitlines()[0])
    assert "value" not in rec["params_summary"]


def test_rotation_when_size_exceeded(audit_path) -> None:
    log = AuditLog(path=audit_path, max_bytes=200, max_generations=3)
    # Write enough entries to trigger rotation a few times
    for i in range(30):
        log.write(method="apps.list", params_summary={"i": i}, result_code=0)
    assert audit_path.exists()
    # At least audit.log.1 should exist
    assert (audit_path.parent / (audit_path.name + ".1")).exists()
    # No generation past max should exist
    assert not (audit_path.parent / (audit_path.name + ".4")).exists()


def test_peer_credentials_included_when_provided(audit_path) -> None:
    import json

    log = AuditLog(path=audit_path)
    log.write(
        method="apps.list",
        params_summary={},
        result_code=0,
        peer={"pid": 1234, "uid": 501},
    )
    rec = json.loads(audit_path.read_text().splitlines()[0])
    assert rec["peer"] == {"pid": 1234, "uid": 501}
