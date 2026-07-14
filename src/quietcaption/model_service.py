from __future__ import annotations

import json
import hashlib
import os
import shutil
from pathlib import Path

from .models import ModelDescriptor, ModelRegistry


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_fetcher(repo_id: str, revision: str, local_dir: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("Install huggingface-hub to download local models") from exc
    snapshot_download(repo_id=repo_id, revision=revision, local_dir=str(local_dir))


class ModelService:
    def __init__(self, registry: ModelRegistry, fetcher=None):
        self.registry = registry
        self.fetcher = fetcher or _snapshot_fetcher

    def install(self, descriptor: ModelDescriptor) -> Path:
        self.registry.root.mkdir(parents=True, exist_ok=True)
        destination = self.registry.root / descriptor.id
        staging = self.registry.root / f".{descriptor.id}.installing"
        backup = self.registry.root / f".{descriptor.id}.previous"
        if staging.exists(): shutil.rmtree(staging)
        try:
            self.fetcher(descriptor.url, descriptor.revision, staging)
            files = [item for item in staging.rglob("*") if item.is_file()]
            if not files:
                raise ValueError("Downloaded model snapshot is empty")
            file_hashes = {
                item.relative_to(staging).as_posix(): _sha256(item)
                for item in files
            }
            (staging / "manifest.json").write_text(json.dumps({"id": descriptor.id, "kind": descriptor.kind, "revision": descriptor.revision, "repo_id": descriptor.url, "files": file_hashes}, indent=2), encoding="utf-8")
            (staging / ".complete").write_text(descriptor.revision, encoding="ascii")
            if backup.exists(): shutil.rmtree(backup)
            if destination.exists(): os.replace(destination, backup)
            os.replace(staging, destination)
            if backup.exists(): shutil.rmtree(backup)
            return destination
        except Exception:
            if staging.exists(): shutil.rmtree(staging)
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise

    def update(self, descriptor: ModelDescriptor) -> Path:
        """Install the catalog revision without risking the current installation."""
        return self.install(descriptor)

    def repair(self, descriptor: ModelDescriptor) -> Path:
        was_active = self.active(descriptor.kind) == descriptor
        installed = self.install(descriptor)
        if was_active:
            self.activate(descriptor)
        return installed

    def move(self, destination: Path, verifier=None) -> Path:
        """Move all installed model state after verifying a staged copy.

        The source remains untouched until the complete destination copy has
        passed verification, so an interrupted or invalid move is recoverable.
        """
        destination = Path(destination)
        source = self.registry.root
        if source.resolve() == destination.resolve():
            return destination
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Destination model folder must be empty")
        staging = destination.with_name(f".{destination.name}.moving")
        if staging.exists():
            shutil.rmtree(staging)
        try:
            shutil.copytree(source, staging)
            verify_copy = verifier or self._verify_registry_copy
            if not verify_copy(staging):
                raise ValueError("Moved model copy failed integrity verification")
            if destination.exists():
                destination.rmdir()
            os.replace(staging, destination)
            shutil.rmtree(source)
            self.registry.root = destination
            return destination
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def _verify_registry_copy(self, root: Path) -> bool:
        installed = [item for item in self.registry.catalog if self.registry.is_installed(item.id)]
        return all(
            root.joinpath(item.id, ".complete").exists()
            and root.joinpath(item.id, "manifest.json").exists()
            for item in installed
        )

    def activate(self, descriptor: ModelDescriptor) -> ModelDescriptor:
        if not self.registry.is_installed(descriptor.id):
            raise ValueError("Model must be installed before activation")
        active = self.registry.root / f"active-{descriptor.kind}.json"
        temporary = active.with_suffix(".tmp")
        temporary.write_text(json.dumps({"id": descriptor.id}), encoding="utf-8")
        os.replace(temporary, active)
        return descriptor

    def active(self, kind: str) -> ModelDescriptor | None:
        path = self.registry.root / f"active-{kind}.json"
        if not path.exists(): return None
        model_id = json.loads(path.read_text(encoding="utf-8"))["id"]
        return next((item for item in self.registry.catalog if item.id == model_id), None)

    def verify(self, descriptor: ModelDescriptor) -> bool:
        root = self.registry.root / descriptor.id
        manifest = root / "manifest.json"
        if not self.registry.is_installed(descriptor.id) or not manifest.exists():
            return False
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if payload.get("revision") != descriptor.revision:
                return False
            expected_files = payload.get("files", {})
            return bool(expected_files) and all(
                root.joinpath(relative).is_file()
                and _sha256(root / relative) == expected
                for relative, expected in expected_files.items()
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def remove(self, descriptor: ModelDescriptor, force: bool = False) -> None:
        if self.active(descriptor.kind) == descriptor and not force:
            raise ValueError("Cannot remove an active model without force")
        root = self.registry.root / descriptor.id
        if root.exists(): shutil.rmtree(root)
        active = self.registry.root / f"active-{descriptor.kind}.json"
        if force and self.active(descriptor.kind) == descriptor: active.unlink(missing_ok=True)
