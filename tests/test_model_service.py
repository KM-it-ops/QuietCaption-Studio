import hashlib
import json
import os
import threading
import time
from pathlib import Path

import pytest

from quietcaption.model_service import ModelRuntime, ModelService
from quietcaption.models import ModelDescriptor, ModelRegistry


def test_install_pins_revision_and_activates_atomically(tmp_path):
    calls = []
    source = tmp_path / "snapshot"; source.mkdir(); (source / "model.bin").write_bytes(b"model")
    def fetch(repo_id, revision, local_dir):
        calls.append((repo_id, revision)); local_dir.mkdir(parents=True); (local_dir / "model.bin").write_bytes(b"model")
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc123")
    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    installed = service.install(descriptor)
    assert calls == [("owner/demo", "abc123")]
    assert installed.joinpath(".complete").exists()
    assert service.activate(descriptor).id == "demo"
    assert service.active("transcription").id == "demo"


def test_remove_refuses_active_model_without_force(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    def fetch(repo_id, revision, local_dir): local_dir.mkdir(parents=True); (local_dir / "model.bin").write_bytes(b"x")
    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    service.install(descriptor); service.activate(descriptor)
    try:
        service.remove(descriptor)
    except ValueError as exc:
        assert "active" in str(exc)
    else:
        raise AssertionError("Active model removal should require force")


def test_failed_update_restores_previous_install(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="v2")
    destination = tmp_path / "models" / "demo"
    destination.mkdir(parents=True)
    (destination / "model.bin").write_bytes(b"working-v1")
    (destination / ".complete").write_text("v1", encoding="ascii")

    def broken_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        (local_dir / "model.bin").write_bytes(b"broken-v2")
        raise RuntimeError("network interrupted")

    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=broken_fetch)
    try:
        service.update(descriptor)
    except RuntimeError:
        pass
    else:
        raise AssertionError("A failed update must report its failure")

    assert (destination / "model.bin").read_bytes() == b"working-v1"
    assert not (tmp_path / "models" / ".demo.installing").exists()


def test_repair_reinstalls_model_and_preserves_active_role(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        (local_dir / "model.bin").write_bytes(b"healthy")

    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.activate(descriptor)
    (tmp_path / "models" / "demo" / "manifest.json").unlink()

    service.repair(descriptor)

    assert service.verify(descriptor)
    assert service.active("transcription") == descriptor


def _tree_snapshot(root):
    if not root.exists():
        return None
    return {
        path.relative_to(root).as_posix(): ("dir" if path.is_dir() else path.read_bytes())
        for path in sorted(root.rglob("*"))
    }


def test_registry_mutations_fail_busy_before_changing_filesystem(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    root = tmp_path / "models"

    def initial_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"working")

    initial = ModelService(ModelRegistry(root, [descriptor]), fetcher=initial_fetch)
    initial.install(descriptor)
    initial.activate(descriptor)

    entered = threading.Event()
    release = threading.Event()

    def blocking_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"pending")
        entered.set()
        if not release.wait(3):
            raise TimeoutError("test did not release blocking fetcher")

    holder = ModelService(ModelRegistry(root, [descriptor]), fetcher=blocking_fetch)
    contender = ModelService(ModelRegistry(root / ".", [descriptor]), fetcher=lambda *_: (_ for _ in ()).throw(AssertionError("busy contender fetched")))
    holder_errors = []
    thread = threading.Thread(target=lambda: _capture_error(holder_errors, lambda: holder.install(descriptor)))
    thread.start()
    assert entered.wait(3), "blocking fetcher was not reached"

    destination = tmp_path / "moved-models"
    operations = {
        "update": lambda: contender.update(descriptor),
        "repair": lambda: contender.repair(descriptor),
        "remove": lambda: contender.remove(descriptor, force=True),
        "activate": lambda: contender.activate(descriptor),
        "move": lambda: contender.move(destination),
    }
    try:
        before = (_tree_snapshot(root), _tree_snapshot(destination))
        for operation, mutate in operations.items():
            with pytest.raises(RuntimeError, match=operation) as busy:
                mutate()
            assert type(busy.value).__name__ == "ModelOperationBusy"
            assert (_tree_snapshot(root), _tree_snapshot(destination)) == before
    finally:
        release.set()
        thread.join(3)

    assert not thread.is_alive()
    assert holder_errors == []


def _capture_error(errors, operation):
    try:
        operation()
    except Exception as exc:
        errors.append(exc)


def test_failed_repair_is_one_transaction_and_preserves_bytes_and_active_pointer(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    root = tmp_path / "models"

    def initial_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"working")

    service = ModelService(ModelRegistry(root, [descriptor]), fetcher=initial_fetch)
    service.install(descriptor)
    service.activate(descriptor)
    before_model = _tree_snapshot(root / descriptor.id)
    before_pointer = root.joinpath("active-transcription.json").read_bytes()

    def failed_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"partial")
        raise RuntimeError("injected repair failure")

    service.fetcher = failed_fetch
    with pytest.raises(RuntimeError, match="injected repair failure"):
        service.repair(descriptor)

    assert _tree_snapshot(root / descriptor.id) == before_model
    assert root.joinpath("active-transcription.json").read_bytes() == before_pointer
    assert not root.joinpath(f".{descriptor.id}.installing").exists()


def test_model_mutation_recovers_an_aged_malformed_lock(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    root = tmp_path / "models"
    root.mkdir()
    lock_path = tmp_path / ".models.model-operation.lock"
    lock_path.write_text("interrupted metadata", encoding="utf-8")
    old = time.time() - 60
    os.utime(lock_path, (old, old))

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"working")

    service = ModelService(ModelRegistry(root, [descriptor]), fetcher=fetch)

    assert service.install(descriptor).joinpath(".complete").is_file()
    assert not lock_path.exists()


def test_move_rolls_back_when_destination_verification_fails(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        (local_dir / "model.bin").write_bytes(b"healthy")

    registry = ModelRegistry(tmp_path / "models", [descriptor])
    service = ModelService(registry, fetcher=fetch)
    service.install(descriptor)
    destination = tmp_path / "moved-models"

    try:
        service.move(destination, verifier=lambda _: False)
    except ValueError:
        pass
    else:
        raise AssertionError("A failed destination verification must abort the move")

    assert registry.root.joinpath("demo", ".complete").exists()
    assert not destination.joinpath("demo").exists()


def test_verify_detects_changed_model_files(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        (local_dir / "model.bin").write_bytes(b"healthy")

    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    installed = service.install(descriptor)
    assert service.verify(descriptor)

    installed.joinpath("model.bin").write_bytes(b"tampered")

    assert not service.verify(descriptor)


def test_install_swap_failure_restores_previous_model(tmp_path, monkeypatch):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="v2")
    destination = tmp_path / "models" / "demo"
    destination.mkdir(parents=True)
    (destination / "model.bin").write_bytes(b"working-v1")
    (destination / ".complete").write_text("v1", encoding="ascii")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        (local_dir / "model.bin").write_bytes(b"healthy-v2")

    import quietcaption.model_service as module

    real_replace = module.os.replace

    def fail_new_install(source, target):
        if Path(source).name == ".demo.installing" and Path(target).name == "demo":
            raise OSError("simulated disk failure")
        return real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_new_install)
    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)

    with pytest.raises(OSError, match="simulated disk failure"):
        service.install(descriptor)

    assert destination.joinpath("model.bin").read_bytes() == b"working-v1"


def test_acquire_runtime_requires_a_complete_verified_active_installation(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    registry = ModelRegistry(tmp_path / "models", [descriptor])
    service = ModelService(registry, fetcher=lambda *_: (_ for _ in ()).throw(AssertionError("fetch must not run")))

    with pytest.raises(ValueError, match="active transcription model"):
        service.acquire_runtime(("transcription",))

    registry.root.mkdir(parents=True)
    registry.root.joinpath("active-transcription.json").write_text('{"id":"demo"}', encoding="utf-8")
    with pytest.raises(ValueError, match="installed"):
        service.acquire_runtime(("transcription",))

    model_path = registry.root / descriptor.id
    model_path.mkdir()
    model_path.joinpath(".complete").write_text(descriptor.revision, encoding="ascii")
    with pytest.raises(ValueError, match="manifest"):
        service.acquire_runtime(("transcription",))

    model_path.joinpath("manifest.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        service.acquire_runtime(("transcription",))

    model_path.joinpath("model.bin").write_bytes(b"model")
    model_path.joinpath("manifest.json").write_text(
        '{"id":"demo","kind":"transcription","revision":"abc","repo_id":"owner/demo","files":{"model.bin":"9372c470eeadd5ecd9c3c74c2b3cb633f8e2f2fad799250a0f70d652b6b825e4"}}',
        encoding="utf-8",
    )
    model_path.joinpath(".complete").write_text("wrong-revision", encoding="ascii")
    with pytest.raises(ValueError, match="installation marker"):
        service.acquire_runtime(("transcription",))
    model_path.joinpath(".complete").write_text(descriptor.revision, encoding="ascii")

    lease = service.acquire_runtime(("transcription",))

    assert lease.runtimes == (ModelRuntime(descriptor, model_path),)
    lease.release()


def test_acquire_runtime_rejects_pointer_to_the_wrong_model_kind(tmp_path):
    descriptor = ModelDescriptor("translator", "translation", {"en"}, 1, "owner/translator", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"model")

    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.registry.root.joinpath("active-transcription.json").write_text('{"id":"translator"}', encoding="utf-8")

    with pytest.raises(ValueError, match="pointer"):
        service.acquire_runtime(("transcription",))


@pytest.mark.parametrize("operation", ["remove", "update", "repair", "move"])
def test_model_mutations_are_blocked_by_live_runtime_lease(tmp_path, operation):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    fetches = []

    def fetch(repo_id, revision, local_dir):
        fetches.append((repo_id, revision))
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"model")

    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.activate(descriptor)
    fetches.clear()
    lease = service.acquire_runtime(("transcription",))
    destination = tmp_path / "moved-models"

    def mutate():
        if operation == "remove":
            return service.remove(descriptor, force=True)
        if operation == "update":
            return service.update(descriptor)
        if operation == "repair":
            return service.repair(descriptor)
        return service.move(destination)

    with pytest.raises(ValueError, match="in use"):
        mutate()

    assert service.registry.root.joinpath(descriptor.id).is_dir()
    assert not destination.exists()
    assert fetches == []

    lease.release()
    lease.release()
    mutate()

    if operation == "remove":
        assert not service.registry.root.joinpath(descriptor.id).exists()
    elif operation == "move":
        assert destination.joinpath(descriptor.id).is_dir()
    else:
        assert fetches == [("owner/demo", "abc")]


def _service_with_manifest_entry(tmp_path, relative, target_bytes=b"outside"):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"model")

    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.activate(descriptor)
    manifest = service.registry.root / descriptor.id / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "id": descriptor.id,
                "kind": descriptor.kind,
                "revision": descriptor.revision,
                "repo_id": descriptor.url,
                "files": {relative: hashlib.sha256(target_bytes).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    return service, descriptor


def test_runtime_manifest_rejects_absolute_file_entry(tmp_path):
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    service, descriptor = _service_with_manifest_entry(tmp_path, str(outside))

    assert not service.verify(descriptor)
    with pytest.raises(ValueError, match="manifest"):
        service.acquire_runtime(("transcription",))


def test_runtime_manifest_rejects_parent_traversal_entry(tmp_path):
    outside = tmp_path / "models" / "outside.bin"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"outside")
    service, descriptor = _service_with_manifest_entry(tmp_path, "../outside.bin")

    assert not service.verify(descriptor)
    with pytest.raises(ValueError, match="manifest"):
        service.acquire_runtime(("transcription",))


def test_runtime_manifest_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    model_link = tmp_path / "models" / "demo" / "link.bin"
    service, descriptor = _service_with_manifest_entry(tmp_path, "link.bin")
    try:
        model_link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Windows symlink creation is unavailable: {exc}")

    assert not service.verify(descriptor)
    with pytest.raises(ValueError, match="manifest"):
        service.acquire_runtime(("transcription",))
