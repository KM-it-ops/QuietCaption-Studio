from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable

from .atomic_files import publish_text_batch
from .domain import Project, SubtitleTrack
from .formats import SrtWriter, TextWriter, VttWriter
from .projects import ProjectStore, project_json


SUPPORTED_FORMATS = ("srt", "vtt", "txt")
_WRITERS = {"srt": SrtWriter, "vtt": VttWriter, "txt": TextWriter}


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
            export_paths = self._publish_to(self.project_path, self.export_paths, replace_existing=True)
        except Exception as exc:
            self._recover_after_failure(exc)
            raise
        self.export_paths = export_paths
        self.dirty = False
        self._remove_committed_recovery(recovery_path, self.project_path)

    def save_as(self, destination: Path) -> None:
        destination = Path(destination)
        if destination.suffix.lower() != ".qcp":
            destination = destination.with_suffix(".qcp")
        new_exports = {
            extension: destination.parent / f"{destination.stem}.{self.track.language}.{extension}"
            for extension in self.selected_formats
        }
        self.last_warning = None
        old_project_path = self.project_path
        old_recovery = self.recovery_path
        try:
            new_exports = self._publish_to(destination, new_exports, replace_existing=False)
        except Exception as exc:
            self._recover_after_failure(exc)
            raise
        self.project_path = destination
        self.export_paths = new_exports
        self.dirty = False
        self._remove_committed_recovery(old_recovery, old_project_path)

    def _publish_to(
        self,
        project_path: Path,
        export_paths: dict[str, Path],
        *,
        replace_existing: bool,
    ) -> dict[str, Path]:
        contents = {project_path: project_json(self.project)}
        effective_paths = dict(export_paths)
        for extension in self.selected_formats:
            destination = export_paths.get(extension)
            if destination is None:
                destination = project_path.parent / f"{project_path.stem}.{self.track.language}.{extension}"
            effective_paths[extension] = destination
            contents[destination] = _WRITERS[extension]().render(self.track)
        publish_text_batch(contents, replace_existing=replace_existing)
        return effective_paths

    def write_recovery(self) -> None:
        ProjectStore(self.recovery_path).save(self.project)
        if self.project_path.exists():
            durable_time = self.project_path.stat().st_mtime_ns
            recovery_time = self.recovery_path.stat().st_mtime_ns
            if recovery_time <= durable_time:
                fresh_time = durable_time + 1_000_000_000
                os.utime(self.recovery_path, ns=(fresh_time, fresh_time))

    def discard_recovery(self) -> None:
        self.recovery_path.unlink(missing_ok=True)

    def _recover_after_failure(self, primary: Exception) -> None:
        try:
            self.write_recovery()
        except Exception as recovery_error:
            primary.recovery_error = recovery_error
            primary.add_note(f"Recovery could not be written: {recovery_error}")

    def _remove_committed_recovery(self, recovery_path: Path, durable_path: Path) -> None:
        try:
            recovery_path.unlink(missing_ok=True)
        except OSError as exc:
            self.last_warning = f"Save committed, but the old recovery snapshot could not be removed: {exc}"
            try:
                durable_time = durable_path.stat().st_mtime_ns
                os.utime(recovery_path, ns=(durable_time, durable_time))
            except OSError:
                pass

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
        if session.recovery_path.stat().st_mtime_ns <= project_path.stat().st_mtime_ns:
            try:
                session.discard_recovery()
            except OSError:
                pass
            return session
        decision = recovery_decision(session.recovery_path)
        if decision == "recover":
            session.project = ProjectStore(session.recovery_path).load()
            session.dirty = True
        elif decision == "discard":
            session.discard_recovery()
        else:
            raise ValueError("Recovery decision must be 'recover' or 'discard'")
        return session

    def _paths_for_track(self, paths: Iterable[Path]) -> dict[str, Path]:
        selected = {}
        for candidate in map(Path, paths):
            extension = candidate.suffix.lower().lstrip(".")
            expected = f"{self.project_path.stem}.{self.track.language}.{extension}"
            if extension in SUPPORTED_FORMATS and candidate.name == expected:
                selected[extension] = candidate
        return selected
