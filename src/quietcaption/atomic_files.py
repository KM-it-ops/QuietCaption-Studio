from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4


@dataclass(frozen=True)
class RollbackFailure:
    path: Path
    error: Exception


@dataclass(frozen=True)
class PublicationResult:
    retained_backups: tuple[Path, ...] = ()


def _unlink_with_retries(path: Path, attempts: int = 3) -> Exception | None:
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return None
        except OSError as exc:
            if attempt == attempts - 1:
                return exc
            time.sleep(0.01)
    return None


def publish_text_batch(
    contents: dict[Path, str],
    temporary_paths: dict[Path, Path] | None = None,
    *,
    replace_existing: bool = True,
    before_publish: Callable[[], None] | None = None,
) -> PublicationResult:
    """Stage and publish a group of text files, rolling back partial publication."""
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    restored: set[Path] = set()
    rollback_failures: list[RollbackFailure] = []
    retained_backups: list[Path] = []
    committed = False
    try:
        for destination, content in contents.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = (temporary_paths or {}).get(
                destination,
                destination.with_name(f".{destination.name}.{uuid4().hex}.tmp"),
            )
            staged[destination] = temporary
            temporary.write_text(content, encoding="utf-8")
        if before_publish is not None:
            before_publish()
        for destination in contents:
            if replace_existing and destination.exists():
                backup = destination.with_name(f".{destination.name}.{uuid4().hex}.bak")
                shutil.copyfile(destination, backup)
                backups[destination] = backup
        for destination, temporary in staged.items():
            if replace_existing:
                os.replace(temporary, destination)
            else:
                os.link(temporary, destination)
            published.append(destination)
        committed = True
    except Exception as primary:
        for destination in reversed(published):
            backup = backups.get(destination)
            if backup is None:
                try:
                    destination.unlink(missing_ok=True)
                except Exception as error:
                    rollback_failures.append(RollbackFailure(destination, error))
            else:
                try:
                    os.replace(backup, destination)
                except Exception as error:
                    rollback_failures.append(RollbackFailure(destination, error))
                    continue
                restored.add(destination)
        if rollback_failures:
            primary.rollback_failures = tuple(rollback_failures)
            detail = "; ".join(f"{failure.path}: {failure.error}" for failure in rollback_failures)
            primary.add_note(f"Rollback incomplete; manual cleanup may be required: {detail}")
        raise
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except Exception:
                pass
        for destination, backup in backups.items():
            if not committed and destination in published and destination not in restored:
                continue
            cleanup_error = _unlink_with_retries(backup)
            if committed and cleanup_error is not None and backup.exists():
                retained_backups.append(backup)
    return PublicationResult(tuple(retained_backups))
