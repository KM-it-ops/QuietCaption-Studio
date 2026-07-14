from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


DEFAULT_STALE_AFTER_SECONDS = 30.0


@dataclass(frozen=True)
class LockReleaseWarning:
    description: str
    path: Path
    error: OSError

    def __str__(self) -> str:
        return f"{self.description} cleanup failed at {self.path}: {self.error}"


class FilesystemLock:
    """Atomic filesystem lock with conservative orphan recovery and non-throwing release."""

    _active_tokens: set[str] = set()

    def __init__(
        self,
        path: Path,
        *,
        description: str = "Filesystem lock",
        stale_after: float = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.description = description
        self.stale_after = stale_after
        self.token = uuid4().hex
        self.acquired = False

    def acquire(self, timeout: float = 0.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            if self._acquire_once():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def _acquire_once(self) -> bool:
        for attempt in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if attempt == 0 and self._recover_orphaned_lock():
                    continue
                return False

            self._active_tokens.add(self.token)
            primary = None
            try:
                metadata = {
                    "pid": os.getpid(),
                    "token": self.token,
                    "created_at": time.time(),
                }
                os.write(descriptor, json.dumps(metadata).encode("utf-8"))
            except Exception as exc:
                primary = exc
            try:
                os.close(descriptor)
            except Exception as close_error:
                if primary is None:
                    primary = close_error
                else:
                    primary.close_error = close_error
                    primary.add_note(f"Lock descriptor close also failed: {close_error}")
            if primary is not None:
                self._active_tokens.discard(self.token)
                cleanup_error = self._unlink_with_retries()
                if cleanup_error is not None:
                    primary.cleanup_error = cleanup_error
                    primary.add_note(f"Partial lock cleanup failed at {self.path}: {cleanup_error}")
                raise primary

            self.acquired = True
            return True
        return False

    def release(self) -> LockReleaseWarning | None:
        if not self.acquired:
            return None
        error = self._unlink_with_retries()
        self._active_tokens.discard(self.token)
        self.acquired = False
        if error is None:
            return None
        return LockReleaseWarning(self.description, self.path, error)

    def _recover_orphaned_lock(self) -> bool:
        try:
            metadata = json.loads(self.path.read_text(encoding="utf-8"))
            token = metadata.get("token")
            pid = int(metadata.get("pid"))
            float(metadata.get("created_at"))
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
            return self._recover_aged_unchanged_lock()
        except OSError:
            return False
        if token in self._active_tokens:
            return False
        if pid != os.getpid() and self._pid_running(pid):
            return False
        return self._unlink_with_retries() is None

    def _recover_aged_unchanged_lock(self) -> bool:
        try:
            observed = self.path.stat()
        except OSError:
            return False
        if time.time() - observed.st_mtime < self.stale_after:
            return False
        try:
            current = self.path.stat()
        except OSError:
            return False
        identity = (observed.st_ino, observed.st_size, observed.st_mtime_ns)
        if identity != (current.st_ino, current.st_size, current.st_mtime_ns):
            return False
        return self._unlink_with_retries() is None

    def _unlink_with_retries(self) -> OSError | None:
        for attempt in range(3):
            try:
                self.path.unlink(missing_ok=True)
                return None
            except OSError as exc:
                if attempt == 2:
                    return exc
                time.sleep(0.01)
        return None

    @staticmethod
    def _pid_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
