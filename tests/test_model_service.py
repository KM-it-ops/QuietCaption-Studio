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
