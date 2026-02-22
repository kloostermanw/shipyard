"""File syncer - one-way local→remote sync via SFTP over SSH."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import AsyncIterator

from shipyard.ssh.connection import SSHConnectionPool


class SyncStatus(Enum):
    IN_SYNC = "in_sync"
    OUT_OF_SYNC = "out_of_sync"
    SYNCING = "syncing"
    ERROR = "error"
    UNKNOWN = "unknown"
    CHECKING = "checking"


@dataclass
class SyncCheckResult:
    files_checked: int
    files_out_of_sync: list[str]
    files_missing_remote: list[str]
    dirs_missing_remote: list[str]

    @property
    def is_in_sync(self) -> bool:
        return (
            not self.files_out_of_sync
            and not self.files_missing_remote
            and not self.dirs_missing_remote
        )

    @property
    def total_changes(self) -> int:
        return len(self.files_out_of_sync) + len(self.files_missing_remote)


@dataclass
class SyncEvent:
    status: SyncStatus
    message: str
    progress: tuple[int, int] | None = None


class FileSyncer:
    """Syncs local files to remote servers via SFTP.

    Only adds/updates files — never deletes on the remote side.
    Skips dotfiles (files starting with '.').
    """

    def __init__(self, ssh_pool: SSHConnectionPool) -> None:
        self._ssh_pool = ssh_pool

    def _scan_local(self, local_path: str) -> dict[str, str]:
        """Walk local directory and return {relative_path: md5_hex}.

        Skips dotfiles and dot-directories.
        """
        root = Path(local_path).expanduser().resolve()
        result: dict[str, str] = {}

        if not root.is_dir():
            return result

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for filename in filenames:
                if filename.startswith("."):
                    continue
                full_path = Path(dirpath) / filename
                relative = str(full_path.relative_to(root))
                md5 = hashlib.md5(full_path.read_bytes()).hexdigest()
                result[relative] = md5

        return result

    def _scan_local_dirs(self, local_path: str) -> list[str]:
        """Return all subdirectory relative paths (including nested/empty ones).

        Skips dot-directories.
        """
        root = Path(local_path).expanduser().resolve()
        result: list[str] = []

        if not root.is_dir():
            return result

        for dirpath, dirnames, _ in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for d in dirnames:
                full = Path(dirpath) / d
                result.append(str(full.relative_to(root)))

        return result

    async def _get_remote_checksums(
        self, server_id: str, remote_path: str
    ) -> dict[str, str]:
        """Run md5sum on remote files via SSH.

        Returns {relative_path: md5_hex}.
        """
        conn = await self._ssh_pool.get_connection(server_id)
        cmd = f"find {remote_path} -type f ! -name '.*' -exec md5sum {{}} +"
        result = await conn.run(cmd, timeout=30)
        stdout = result.stdout or ""

        checksums: dict[str, str] = {}
        for line in stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            md5_hex, abs_path = parts
            # Convert absolute path to relative
            if abs_path.startswith(remote_path):
                relative = abs_path[len(remote_path) :].lstrip("/")
                if relative:
                    checksums[relative] = md5_hex

        return checksums

    async def check_sync_status(
        self, server_id: str, local_path: str, remote_path: str
    ) -> SyncCheckResult:
        """Compare local vs remote checksums and return diff result."""
        local_files = self._scan_local(local_path)
        remote_files = await self._get_remote_checksums(server_id, remote_path)
        local_dirs = self._scan_local_dirs(local_path)

        # Check for remote directories that don't exist
        conn = await self._ssh_pool.get_connection(server_id)
        dirs_missing: list[str] = []
        for d in local_dirs:
            check = await conn.run(f"test -d {remote_path}/{d}", timeout=5)
            if check.exit_status != 0:
                dirs_missing.append(d)

        files_missing: list[str] = []
        files_out_of_sync: list[str] = []

        for rel_path, local_md5 in local_files.items():
            if rel_path not in remote_files:
                files_missing.append(rel_path)
            elif remote_files[rel_path] != local_md5:
                files_out_of_sync.append(rel_path)

        return SyncCheckResult(
            files_checked=len(local_files),
            files_out_of_sync=files_out_of_sync,
            files_missing_remote=files_missing,
            dirs_missing_remote=dirs_missing,
        )

    async def sync(
        self, server_id: str, local_path: str, remote_path: str
    ) -> AsyncIterator[SyncEvent]:
        """Sync local files to remote via SFTP. Yields progress events."""
        local_root = Path(local_path).expanduser().resolve()

        yield SyncEvent(
            status=SyncStatus.SYNCING,
            message="Scanning local files...",
        )

        local_files = self._scan_local(local_path)
        local_dirs = self._scan_local_dirs(local_path)

        if not local_files:
            yield SyncEvent(
                status=SyncStatus.ERROR,
                message=f"No files found in {local_path}",
            )
            return

        yield SyncEvent(
            status=SyncStatus.SYNCING,
            message=f"Found {len(local_files)} local file(s)",
        )

        yield SyncEvent(
            status=SyncStatus.SYNCING,
            message="Getting remote checksums...",
        )

        try:
            remote_files = await self._get_remote_checksums(server_id, remote_path)
        except Exception as exc:
            yield SyncEvent(
                status=SyncStatus.ERROR,
                message=f"Failed to get remote checksums: {exc}",
            )
            return

        # Determine what needs syncing
        to_sync: list[str] = []
        for rel_path, local_md5 in local_files.items():
            if rel_path not in remote_files or remote_files[rel_path] != local_md5:
                to_sync.append(rel_path)

        if not to_sync and not any(d for d in local_dirs if d not in remote_files):
            yield SyncEvent(
                status=SyncStatus.IN_SYNC,
                message="All files are in sync",
                progress=(len(local_files), len(local_files)),
            )
            return

        yield SyncEvent(
            status=SyncStatus.SYNCING,
            message=f"{len(to_sync)} file(s) to sync",
        )

        try:
            conn = await self._ssh_pool.get_connection(server_id)
            async with conn.start_sftp_client() as sftp:
                # Create missing directories
                for d in local_dirs:
                    remote_dir = f"{remote_path}/{d}"
                    try:
                        await sftp.stat(remote_dir)
                    except (OSError, Exception):
                        yield SyncEvent(
                            status=SyncStatus.SYNCING,
                            message=f"Creating directory: {d}",
                        )
                        await sftp.makedirs(remote_dir, exist_ok=True)

                # Upload files
                for i, rel_path in enumerate(to_sync, 1):
                    local_file = local_root / rel_path
                    remote_file = f"{remote_path}/{rel_path}"

                    yield SyncEvent(
                        status=SyncStatus.SYNCING,
                        message=f"Uploading: {rel_path}",
                        progress=(i, len(to_sync)),
                    )

                    await sftp.put(str(local_file), remote_file)

            yield SyncEvent(
                status=SyncStatus.IN_SYNC,
                message=f"Sync complete — {len(to_sync)} file(s) transferred",
                progress=(len(to_sync), len(to_sync)),
            )

        except Exception as exc:
            yield SyncEvent(
                status=SyncStatus.ERROR,
                message=f"Sync failed: {exc}",
            )
