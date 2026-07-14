from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4


DEFAULT_STALE_AFTER_SECONDS = 30.0


class ModelOperationLock:
    """Immediate registry-scoped lock whose owner alone may release it."""

    _process_guard = threading.Lock()
    _active_tokens: set[str] = set()

    def __init__(self, registry_root: Path, *, stale_after: float = DEFAULT_STALE_AFTER_SECONDS) -> None:
        self.registry_root = Path(registry_root).resolve()
        self.path = self.registry_root.with_name(f".{self.registry_root.name}.model-operation.lock")
        self.stale_after = stale_after
        self.token = uuid4().hex
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._process_guard:
            for attempt in range(2):
                try:
                    descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    if attempt == 0 and self._recover_orphaned_lock():
                        continue
                    return False

                try:
                    payload = {"pid": os.getpid(), "token": self.token, "created_at": time.time()}
                    os.write(descriptor, json.dumps(payload).encode("utf-8"))
                except Exception:
                    try:
                        os.close(descriptor)
                    finally:
                        self.path.unlink(missing_ok=True)
                    raise
                os.close(descriptor)
                self._active_tokens.add(self.token)
                self.acquired = True
                return True
        return False

    def release(self) -> None:
        if not self.acquired:
            return
        with self._process_guard:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                payload = None
            try:
                if isinstance(payload, dict) and payload.get("token") == self.token:
                    self.path.unlink(missing_ok=True)
            except OSError:
                pass
            finally:
                self._active_tokens.discard(self.token)
                self.acquired = False

    def _recover_orphaned_lock(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            token = payload["token"]
            pid = int(payload["pid"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return self._recover_aged_unchanged_lock()
        except OSError:
            return False
        if token in self._active_tokens or (pid != os.getpid() and self._pid_running(pid)):
            return False
        self.path.unlink(missing_ok=True)
        return True

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
        try:
            self.path.unlink()
        except OSError:
            return False
        return True

    @staticmethod
    def _pid_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
