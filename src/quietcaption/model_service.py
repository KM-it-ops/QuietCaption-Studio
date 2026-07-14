from __future__ import annotations

import json
import hashlib
import os
import shutil
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4
from weakref import WeakValueDictionary

from .model_operation_lock import ModelOperationLock
from .models import ModelDescriptor, ModelRegistry


@dataclass(frozen=True)
class ModelRuntime:
    descriptor: ModelDescriptor
    path: Path


@dataclass
class _RegistryUseState:
    lock: threading.RLock = field(default_factory=threading.RLock)
    counts: dict[str, int] = field(default_factory=dict)


_registry_states_guard = threading.Lock()
_registry_states: WeakValueDictionary[Path, _RegistryUseState] = WeakValueDictionary()


def _registry_use_state(registry_root: Path) -> _RegistryUseState:
    normalized_root = Path(registry_root).resolve()
    with _registry_states_guard:
        return _registry_states.setdefault(normalized_root, _RegistryUseState())


class ModelUseLease:
    def __init__(self, state: _RegistryUseState, runtimes: tuple[ModelRuntime, ...]):
        self._state = state
        self.runtimes = runtimes
        self._released = False

    def release(self) -> None:
        with self._state.lock:
            if self._released:
                return
            for runtime in self.runtimes:
                model_id = runtime.descriptor.id
                remaining = self._state.counts[model_id] - 1
                if remaining:
                    self._state.counts[model_id] = remaining
                else:
                    del self._state.counts[model_id]
            self._released = True

    def __enter__(self) -> "ModelUseLease":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


class ModelOperationBusy(RuntimeError):
    def __init__(self, registry_root: Path, operation: str):
        self.registry_root = Path(registry_root)
        self.operation = operation
        super().__init__(
            f"Model registry at {self.registry_root} is busy with another lifecycle mutation; "
            f"cannot start {operation}. Wait for the current operation to finish and retry."
        )


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


class _MutationJournal:
    """Own reversible model swaps and pointer snapshots until commit."""

    def __init__(self, operation: str, cleanup_warning: Callable[[str, Path, Exception], None]) -> None:
        self._operation = operation
        self._cleanup_warning = cleanup_warning
        self._undo: list[tuple[str, Path, Path | bytes | None]] = []
        self._owned_artifacts: set[Path] = set()
        self._captured_pointers: set[Path] = set()

    def __enter__(self) -> "_MutationJournal":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    def claim(self, path: Path) -> None:
        self._owned_artifacts.add(path)

    def relinquish(self, path: Path) -> None:
        self._owned_artifacts.discard(path)

    def record_swap(self, destination: Path, backup: Path | None) -> None:
        self._undo.append(("swap", destination, backup))

    def capture_pointer(self, path: Path) -> None:
        if path in self._captured_pointers:
            return
        previous = path.read_bytes() if path.exists() else None
        self._captured_pointers.add(path)
        self._undo.append(("pointer", path, previous))

    def commit(self) -> None:
        self._undo.clear()
        self._captured_pointers.clear()
        self._cleanup_owned_artifacts()

    def rollback(self) -> None:
        for action, path, previous in reversed(self._undo):
            if action == "swap":
                if path.exists():
                    _remove_path(path)
                if isinstance(previous, Path) and previous.exists():
                    os.replace(previous, path)
                    self.relinquish(previous)
                continue
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                temporary = path.with_name(f".{path.name}.rollback.{uuid4().hex}")
                self.claim(temporary)
                temporary.write_bytes(previous)
                os.replace(temporary, path)
                self.relinquish(temporary)
        self._cleanup_owned_artifacts()
        self._undo.clear()
        self._captured_pointers.clear()

    def _cleanup_owned_artifacts(self) -> None:
        for path in tuple(self._owned_artifacts):
            try:
                if path.exists():
                    _remove_path(path)
            except Exception as exc:
                self._cleanup_warning(self._operation, path, exc)
            else:
                self._owned_artifacts.discard(path)


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
        self._state_guard = threading.Lock()
        self._state_root = self.registry.root.resolve()
        self._use_state = _registry_use_state(self._state_root)
        self._cleanup_warnings: list[str] = []
        self._pending_cleanup_paths: set[Path] = set()

    @property
    def cleanup_warnings(self) -> tuple[str, ...]:
        return tuple(self._cleanup_warnings)

    @property
    def pending_cleanup_paths(self) -> tuple[Path, ...]:
        return tuple(sorted(self._pending_cleanup_paths, key=str))

    def _record_cleanup_warning(self, operation: str, path: Path, exc: Exception) -> None:
        owned_path = Path(path)
        self._pending_cleanup_paths.add(owned_path)
        self._cleanup_warnings.append(
            f"{operation} left the authoritative model state valid, but cleanup of "
            f"{owned_path} failed: {exc}. Remove this residual path only after confirming "
            "that no model lifecycle operation is running."
        )

    def _state_for_root(self, root: Path) -> _RegistryUseState:
        normalized_root = Path(root).resolve()
        with self._state_guard:
            if normalized_root != self._state_root:
                self._state_root = normalized_root
                self._use_state = _registry_use_state(normalized_root)
            return self._use_state

    def _journal(self, operation: str) -> _MutationJournal:
        return _MutationJournal(operation, self._record_cleanup_warning)

    @contextmanager
    def mutation(self, operation: str):
        """Acquire one immediate mutation transaction for this registry root."""
        root = self.registry.root.resolve()
        operation_lock = ModelOperationLock(root)
        if not operation_lock.acquire():
            raise ModelOperationBusy(root, operation)
        state = self._state_for_root(root)
        try:
            with state.lock:
                yield
        finally:
            operation_lock.release()

    def acquire_runtime(self, kinds: tuple[str, ...]) -> ModelUseLease:
        while True:
            root = self.registry.root.resolve()
            state = self._state_for_root(root)
            with state.lock:
                if self.registry.root.resolve() != root:
                    continue
                runtimes = []
                for kind in kinds:
                    try:
                        descriptor = self._active_at_root(kind, root)
                    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                        raise ValueError(f"Active {kind} model pointer is invalid") from exc
                    if descriptor is None:
                        raise ValueError(f"No active {kind} model is ready")
                    if descriptor.kind != kind:
                        raise ValueError(f"Active {kind} model pointer selects the wrong model kind")
                    path = root / descriptor.id
                    if not self._is_installed_at_root(descriptor.id, root):
                        raise ValueError(f"Active {kind} model is not installed")
                    marker = path / ".complete"
                    try:
                        marker_revision = marker.read_text(encoding="ascii")
                    except (OSError, UnicodeError) as exc:
                        raise ValueError(f"Active {kind} model installation marker is invalid") from exc
                    if not path.is_dir() or not marker.is_file() or marker_revision != descriptor.revision:
                        raise ValueError(f"Active {kind} model installation marker is invalid")
                    manifest = path / "manifest.json"
                    if not manifest.is_file():
                        raise ValueError(f"Active {kind} model manifest is missing")
                    try:
                        payload = json.loads(manifest.read_text(encoding="utf-8"))
                    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                        raise ValueError(f"Active {kind} model manifest is invalid") from exc
                    identity = (payload.get("id"), payload.get("kind"), payload.get("revision"), payload.get("repo_id"))
                    expected_identity = (descriptor.id, descriptor.kind, descriptor.revision, descriptor.url)
                    if identity != expected_identity or not self._verify_at_root(descriptor, root):
                        raise ValueError(f"Active {kind} model manifest is invalid")
                    runtimes.append(ModelRuntime(descriptor, path))
                result = tuple(runtimes)
                for runtime in result:
                    model_id = runtime.descriptor.id
                    state.counts[model_id] = state.counts.get(model_id, 0) + 1
                return ModelUseLease(state, result)

    def install(self, descriptor: ModelDescriptor) -> Path:
        with self.mutation("install"):
            self._assert_not_in_use(descriptor.id)
            with self._journal("install") as journal:
                return self._install_unlocked(descriptor, journal)

    def _install_unlocked(self, descriptor: ModelDescriptor, journal: _MutationJournal) -> Path:
        self.registry.root.mkdir(parents=True, exist_ok=True)
        destination = self.registry.root / descriptor.id
        operation_id = uuid4().hex
        staging = self.registry.root / f".{descriptor.id}.installing.{operation_id}"
        backup = self.registry.root / f".{descriptor.id}.previous.{operation_id}"
        if staging.exists() or backup.exists():
            raise RuntimeError(f"Unique install workspace already exists for {descriptor.id}; retry the operation")
        journal.claim(staging)
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
        previous = None
        if destination.exists():
            os.replace(destination, backup)
            journal.claim(backup)
            previous = backup
        journal.record_swap(destination, previous)
        os.replace(staging, destination)
        journal.relinquish(staging)
        return destination

    def update(self, descriptor: ModelDescriptor) -> Path:
        """Install the catalog revision without risking the current installation."""
        with self.mutation("update"):
            self._assert_not_in_use(descriptor.id)
            with self._journal("update") as journal:
                return self._install_unlocked(descriptor, journal)

    def repair(self, descriptor: ModelDescriptor) -> Path:
        with self.mutation("repair"):
            self._assert_not_in_use(descriptor.id)
            was_active = self._active_unlocked(descriptor.kind) == descriptor
            with self._journal("repair") as journal:
                installed = self._install_unlocked(descriptor, journal)
                if was_active:
                    self._activate_unlocked(descriptor, journal)
                return installed

    def install_and_activate(self, descriptors: Iterable[ModelDescriptor]) -> tuple[ModelDescriptor, ...]:
        """Install and activate an automated model bundle in one transaction."""
        models = tuple(descriptors)
        with self.mutation("automated setup"):
            self._assert_not_in_use(*(descriptor.id for descriptor in models))
            with self._journal("automated setup") as journal:
                for descriptor in models:
                    self._install_unlocked(descriptor, journal)
                    self._activate_unlocked(descriptor, journal)
        return models

    def move(self, destination: Path, verifier=None) -> Path:
        """Move all installed model state after verifying a staged copy.

        The source remains untouched until the complete destination copy has
        passed verification, so an interrupted or invalid move is recoverable.
        """
        with self.mutation("move"):
            installed_ids = tuple(
                item.id for item in self.registry.catalog
                if self.registry.is_installed(item.id)
            )
            self._assert_not_in_use(*installed_ids)
            return self._move_unlocked(Path(destination), verifier)

    def _move_unlocked(self, destination: Path, verifier=None) -> Path:
        source = self.registry.root
        if source.resolve() == destination.resolve():
            return destination
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Destination model folder must be empty")
        staging = destination.with_name(f".{destination.name}.moving.{uuid4().hex}")
        if staging.exists():
            raise RuntimeError("Unique move workspace already exists; retry the operation")
        destination_was_empty = destination.exists()
        try:
            shutil.copytree(source, staging)
            verify_copy = verifier or self._verify_registry_copy
            if not verify_copy(staging):
                raise ValueError("Moved model copy failed integrity verification")
            if destination.exists():
                destination.rmdir()
            os.replace(staging, destination)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            if destination_was_empty and not destination.exists():
                destination.mkdir(parents=True)
            raise
        self.registry.root = destination
        try:
            shutil.rmtree(source)
        except Exception as exc:
            self._record_cleanup_warning("move", source, exc)
        return destination

    def _verify_registry_copy(self, root: Path) -> bool:
        installed = [item for item in self.registry.catalog if self.registry.is_installed(item.id)]
        return all(
            root.joinpath(item.id, ".complete").exists()
            and root.joinpath(item.id, "manifest.json").exists()
            for item in installed
        )

    def activate(self, descriptor: ModelDescriptor) -> ModelDescriptor:
        with self.mutation("activate"):
            with self._journal("activate") as journal:
                return self._activate_unlocked(descriptor, journal)

    def _activate_unlocked(self, descriptor: ModelDescriptor, journal: _MutationJournal) -> ModelDescriptor:
        if not self.registry.is_installed(descriptor.id):
            raise ValueError("Model must be installed before activation")
        active = self.registry.root / f"active-{descriptor.kind}.json"
        journal.capture_pointer(active)
        temporary = active.with_name(f".{active.name}.tmp.{uuid4().hex}")
        if temporary.exists():
            raise RuntimeError(f"Unique activation workspace already exists for {descriptor.kind}; retry the operation")
        journal.claim(temporary)
        temporary.write_text(json.dumps({"id": descriptor.id}), encoding="utf-8")
        os.replace(temporary, active)
        journal.relinquish(temporary)
        return descriptor

    def active(self, kind: str) -> ModelDescriptor | None:
        while True:
            root = self.registry.root.resolve()
            state = self._state_for_root(root)
            with state.lock:
                if self.registry.root.resolve() != root:
                    continue
                return self._active_at_root(kind, root)

    def _active_unlocked(self, kind: str) -> ModelDescriptor | None:
        return self._active_at_root(kind, self.registry.root.resolve())

    def _active_at_root(self, kind: str, root: Path) -> ModelDescriptor | None:
        path = Path(root) / f"active-{kind}.json"
        if not path.exists(): return None
        model_id = json.loads(path.read_text(encoding="utf-8"))["id"]
        return next((item for item in self.registry.catalog if item.id == model_id), None)

    def verify(self, descriptor: ModelDescriptor) -> bool:
        return self._verify_at_root(descriptor, self.registry.root.resolve())

    @staticmethod
    def _is_installed_at_root(model_id: str, root: Path) -> bool:
        return Path(root).joinpath(model_id, ".complete").exists()

    def _verify_at_root(self, descriptor: ModelDescriptor, registry_root: Path) -> bool:
        model_root = Path(registry_root) / descriptor.id
        manifest = model_root / "manifest.json"
        if not self._is_installed_at_root(descriptor.id, registry_root) or not manifest.exists():
            return False
        try:
            resolved_root = model_root.resolve(strict=True)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if payload.get("revision") != descriptor.revision:
                return False
            expected_files = payload.get("files", {})
            if not isinstance(expected_files, dict) or not expected_files:
                return False
            for relative, expected in expected_files.items():
                if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
                    return False
                candidate = resolved_root.joinpath(relative).resolve(strict=True)
                if not candidate.is_relative_to(resolved_root) or not candidate.is_file():
                    return False
                if _sha256(candidate) != expected:
                    return False
            return True
        except (OSError, ValueError, TypeError, RuntimeError, json.JSONDecodeError):
            return False

    def remove(self, descriptor: ModelDescriptor, force: bool = False) -> None:
        with self.mutation("remove"):
            self._assert_not_in_use(descriptor.id)
            self._remove_unlocked(descriptor, force=force)

    def _remove_unlocked(self, descriptor: ModelDescriptor, force: bool = False) -> None:
        active_model = self._active_unlocked(descriptor.kind)
        if active_model == descriptor and not force:
            raise ValueError("Cannot remove an active model without force")
        root = self.registry.root / descriptor.id
        active = self.registry.root / f"active-{descriptor.kind}.json"
        with self._journal("remove") as journal:
            if root.exists():
                removed = self.registry.root / f".{descriptor.id}.removed.{uuid4().hex}"
                if removed.exists():
                    raise RuntimeError(f"Unique removal workspace already exists for {descriptor.id}; retry the operation")
                os.replace(root, removed)
                journal.claim(removed)
                journal.record_swap(root, removed)
            if force and active_model == descriptor:
                journal.capture_pointer(active)
                active.unlink(missing_ok=True)

    def _assert_not_in_use(self, *model_ids: str) -> None:
        counts = self._state_for_root(self.registry.root).counts
        in_use = [model_id for model_id in model_ids if counts.get(model_id, 0)]
        if in_use:
            raise ValueError(f"Model is in use: {', '.join(in_use)}")
