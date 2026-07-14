import gc
import hashlib
import json
import multiprocessing
import os
import threading
import time
import weakref
from pathlib import Path

import pytest

from quietcaption.model_operation_lock import ModelOperationLock
from quietcaption.model_service import ModelOperationBusy, ModelRuntime, ModelService
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
            with pytest.raises(ModelOperationBusy, match=operation):
                mutate()
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
    assert not tuple(root.glob(f".{descriptor.id}.installing.*"))


def _hold_os_file_lock(path, payload, aged, ready, release):
    path = Path(path)
    path.write_bytes(payload)
    if aged:
        old = time.time() - 60
        os.utime(path, (old, old))
    handle = path.open("r+b")
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    ready.set()
    release.wait(5)
    if os.name == "nt":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


@pytest.mark.parametrize(
    ("payload", "aged"),
    [
        (b'{"pid":99999999,"token":"stale-owner","created_at":0}', False),
        (b"aged malformed owner metadata", True),
    ],
)
def test_model_operation_lock_never_unlinks_a_live_os_locked_owner(tmp_path, payload, aged):
    root = tmp_path / "models"
    root.mkdir()
    lock_path = tmp_path / ".models.model-operation.lock"
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    owner = context.Process(target=_hold_os_file_lock, args=(lock_path, payload, aged, ready, release))
    owner.start()
    try:
        assert ready.wait(5), "lock owner did not reach the deterministic barrier"
        contender = ModelOperationLock(root)
        assert contender.acquire() is False
    finally:
        release.set()
        owner.join(5)
        if owner.is_alive():
            owner.terminate()
            owner.join(5)

    assert owner.exitcode == 0
    assert lock_path.read_bytes() == payload
    available = ModelOperationLock(root)
    assert available.acquire() is True
    available.release()
    assert lock_path.read_bytes() == payload


@pytest.mark.parametrize(
    ("payload", "aged"),
    [
        (b'{"pid":99999999,"token":"stale-owner","created_at":0}', False),
        (b"aged malformed owner metadata", True),
    ],
)
def test_unlocked_stale_lockfile_is_reused_without_read_then_unlink_recovery(tmp_path, payload, aged):
    root = tmp_path / "models"
    root.mkdir()
    lock_path = tmp_path / ".models.model-operation.lock"
    lock_path.write_bytes(payload)
    if aged:
        old = time.time() - 60
        os.utime(lock_path, (old, old))

    operation_lock = ModelOperationLock(root)
    assert operation_lock.acquire() is True
    operation_lock.release()

    assert lock_path.read_bytes() == payload


@pytest.mark.parametrize("operation", ["remove", "update", "repair", "move"])
def test_runtime_lease_blocks_same_root_mutation_across_service_instances(tmp_path, operation):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    root = tmp_path / "models"
    fetches = []

    def fetch(repo_id, revision, local_dir):
        fetches.append((repo_id, revision))
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"model")

    service_a = ModelService(ModelRegistry(root, [descriptor]), fetcher=fetch)
    service_a.install(descriptor)
    service_a.activate(descriptor)
    lease = service_a.acquire_runtime(("transcription",))
    service_b = ModelService(ModelRegistry(root / ".", [descriptor]), fetcher=fetch)
    destination = tmp_path / "moved-models"
    fetches.clear()

    def mutate():
        if operation == "remove":
            return service_b.remove(descriptor, force=True)
        if operation == "update":
            return service_b.update(descriptor)
        if operation == "repair":
            return service_b.repair(descriptor)
        return service_b.move(destination)

    before = (_tree_snapshot(root), _tree_snapshot(destination))
    with pytest.raises(ValueError, match="in use"):
        mutate()
    assert (_tree_snapshot(root), _tree_snapshot(destination)) == before
    assert fetches == []

    lease.release()
    lease.release()
    mutate()


def test_runtime_lease_counts_are_isolated_between_distinct_registry_roots(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"model")

    service_a = ModelService(ModelRegistry(tmp_path / "models-a", [descriptor]), fetcher=fetch)
    service_b = ModelService(ModelRegistry(tmp_path / "models-b", [descriptor]), fetcher=fetch)
    for service in (service_a, service_b):
        service.install(descriptor)
        service.activate(descriptor)

    lease = service_a.acquire_runtime(("transcription",))
    service_b.remove(descriptor, force=True)
    lease.release()

    assert not service_b.registry.root.joinpath(descriptor.id).exists()


def test_runtime_acquisition_retries_on_destination_root_after_concurrent_move(tmp_path, monkeypatch):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"model")

    source = tmp_path / "models"
    destination = tmp_path / "moved-models"
    moved_again = tmp_path / "moved-again"
    service = ModelService(ModelRegistry(source, [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.activate(descriptor)
    verifier_entered = threading.Event()
    allow_move = threading.Event()
    acquisition_captured_state = threading.Event()
    move_errors = []
    acquisition_errors = []
    acquired_leases = []

    def blocking_verifier(staging):
        assert staging.joinpath(descriptor.id, "model.bin").read_bytes() == b"model"
        verifier_entered.set()
        if not allow_move.wait(5):
            raise TimeoutError("test did not release move verifier")
        return True

    real_state_for_root = service._state_for_root
    acquisition_thread = None

    def tracking_state_for_root(root):
        state = real_state_for_root(root)
        if threading.current_thread() is acquisition_thread:
            acquisition_captured_state.set()
        return state

    monkeypatch.setattr(service, "_state_for_root", tracking_state_for_root)
    move_thread = threading.Thread(
        target=lambda: _capture_error(move_errors, lambda: service.move(destination, verifier=blocking_verifier))
    )

    def acquire():
        try:
            acquired_leases.append(service.acquire_runtime(("transcription",)))
        except Exception as exc:
            acquisition_errors.append(exc)

    acquisition_thread = threading.Thread(target=acquire)
    move_thread.start()
    try:
        assert verifier_entered.wait(5), "move did not reach verifier barrier"
        acquisition_thread.start()
        assert acquisition_captured_state.wait(5), "acquisition did not capture the old-root state"
    finally:
        allow_move.set()
        move_thread.join(5)
        acquisition_thread.join(5)

    assert not move_thread.is_alive()
    assert not acquisition_thread.is_alive()
    assert move_errors == []
    assert acquisition_errors == []
    assert len(acquired_leases) == 1
    lease = acquired_leases[0]
    assert lease.runtimes == (ModelRuntime(descriptor, destination / descriptor.id),)
    assert service.registry.root == destination
    assert service.verify(descriptor)

    contender_fetches = []

    def contender_fetch(repo_id, revision, local_dir):
        contender_fetches.append((repo_id, revision))
        fetch(repo_id, revision, local_dir)

    contender = ModelService(ModelRegistry(destination, [descriptor]), fetcher=contender_fetch)
    before = (_tree_snapshot(destination), _tree_snapshot(moved_again))
    blocked_operations = (
        lambda: contender.remove(descriptor, force=True),
        lambda: contender.update(descriptor),
        lambda: contender.move(moved_again),
    )
    for mutate in blocked_operations:
        with pytest.raises(ValueError, match="in use"):
            mutate()
        assert (_tree_snapshot(destination), _tree_snapshot(moved_again)) == before
    assert contender_fetches == []

    lease.release()
    contender.update(descriptor)
    assert contender_fetches == [("owner/demo", "abc")]


def test_normalized_registry_use_state_is_collectible_after_service_release(tmp_path):
    import quietcaption.model_service as module

    root = (tmp_path / "collectible-models").resolve()
    service = ModelService(ModelRegistry(root, []), fetcher=lambda *_: None)
    service.active("transcription")
    state = module._registry_states[root]
    state_reference = weakref.ref(state)

    del state
    del service
    gc.collect()

    assert state_reference() is None
    assert root not in module._registry_states


def test_model_operation_lock_has_no_stale_recovery_configuration(tmp_path):
    import quietcaption.model_operation_lock as module

    assert not hasattr(module, "DEFAULT_STALE_AFTER_SECONDS")
    with pytest.raises(TypeError):
        ModelOperationLock(tmp_path / "models", stale_after=1)


def test_move_rolls_back_when_destination_verification_fails(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        (local_dir / "model.bin").write_bytes(b"healthy")

    registry = ModelRegistry(tmp_path / "models", [descriptor])
    service = ModelService(registry, fetcher=fetch)
    service.install(descriptor)
    destination = tmp_path / "moved-models"
    source = registry.root
    before = _tree_snapshot(source)

    try:
        service.move(destination, verifier=lambda _: False)
    except ValueError:
        pass
    else:
        raise AssertionError("A failed destination verification must abort the move")

    assert registry.root == source
    assert _tree_snapshot(source) == before
    assert registry.root.joinpath("demo", ".complete").exists()
    assert not destination.joinpath("demo").exists()
    assert service.cleanup_warnings == ()


@pytest.mark.parametrize("partial_cleanup", [False, True])
def test_move_source_cleanup_failure_keeps_promoted_destination_authoritative(tmp_path, monkeypatch, partial_cleanup):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"healthy")

    source = tmp_path / "models"
    destination = tmp_path / "moved-models"
    service = ModelService(ModelRegistry(source, [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.activate(descriptor)
    before_source = _tree_snapshot(source)
    import quietcaption.model_service as module

    real_rmtree = module.shutil.rmtree

    def fail_source_cleanup(path, *args, **kwargs):
        if Path(path) == source:
            if partial_cleanup:
                source.joinpath(descriptor.id, "model.bin").unlink()
            raise OSError("old source cleanup denied")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(module.shutil, "rmtree", fail_source_cleanup)

    assert service.move(destination) == destination
    assert service.registry.root == destination
    assert service.verify(descriptor)
    assert destination.joinpath(descriptor.id, "model.bin").read_bytes() == b"healthy"
    if partial_cleanup:
        assert _tree_snapshot(source) != before_source
    else:
        assert _tree_snapshot(source) == before_source
    assert source in service.pending_cleanup_paths
    assert any("move" in warning and "old source cleanup denied" in warning for warning in service.cleanup_warnings)


def test_forced_remove_pointer_failure_restores_model_and_pointer_byte_for_byte(tmp_path, monkeypatch):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"healthy")

    root = tmp_path / "models"
    service = ModelService(ModelRegistry(root, [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.activate(descriptor)
    before = _tree_snapshot(root)
    pointer = root / "active-transcription.json"
    real_unlink = Path.unlink

    def fail_pointer_unlink(path, *args, **kwargs):
        if path == pointer:
            raise OSError("pointer unlink denied")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_pointer_unlink)

    with pytest.raises(OSError, match="pointer unlink denied"):
        service.remove(descriptor, force=True)

    assert _tree_snapshot(root) == before
    assert service.active("transcription") == descriptor


def test_forced_remove_cleanup_failure_is_nonfatal_after_logical_commit(tmp_path, monkeypatch):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"healthy")

    root = tmp_path / "models"
    service = ModelService(ModelRegistry(root, [descriptor]), fetcher=fetch)
    service.install(descriptor)
    service.activate(descriptor)
    foreign = root / ".demo.removed"
    foreign.mkdir()
    foreign.joinpath("sentinel.bin").write_bytes(b"foreign")
    import quietcaption.model_service as module

    real_remove_path = module._remove_path
    injected = []

    def fail_owned_removed_cleanup(path):
        if path.name.startswith(".demo.removed."):
            injected.append(path)
            raise OSError("removed backup cleanup denied")
        return real_remove_path(path)

    monkeypatch.setattr(module, "_remove_path", fail_owned_removed_cleanup)

    service.remove(descriptor, force=True)

    assert injected
    assert not root.joinpath(descriptor.id).exists()
    assert not root.joinpath("active-transcription.json").exists()
    assert foreign.joinpath("sentinel.bin").read_bytes() == b"foreign"
    assert injected[0] in service.pending_cleanup_paths
    assert injected[0].exists()
    assert any("remove" in warning and "removed backup cleanup denied" in warning for warning in service.cleanup_warnings)


@pytest.mark.parametrize("operation", ["update", "repair"])
def test_committed_install_cleanup_failure_returns_new_valid_state_with_warning(tmp_path, monkeypatch, operation):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    root = tmp_path / "models"

    def initial_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"original")

    service = ModelService(ModelRegistry(root, [descriptor]), fetcher=initial_fetch)
    service.install(descriptor)
    service.activate(descriptor)
    foreign = root / ".demo.previous"
    foreign.mkdir()
    foreign.joinpath("sentinel.bin").write_bytes(b"foreign")

    def replacement_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"replacement")

    service.fetcher = replacement_fetch
    import quietcaption.model_service as module

    real_remove_path = module._remove_path
    injected = []

    def fail_owned_backup_cleanup(path):
        if path.name.startswith(".demo.previous."):
            injected.append(path)
            raise OSError("install backup cleanup denied")
        return real_remove_path(path)

    monkeypatch.setattr(module, "_remove_path", fail_owned_backup_cleanup)

    installed = getattr(service, operation)(descriptor)

    assert installed == root / descriptor.id
    assert installed.joinpath("model.bin").read_bytes() == b"replacement"
    assert service.active("transcription") == descriptor
    assert service.verify(descriptor)
    assert foreign.joinpath("sentinel.bin").read_bytes() == b"foreign"
    assert injected[0] in service.pending_cleanup_paths
    assert injected[0].exists()
    assert any(operation in warning and "install backup cleanup denied" in warning for warning in service.cleanup_warnings)


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
        if Path(source).name.startswith(".demo.installing") and Path(target).name == "demo":
            raise OSError("simulated disk failure")
        return real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_new_install)
    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)

    with pytest.raises(OSError, match="simulated disk failure"):
        service.install(descriptor)

    assert destination.joinpath("model.bin").read_bytes() == b"working-v1"


@pytest.mark.parametrize("failure_point", ["second_install", "second_activation"])
def test_automated_setup_rolls_back_every_model_and_active_pointer(tmp_path, monkeypatch, failure_point):
    old_transcription = ModelDescriptor("old-transcription", "transcription", {"en"}, 1, "old/transcription", "0" * 64, revision="old")
    old_translation = ModelDescriptor("old-translation", "translation", {"en"}, 1, "old/translation", "1" * 64, revision="old")
    new_transcription = ModelDescriptor("new-transcription", "transcription", {"en"}, 1, "new/transcription", "2" * 64, revision="new")
    new_translation = ModelDescriptor("new-translation", "translation", {"en"}, 1, "new/translation", "3" * 64, revision="new")
    catalog = [old_transcription, old_translation, new_transcription, new_translation]
    root = tmp_path / "models"

    def initial_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(repo_id.encode("ascii"))

    service = ModelService(ModelRegistry(root, catalog), fetcher=initial_fetch)
    for descriptor in (old_transcription, old_translation):
        service.install(descriptor)
        service.activate(descriptor)
    before = _tree_snapshot(root)

    def bundle_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(f"replacement:{repo_id}".encode("ascii"))
        if failure_point == "second_install" and repo_id == new_translation.url:
            raise RuntimeError("second installation failed")

    service.fetcher = bundle_fetch
    if failure_point == "second_activation":
        import quietcaption.model_service as module

        real_replace = module.os.replace
        activation_failed = False

        def fail_translation_activation(source, target):
            nonlocal activation_failed
            if Path(target).name == "active-translation.json" and not activation_failed:
                activation_failed = True
                raise OSError("second activation failed")
            return real_replace(source, target)

        monkeypatch.setattr(module.os, "replace", fail_translation_activation)

    with pytest.raises((OSError, RuntimeError), match="second .* failed"):
        service.install_and_activate((new_transcription, new_translation))

    assert _tree_snapshot(root) == before
    assert service.active("transcription") == old_transcription
    assert service.active("translation") == old_translation


def test_repair_activation_failure_restores_previous_bytes_and_pointer(tmp_path, monkeypatch):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    root = tmp_path / "models"

    def initial_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"original")

    service = ModelService(ModelRegistry(root, [descriptor]), fetcher=initial_fetch)
    service.install(descriptor)
    service.activate(descriptor)
    before = _tree_snapshot(root)

    def replacement_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"replacement")

    service.fetcher = replacement_fetch
    import quietcaption.model_service as module

    real_replace = module.os.replace
    activation_failed = False

    def fail_activation(source, target):
        nonlocal activation_failed
        if Path(target).name == "active-transcription.json" and not activation_failed:
            activation_failed = True
            raise OSError("activation failed")
        return real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_activation)

    with pytest.raises(OSError, match="activation failed"):
        service.repair(descriptor)

    assert _tree_snapshot(root) == before
    assert service.active("transcription") == descriptor


def test_install_preserves_foreign_fixed_name_artifacts_and_cleans_unique_failure_paths(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")
    root = tmp_path / "models"
    foreign_staging = root / ".demo.installing"
    foreign_backup = root / ".demo.previous"
    foreign_staging.mkdir(parents=True)
    foreign_backup.mkdir()
    foreign_staging.joinpath("sentinel.bin").write_bytes(b"foreign staging")
    foreign_backup.joinpath("sentinel.bin").write_bytes(b"foreign backup")

    def failed_fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("partial.bin").write_bytes(b"owned partial")
        raise RuntimeError("injected fetch failure")

    service = ModelService(ModelRegistry(root, [descriptor]), fetcher=failed_fetch)
    with pytest.raises(RuntimeError, match="injected fetch failure"):
        service.install(descriptor)

    assert foreign_staging.joinpath("sentinel.bin").read_bytes() == b"foreign staging"
    assert foreign_backup.joinpath("sentinel.bin").read_bytes() == b"foreign backup"
    assert not tuple(root.glob(".demo.installing.*"))
    assert not tuple(root.glob(".demo.previous.*"))


def test_move_preserves_foreign_fixed_name_artifact_and_cleans_unique_failure_path(tmp_path):
    descriptor = ModelDescriptor("demo", "transcription", {"en"}, 1, "owner/demo", "0" * 64, revision="abc")

    def fetch(repo_id, revision, local_dir):
        local_dir.mkdir(parents=True)
        local_dir.joinpath("model.bin").write_bytes(b"model")

    service = ModelService(ModelRegistry(tmp_path / "models", [descriptor]), fetcher=fetch)
    service.install(descriptor)
    destination = tmp_path / "moved-models"
    foreign_staging = tmp_path / ".moved-models.moving"
    foreign_staging.mkdir()
    foreign_staging.joinpath("sentinel.bin").write_bytes(b"foreign move")

    with pytest.raises(ValueError, match="integrity"):
        service.move(destination, verifier=lambda _: False)

    assert foreign_staging.joinpath("sentinel.bin").read_bytes() == b"foreign move"
    assert not tuple(tmp_path.glob(".moved-models.moving.*"))
    assert service.registry.root.joinpath(descriptor.id).is_dir()


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
