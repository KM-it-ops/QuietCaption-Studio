from pathlib import Path

import pytest

import quietcaption.atomic_files as atomic_module
from quietcaption.atomic_files import publish_text_batch


def test_no_replace_publication_never_overwrites_a_racing_file(tmp_path, monkeypatch):
    destination = tmp_path / "new.qcp"
    real_link = atomic_module.os.link

    def race_before_link(source, target):
        Path(target).write_text("racer", encoding="utf-8")
        return real_link(source, target)

    monkeypatch.setattr(atomic_module.os, "link", race_before_link)

    with pytest.raises(FileExistsError):
        publish_text_batch({destination: "ours"}, replace_existing=False)

    assert destination.read_text(encoding="utf-8") == "racer"


def test_rollback_attempts_every_restore_and_retains_failed_backup(tmp_path, monkeypatch):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    third = tmp_path / "third.txt"
    for path in (first, second, third):
        path.write_text(f"old {path.stem}", encoding="utf-8")
    real_replace = atomic_module.os.replace
    restored = []

    def fail_publish_and_one_restore(source, destination):
        source = Path(source)
        destination = Path(destination)
        if destination == third and source.suffix == ".tmp":
            raise OSError("publish failed")
        if destination in {first, second} and source.suffix == ".bak":
            restored.append(destination)
            if destination == second:
                raise OSError("restore failed")
        return real_replace(source, destination)

    monkeypatch.setattr(atomic_module.os, "replace", fail_publish_and_one_restore)

    with pytest.raises(OSError, match="publish failed"):
        publish_text_batch({first: "new first", second: "new second", third: "new third"})

    assert restored == [second, first]
    assert first.read_text(encoding="utf-8") == "old first"
    assert second.read_text(encoding="utf-8") == "new second"
    assert list(tmp_path.glob(f".{second.name}.*.bak"))


def test_cleanup_failure_does_not_turn_committed_success_into_failure(tmp_path, monkeypatch):
    destination = tmp_path / "project.qcp"
    destination.write_text("old", encoding="utf-8")
    real_unlink = Path.unlink

    def fail_cleanup(path, *args, **kwargs):
        if path.suffix in {".tmp", ".bak"}:
            raise PermissionError("cleanup denied")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_cleanup)

    publish_text_batch({destination: "committed"})

    assert destination.read_text(encoding="utf-8") == "committed"


def test_committed_publication_reports_exact_retained_backup_path(tmp_path, monkeypatch):
    destination = tmp_path / "project.qcp"
    destination.write_text("old user data", encoding="utf-8")
    real_unlink = Path.unlink

    def retain_backup(path, *args, **kwargs):
        if path.suffix == ".bak":
            raise PermissionError("backup is locked")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", retain_backup)

    result = publish_text_batch({destination: "committed"})

    assert destination.read_text(encoding="utf-8") == "committed"
    assert len(result.retained_backups) == 1
    retained = result.retained_backups[0]
    assert retained.exists()
    assert retained.read_text(encoding="utf-8") == "old user data"


def test_cleanup_failure_does_not_mask_primary_staging_failure(tmp_path, monkeypatch):
    destination = tmp_path / "project.qcp"
    real_write = Path.write_text
    real_unlink = Path.unlink

    def fail_write(path, content, *args, **kwargs):
        if path.suffix == ".tmp":
            raise OSError("primary staging failure")
        return real_write(path, content, *args, **kwargs)

    def fail_cleanup(path, *args, **kwargs):
        if path.suffix == ".tmp":
            raise PermissionError("cleanup denied")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)

    with pytest.raises(OSError, match="primary staging failure"):
        publish_text_batch({destination: "new"})


def test_no_replace_rollback_reports_partial_destination_that_cannot_be_removed(tmp_path, monkeypatch):
    project = tmp_path / "renamed.qcp"
    export = tmp_path / "renamed.en.srt"
    export.write_text("collision", encoding="utf-8")
    real_unlink = Path.unlink

    def deny_project_rollback(path, *args, **kwargs):
        if path == project:
            raise PermissionError("project is locked")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_project_rollback)

    with pytest.raises(FileExistsError) as caught:
        publish_text_batch({project: "project", export: "subtitle"}, replace_existing=False)

    assert project.exists()
    assert [failure.path for failure in caught.value.rollback_failures] == [project]
    assert "project is locked" in str(caught.value.rollback_failures[0].error)
