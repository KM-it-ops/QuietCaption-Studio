from pathlib import Path

import pytest

from quietcaption.model_service import ModelService
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
