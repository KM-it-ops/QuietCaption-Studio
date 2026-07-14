from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4


def publish_text_batch(contents: dict[Path, str], temporary_paths: dict[Path, Path] | None = None) -> None:
    """Stage and publish a group of text files, rolling back partial publication."""
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for destination, content in contents.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = (temporary_paths or {}).get(
                destination,
                destination.with_name(f".{destination.name}.{uuid4().hex}.tmp"),
            )
            staged[destination] = temporary
            temporary.write_text(content, encoding="utf-8")
        for destination in contents:
            if destination.exists():
                backup = destination.with_name(f".{destination.name}.{uuid4().hex}.bak")
                shutil.copyfile(destination, backup)
                backups[destination] = backup
        for destination, temporary in staged.items():
            os.replace(temporary, destination)
            published.append(destination)
    except Exception:
        for destination in reversed(published):
            backup = backups.get(destination)
            if backup is None:
                destination.unlink(missing_ok=True)
            else:
                os.replace(backup, destination)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)
