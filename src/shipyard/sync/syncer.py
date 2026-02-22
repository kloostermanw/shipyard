"""File syncer - one-way local→remote sync via SFTP over SSH."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

from shipyard.ssh.connection import SSHConnectionPool

if TYPE_CHECKING:
    from shipyard.secrets.store import SecretStore


_TEMPLATE_RE = re.compile(r"\{\{(\w+)\}\}")


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


class TemplateError(Exception):
    """Raised when a .j2 template references undefined secret variables."""


class FileSyncer:
    """Syncs local files to remote servers via SFTP.

    Only adds/updates files — never deletes on the remote side.
    Skips dotfiles (files starting with '.').
    """

    def __init__(
        self, ssh_pool: SSHConnectionPool, secret_store: SecretStore | None = None
    ) -> None:
        self._ssh_pool = ssh_pool
        self._secret_store = secret_store

    def _can_process_templates(self) -> bool:
        """Return True if the secret store is present and unlocked."""
        return self._secret_store is not None and self._secret_store.is_unlocked

    def _process_template(self, content: bytes, file_path: str) -> bytes:
        """Replace {{VAR}} placeholders with secret values.

        Raises TemplateError listing all missing variables.
        """
        text = content.decode("utf-8")
        variables = set(_TEMPLATE_RE.findall(text))
        if not variables:
            return content

        secrets = self._secret_store.get_all() if self._secret_store else {}
        missing = sorted(variables - secrets.keys())
        if missing:
            raise TemplateError(
                f"Template '{file_path}' references undefined secrets: {', '.join(missing)}"
            )

        rendered = _TEMPLATE_RE.sub(lambda m: secrets[m.group(1)], text)
        return rendered.encode("utf-8")

    def _scan_local(self, local_path: str) -> dict[str, str]:
        """Walk local directory and return {relative_path: md5_hex}.

        Skips dotfiles and dot-directories.
        For .j2 files when secrets are unlocked: registers under output name
        (strip .j2) and computes MD5 of rendered content.
        """
        root = Path(local_path).expanduser().resolve()
        result: dict[str, str] = {}

        if not root.is_dir():
            return result

        process_templates = self._can_process_templates()
        templates: set[str] = set()  # output names claimed by .j2 files

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

            for filename in filenames:
                if filename.startswith("."):
                    continue
                full_path = Path(dirpath) / filename
                relative = str(full_path.relative_to(root))
                raw_bytes = full_path.read_bytes()

                if filename.endswith(".j2") and process_templates:
                    output_name = relative[:-3]  # strip .j2
                    if output_name in result:
                        raise TemplateError(
                            f"Conflict: both '{output_name}' and '{relative}' exist"
                        )
                    rendered = self._process_template(raw_bytes, relative)
                    md5 = hashlib.md5(rendered).hexdigest()
                    result[output_name] = md5
                    # Track that this name came from a template
                    templates.add(output_name)
                else:
                    if filename.endswith(".j2") and not process_templates:
                        # Check for conflict with non-template file
                        output_name = relative[:-3]
                        if output_name in result:
                            raise TemplateError(
                                f"Conflict: both '{output_name}' and '{relative}' exist"
                            )
                    elif not filename.endswith(".j2") and relative in templates:
                        raise TemplateError(
                            f"Conflict: both '{relative}' and '{relative}.j2' exist"
                        )
                    md5 = hashlib.md5(raw_bytes).hexdigest()
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

    def _get_source_path(self, local_root: Path, rel_path: str) -> tuple[Path, bool]:
        """Return (source_file_path, is_template).

        If a .j2 variant exists for rel_path, returns the template path.
        """
        j2_path = local_root / (rel_path + ".j2")
        if j2_path.is_file() and self._can_process_templates():
            return j2_path, True
        return local_root / rel_path, False

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

    def _has_j2_files(self, local_path: str) -> bool:
        """Check if the local directory contains any .j2 template files."""
        root = Path(local_path).expanduser().resolve()
        if not root.is_dir():
            return False
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for f in filenames:
                if f.endswith(".j2") and not f.startswith("."):
                    return True
        return False

    async def sync(
        self, server_id: str, local_path: str, remote_path: str
    ) -> AsyncIterator[SyncEvent]:
        """Sync local files to remote via SFTP. Yields progress events."""
        local_root = Path(local_path).expanduser().resolve()

        # Check if .j2 files exist but secrets store is locked
        if self._has_j2_files(local_path) and not self._can_process_templates():
            yield SyncEvent(
                status=SyncStatus.ERROR,
                message="Template files found but secrets store is locked. "
                "Unlock secrets first (press 'e' on dashboard).",
            )
            return

        yield SyncEvent(
            status=SyncStatus.SYNCING,
            message="Scanning local files...",
        )

        try:
            local_files = self._scan_local(local_path)
        except TemplateError as exc:
            yield SyncEvent(
                status=SyncStatus.ERROR,
                message=str(exc),
            )
            return
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
                    source_path, is_template = self._get_source_path(local_root, rel_path)
                    remote_file = f"{remote_path}/{rel_path}"

                    yield SyncEvent(
                        status=SyncStatus.SYNCING,
                        message=f"Uploading: {rel_path}"
                        + (" (template)" if is_template else ""),
                        progress=(i, len(to_sync)),
                    )

                    if is_template:
                        rendered = self._process_template(
                            source_path.read_bytes(), str(source_path.name)
                        )
                        async with sftp.open(remote_file, "wb") as f:
                            await f.write(rendered)
                    else:
                        await sftp.put(str(source_path), remote_file)

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
