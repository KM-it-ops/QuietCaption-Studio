from __future__ import annotations

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
        self.export_paths = self._save_to(self.project_path, self.export_paths)

    def save_as(self, destination: Path) -> None:
        destination = Path(destination)
        if destination.suffix.lower() != ".qcp":
            destination = destination.with_suffix(".qcp")
        new_exports = {
            extension: destination.parent / f"{destination.stem}.{self.track.language}.{extension}"
            for extension in self.selected_formats
        }
        conflicts = [path for path in (destination, *new_exports.values()) if path.exists()]
        if conflicts:
            raise FileExistsError(f"Save As destination already exists: {conflicts[0]}")
        old_recovery = self.recovery_path
        new_exports = self._save_to(destination, new_exports)
        old_recovery.unlink(missing_ok=True)
        self.project_path = destination
        self.export_paths = new_exports

    def _save_to(self, project_path: Path, export_paths: dict[str, Path]) -> dict[str, Path]:
        try:
            contents = {project_path: project_json(self.project)}
            effective_paths = dict(export_paths)
            for extension in self.selected_formats:
                destination = export_paths.get(extension)
                if destination is None:
                    destination = project_path.parent / f"{project_path.stem}.{self.track.language}.{extension}"
                effective_paths[extension] = destination
                contents[destination] = _WRITERS[extension]().render(self.track)
            publish_text_batch(contents)
        except Exception:
            self.write_recovery()
            raise
        self.dirty = False
        self.recovery_path.unlink(missing_ok=True)
        return effective_paths

    def write_recovery(self) -> None:
        ProjectStore(self.recovery_path).save(self.project)

    def discard_recovery(self) -> None:
        self.recovery_path.unlink(missing_ok=True)

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
