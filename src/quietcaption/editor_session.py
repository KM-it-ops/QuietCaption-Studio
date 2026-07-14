from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable

from .atomic_files import publish_text_batch
from .domain import Project, SubtitleTrack
from .formats import SrtWriter, TextWriter, VttWriter
from .projects import ProjectStore, project_json


SUPPORTED_FORMATS = ("srt", "vtt", "txt")
_WRITERS = {"srt": SrtWriter, "vtt": VttWriter, "txt": TextWriter}
_RECOVERY_VERSION = 1


class SaveConflictError(RuntimeError):
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        super().__init__(f"Project changed outside QuietCaption: {self.project_path}")


class EditorSession:
    def __init__(
        self,
        project: Project,
        project_path: Path,
        track_index: int,
        export_paths: Iterable[Path],
    ) -> None:
        self.project = project
        self.project_path = Path(project_path)
        self.track_index = track_index
        self.export_paths = self._paths_for_track(export_paths)
        self.selected_formats = set(self.export_paths)
        self.dirty = False
        self.last_warning: str | None = None
        self._base_fingerprint = self._fingerprint(self.project_path)

    @property
    def track(self) -> SubtitleTrack:
        return self.project.tracks[self.track_index]

    @property
    def recovery_path(self) -> Path:
        return self.project_path.with_suffix(self.project_path.suffix + ".recovery")

    def set_segment_text(self, row: int, text: str) -> None:
        segments = list(self.track.segments)
        if segments[row].text == text:
            return
        segments[row] = replace(segments[row], text=text)
        tracks = list(self.project.tracks)
        tracks[self.track_index] = replace(self.track, segments=segments)
        self.project = replace(self.project, tracks=tracks)
        self.dirty = True

    def save(self) -> None:
        self.last_warning = None
        recovery_path = self.recovery_path
        try:
            export_paths, retained = self._publish_to(
                self.project_path,
                self.export_paths,
                replace_existing=True,
                expected_fingerprint=self._base_fingerprint,
            )
        except Exception as exc:
            self._recover_after_failure(exc)
            raise
        self.export_paths = export_paths
        self.dirty = False
        self._base_fingerprint = self._fingerprint(self.project_path)
        self._warn_retained_backups(retained)
        self._remove_committed_recovery(recovery_path)

    def save_as(self, destination: Path) -> None:
        destination = Path(destination)
        if destination.suffix.lower() != ".qcp":
            destination = destination.with_suffix(".qcp")
        new_exports = {
            extension: destination.parent / f"{destination.stem}.{self.track.language}.{extension}"
            for extension in self.selected_formats
        }
        self.last_warning = None
        old_recovery = self.recovery_path
        try:
            new_exports, retained = self._publish_to(destination, new_exports, replace_existing=False)
        except Exception as exc:
            self._recover_after_failure(exc)
            raise
        self.project_path = destination
        self.export_paths = new_exports
        self.dirty = False
        self._base_fingerprint = self._fingerprint(self.project_path)
        self._warn_retained_backups(retained)
        self._remove_committed_recovery(old_recovery)

    def _publish_to(
        self,
        project_path: Path,
        export_paths: dict[str, Path],
        *,
        replace_existing: bool,
        expected_fingerprint: str | None = None,
    ) -> tuple[dict[str, Path], tuple[Path, ...]]:
        contents = {project_path: project_json(self.project)}
        effective_paths = dict(export_paths)
        for extension in self.selected_formats:
            destination = export_paths.get(extension)
            if destination is None:
                destination = project_path.parent / f"{project_path.stem}.{self.track.language}.{extension}"
            effective_paths[extension] = destination
            contents[destination] = _WRITERS[extension]().render(self.track)
        if expected_fingerprint is not None and self._current_fingerprint(project_path) != expected_fingerprint:
            raise SaveConflictError(project_path)
        publication = publish_text_batch(contents, replace_existing=replace_existing)
        return effective_paths, publication.retained_backups

    def _warn_retained_backups(self, retained: tuple[Path, ...]) -> None:
        if retained:
            paths = ", ".join(str(path) for path in retained)
            self.last_warning = f"Save committed, but backup files containing prior user data were retained at: {paths}"

    def write_recovery(self) -> None:
        envelope = {
            "recovery_version": _RECOVERY_VERSION,
            "base_fingerprint": self._base_fingerprint,
            "project": self.project.to_dict(),
        }
        publish_text_batch(
            {self.recovery_path: json.dumps(envelope, ensure_ascii=False, indent=2)},
            {self.recovery_path: self.recovery_path.with_suffix(self.recovery_path.suffix + ".tmp")},
        )

    def recovery_project(self) -> Project:
        project, _ = self._read_recovery()
        return project

    def discard_recovery(self) -> None:
        self.recovery_path.unlink(missing_ok=True)

    def _recover_after_failure(self, primary: Exception) -> None:
        try:
            self.write_recovery()
        except Exception as recovery_error:
            primary.recovery_error = recovery_error
            primary.add_note(f"Recovery could not be written: {recovery_error}")

    def _remove_committed_recovery(self, recovery_path: Path) -> None:
        try:
            recovery_path.unlink(missing_ok=True)
        except OSError as exc:
            warning = f"Save committed, but the old recovery snapshot could not be removed: {exc}"
            self.last_warning = f"{self.last_warning} {warning}" if self.last_warning else warning

    @classmethod
    def open(
        cls,
        project_path: Path,
        track_index: int,
        export_paths: Iterable[Path],
        recovery_decision: Callable[[Path], str],
    ) -> "EditorSession":
        project_path = Path(project_path)
        durable = ProjectStore(project_path).load()
        session = cls(durable, project_path, track_index, export_paths)
        if not session.recovery_path.exists():
            return session
        try:
            recovered, base_fingerprint = session._read_recovery()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            session.last_warning = (
                f"Corrupt recovery snapshot was retained at {session.recovery_path}. "
                f"The durable project was opened; move or delete the snapshot before retrying recovery. {exc}"
            )
            return session
        if base_fingerprint != session._base_fingerprint:
            try:
                session.discard_recovery()
            except OSError as exc:
                session.last_warning = f"The stale recovery snapshot could not be removed: {exc}"
            return session
        decision = recovery_decision(session.recovery_path)
        if decision == "recover":
            session.project = recovered
            session.dirty = True
        elif decision == "discard":
            session.discard_recovery()
        else:
            raise ValueError("Recovery decision must be 'recover' or 'discard'")
        return session

    def _read_recovery(self) -> tuple[Project, str | None]:
        data = json.loads(self.recovery_path.read_text(encoding="utf-8"))
        if data.get("recovery_version") == _RECOVERY_VERSION and "project" in data:
            return Project.from_dict(data["project"]), data.get("base_fingerprint")
        return Project.from_dict(data), None

    @staticmethod
    def _fingerprint(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _current_fingerprint(path: Path) -> str | None:
        try:
            return EditorSession._fingerprint(path)
        except FileNotFoundError:
            return None

    def _paths_for_track(self, paths: Iterable[Path]) -> dict[str, Path]:
        selected = {}
        for candidate in map(Path, paths):
            extension = candidate.suffix.lower().lstrip(".")
            expected = f"{self.project_path.stem}.{self.track.language}.{extension}"
            if extension in SUPPORTED_FORMATS and candidate.name == expected:
                selected[extension] = candidate
        return selected
