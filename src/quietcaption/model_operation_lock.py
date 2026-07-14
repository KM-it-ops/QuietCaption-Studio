from __future__ import annotations

import errno
import os
import threading
from pathlib import Path
from typing import BinaryIO


DEFAULT_STALE_AFTER_SECONDS = 30.0


class ModelOperationLock:
    """Immediate registry lock backed by an OS-owned open file handle."""

    _process_guard = threading.Lock()
    _active_paths: set[Path] = set()

    def __init__(self, registry_root: Path, *, stale_after: float = DEFAULT_STALE_AFTER_SECONDS) -> None:
        self.registry_root = Path(registry_root).resolve()
        self.path = self.registry_root.with_name(f".{self.registry_root.name}.model-operation.lock")
        self.stale_after = stale_after
        self.acquired = False
        self._handle: BinaryIO | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._process_guard:
            if self.path in self._active_paths:
                return False
            handle = self.path.open("a+b")
            try:
                self._ensure_lock_byte(handle)
                self._lock_nonblocking(handle)
            except OSError as exc:
                handle.close()
                if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    return False
                raise
            self._active_paths.add(self.path)
            self._handle = handle
            self.acquired = True
            return True

    def release(self) -> None:
        if not self.acquired:
            return
        with self._process_guard:
            handle = self._handle
            try:
                if handle is not None:
                    self._unlock(handle)
            finally:
                if handle is not None:
                    handle.close()
                self._active_paths.discard(self.path)
                self._handle = None
                self.acquired = False

    @staticmethod
    def _ensure_lock_byte(handle: BinaryIO) -> None:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

    @staticmethod
    def _lock_nonblocking(handle: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(handle: BinaryIO) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
