from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .domain import Project, SubtitleSegment, SubtitleTrack
from .formats import SrtWriter, TextWriter, VttWriter
from .projects import ProjectStore


@dataclass(frozen=True)
class PipelineRequest:
    source: Path
    output_directory: Path
    target_languages: list[str]
    formats: list[str]
    source_language: str = "auto"
    collision_policy: str = "ask"


@dataclass(frozen=True)
class PipelineResult:
    project_path: Path | None
    exports: list[Path]
    skipped: bool = False


class CollisionError(RuntimeError):
    def __init__(self, conflicts: tuple[Path, ...]):
        self.conflicts = conflicts
        paths = ", ".join(str(path) for path in conflicts)
        super().__init__(f"Output namespace already exists: {paths}")


class _NamespaceReservation:
    def __init__(self, output_directory: Path, base_name: str):
        normalized_name = os.path.normcase(base_name)
        digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
        self.path = output_directory / f".quietcaption-reservation-{digest}.lock"
        self.acquired = False

    def acquire(self) -> bool:
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        os.close(descriptor)
        self.acquired = True
        return True

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False


@dataclass(frozen=True)
class _SelectedNamespace:
    base_name: str
    reservation: _NamespaceReservation


class SubtitlePipeline:
    def __init__(self, media, transcriber, translator=None):
        self.media, self.transcriber, self.translator = media, transcriber, translator

    def run(self, request: PipelineRequest, progress=None, cancel=None) -> PipelineResult:
        if not request.source.is_file():
            raise FileNotFoundError(request.source)
        if request.collision_policy not in {"ask", "increment", "replace", "skip"}:
            raise ValueError(f"Unsupported collision policy: {request.collision_policy}")
        request.output_directory.mkdir(parents=True, exist_ok=True)
        selection = self._select_namespace(request)
        if selection is None:
            return PipelineResult(None, [], skipped=True)
        workspace = request.output_directory / ".quietcaption" / uuid4().hex
        staged_exports: list[Path] = []
        try:
            self.media.probe(request.source)
            workspace.mkdir(parents=True, exist_ok=True)
            audio = self.media.extract_audio(request.source, workspace / "audio.wav", cancel)
            language, segments = self.transcriber.transcribe(audio, request.source_language, progress, cancel)
            source_track = SubtitleTrack(language, segments, "Source")
            tracks = [source_track]
            for target in request.target_languages:
                if target == language:
                    continue
                if self.translator is None:
                    raise ValueError(f"No offline translation model is configured for {language} → {target}")
                texts = self.translator.translate([item.text for item in segments], language, target)
                translated = [SubtitleSegment(item.id, item.start, item.end, text) for item, text in zip(segments, texts, strict=True)]
                tracks.append(SubtitleTrack(target, translated, f"Translation ({target})"))

            project = Project(uuid4().hex, str(request.source), tracks)
            project_path = request.output_directory / f"{selection.base_name}.qcp"
            writers = {"srt": SrtWriter(), "vtt": VttWriter(), "txt": TextWriter()}
            rendered_exports: list[tuple[Path, str]] = []
            for track in tracks:
                for extension in request.formats:
                    if extension not in writers:
                        continue
                    path = request.output_directory / f"{selection.base_name}.{track.language}.{extension}"
                    rendered_exports.append((path, writers[extension].render(track)))

            for path, content in rendered_exports:
                temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
                staged_exports.append(temporary)
                temporary.write_text(content, encoding="utf-8")
            ProjectStore(project_path).save(project)
            exports = []
            for temporary, (path, _) in zip(staged_exports, rendered_exports, strict=True):
                os.replace(temporary, path)
                exports.append(path)
            return PipelineResult(project_path, exports)
        finally:
            for temporary in staged_exports:
                temporary.unlink(missing_ok=True)
            shutil.rmtree(workspace, ignore_errors=True)
            selection.reservation.release()

    def _select_namespace(self, request: PipelineRequest) -> _SelectedNamespace | None:
        base_name = request.source.stem
        index = 1
        while True:
            conflicts = self._namespace_conflicts(request.output_directory, base_name)
            if conflicts and request.collision_policy == "ask":
                raise CollisionError(conflicts)
            if conflicts and request.collision_policy == "skip":
                return None
            if conflicts and request.collision_policy == "increment":
                index += 1
                base_name = f"{request.source.stem} ({index})"
                continue

            reservation = _NamespaceReservation(request.output_directory, base_name)
            if reservation.acquire():
                return _SelectedNamespace(base_name, reservation)
            reservation.release()
            if request.collision_policy == "increment":
                index += 1
                base_name = f"{request.source.stem} ({index})"
                continue
            if request.collision_policy == "skip":
                return None
            reserved_path = request.output_directory / f"{base_name}.qcp"
            raise CollisionError(conflicts or (reserved_path,))

    @staticmethod
    def _namespace_conflicts(output_directory: Path, base_name: str) -> tuple[Path, ...]:
        project_path = output_directory / f"{base_name}.qcp"
        conflicts = [project_path] if project_path.exists() else []
        export_prefix = f"{base_name}.".casefold()
        exports = sorted(
            path for path in output_directory.iterdir()
            if path.is_file()
            and path.name.casefold().startswith(export_prefix)
            and path.suffix.lower() in {".srt", ".vtt", ".txt"}
        )
        conflicts.extend(exports)
        return tuple(conflicts)
