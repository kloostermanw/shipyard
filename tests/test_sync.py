"""Tests for the sync module."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from shipyard.config.schema import EnvironmentConfig
from shipyard.sync.syncer import FileSyncer, SyncCheckResult, SyncEvent, SyncStatus


class TestSyncStatus:
    """Tests for SyncStatus enum."""

    def test_status_values(self) -> None:
        assert SyncStatus.IN_SYNC.value == "in_sync"
        assert SyncStatus.OUT_OF_SYNC.value == "out_of_sync"
        assert SyncStatus.SYNCING.value == "syncing"
        assert SyncStatus.ERROR.value == "error"
        assert SyncStatus.UNKNOWN.value == "unknown"
        assert SyncStatus.CHECKING.value == "checking"


class TestSyncCheckResult:
    """Tests for SyncCheckResult dataclass."""

    def test_in_sync_when_empty(self) -> None:
        result = SyncCheckResult(
            files_checked=5,
            files_out_of_sync=[],
            files_missing_remote=[],
            dirs_missing_remote=[],
        )
        assert result.is_in_sync is True
        assert result.total_changes == 0

    def test_out_of_sync_with_changed_files(self) -> None:
        result = SyncCheckResult(
            files_checked=5,
            files_out_of_sync=["config.yaml", "docker-compose.yml"],
            files_missing_remote=[],
            dirs_missing_remote=[],
        )
        assert result.is_in_sync is False
        assert result.total_changes == 2

    def test_out_of_sync_with_missing_files(self) -> None:
        result = SyncCheckResult(
            files_checked=5,
            files_out_of_sync=[],
            files_missing_remote=["new-file.txt"],
            dirs_missing_remote=[],
        )
        assert result.is_in_sync is False
        assert result.total_changes == 1

    def test_out_of_sync_with_missing_dirs(self) -> None:
        result = SyncCheckResult(
            files_checked=5,
            files_out_of_sync=[],
            files_missing_remote=[],
            dirs_missing_remote=["subdir"],
        )
        assert result.is_in_sync is False

    def test_total_changes_combined(self) -> None:
        result = SyncCheckResult(
            files_checked=10,
            files_out_of_sync=["a.txt"],
            files_missing_remote=["b.txt", "c.txt"],
            dirs_missing_remote=[],
        )
        assert result.total_changes == 3


class TestSyncEvent:
    """Tests for SyncEvent dataclass."""

    def test_event_creation(self) -> None:
        event = SyncEvent(status=SyncStatus.SYNCING, message="uploading")
        assert event.status == SyncStatus.SYNCING
        assert event.message == "uploading"
        assert event.progress is None

    def test_event_with_progress(self) -> None:
        event = SyncEvent(
            status=SyncStatus.SYNCING,
            message="uploading file.txt",
            progress=(3, 10),
        )
        assert event.progress == (3, 10)


class TestEnvironmentConfigLocalPath:
    """Tests for EnvironmentConfig local_path field."""

    def test_without_local_path(self) -> None:
        env = EnvironmentConfig(server="s1", path="/opt/apps/test")
        assert env.local_path is None

    def test_with_absolute_local_path(self) -> None:
        env = EnvironmentConfig(
            server="s1",
            path="/opt/apps/test",
            local_path="/home/user/project",
        )
        assert env.local_path == "/home/user/project"

    def test_with_tilde_local_path(self) -> None:
        env = EnvironmentConfig(
            server="s1",
            path="/opt/apps/test",
            local_path="~/repos/project",
        )
        assert env.local_path == "~/repos/project"

    def test_with_alias_local_path(self) -> None:
        """Test that local-path YAML alias works."""
        env = EnvironmentConfig.model_validate({
            "server": "s1",
            "path": "/opt/apps/test",
            "local-path": "/home/user/project",
        })
        assert env.local_path == "/home/user/project"

    def test_relative_local_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="absolute or start with ~"):
            EnvironmentConfig(
                server="s1",
                path="/opt/apps/test",
                local_path="relative/path",
            )


class TestFileSyncerScanLocal:
    """Tests for FileSyncer._scan_local with temp directory."""

    def test_scan_local_files(self, tmp_path: Path) -> None:
        # Create test files
        (tmp_path / "config.yaml").write_text("key: value")
        (tmp_path / "docker-compose.yml").write_text("version: '3'")

        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local(str(tmp_path))

        assert len(result) == 2
        assert "config.yaml" in result
        assert "docker-compose.yml" in result
        # Values should be md5 hex strings
        for md5 in result.values():
            assert len(md5) == 32

    def test_scan_local_skips_dotfiles(self, tmp_path: Path) -> None:
        (tmp_path / "visible.txt").write_text("hello")
        (tmp_path / ".hidden").write_text("secret")

        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local(str(tmp_path))

        assert "visible.txt" in result
        assert ".hidden" not in result

    def test_scan_local_skips_dot_directories(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git stuff")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.txt").write_text("content")

        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local(str(tmp_path))

        assert "subdir/file.txt" in result
        assert ".git/config" not in result

    def test_scan_local_nested_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "b" / "deep.txt").write_text("deep")
        (tmp_path / "a" / "shallow.txt").write_text("shallow")

        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local(str(tmp_path))

        assert "a/b/deep.txt" in result
        assert "a/shallow.txt" in result

    def test_scan_local_empty_dir(self, tmp_path: Path) -> None:
        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local(str(tmp_path))
        assert result == {}

    def test_scan_local_nonexistent(self) -> None:
        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local("/nonexistent/path")
        assert result == {}


class TestFileSyncerScanLocalDirs:
    """Tests for FileSyncer._scan_local_dirs."""

    def test_scan_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "subdir1").mkdir()
        (tmp_path / "subdir2").mkdir()
        (tmp_path / "subdir1" / "nested").mkdir()

        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local_dirs(str(tmp_path))

        assert "subdir1" in result
        assert "subdir2" in result
        assert "subdir1/nested" in result

    def test_scan_dirs_skips_dotdirs(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()

        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local_dirs(str(tmp_path))

        assert "visible" in result
        assert ".hidden" not in result

    def test_scan_dirs_empty(self, tmp_path: Path) -> None:
        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local_dirs(str(tmp_path))
        assert result == []

    def test_scan_dirs_nonexistent(self) -> None:
        syncer = FileSyncer.__new__(FileSyncer)
        result = syncer._scan_local_dirs("/nonexistent/path")
        assert result == []
