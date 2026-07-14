from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .atomic_files import publish_text_batch
from .domain import Project, SubtitleSegment, SubtitleTrack
from .formats import SrtWriter, TextWriter, VttWriter
from .projects import project_json


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
    warnings: tuple[str, ...] = ()


class CollisionError(RuntimeError):
    def __init__(self, conflicts: tuple[Path, ...]):
        self.conflicts = conflicts
        paths = ", ".join(str(path) for path in conflicts)
        super().__init__(f"Output namespace already exists: {paths}")


class _NamespaceReservation:
    _active_tokens: set[str] = set()

    def __init__(self, output_directory: Path, base_name: str):
        normalized_name = os.path.normcase(base_name)
        digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
        self.path = output_directory / f".quietcaption-reservation-{digest}.lock"
        self.acquired = False
        self.token = uuid4().hex

    def acquire(self) -> bool:
        for attempt in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if attempt == 0 and self._recover_orphaned_lock():
                    continue
                return False
            try:
                payload = json.dumps({"pid": os.getpid(), "token": self.token}).encode("utf-8")
                os.write(descriptor, payload)
            finally:
                os.close(descriptor)
            self.acquired = True
            self._active_tokens.add(self.token)
            return True
        return False

    def release(self) -> str | None:
        if self.acquired:
            error = self._unlink_with_retries()
            self._active_tokens.discard(self.token)
            self.acquired = False
            if error is not None:
                return f"Output reservation cleanup failed at {self.path}: {error}"
        return None

    def _recover_orphaned_lock(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            token = payload.get("token")
            pid = int(payload.get("pid"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False
        if token in self._active_tokens:
            return False
        if pid != os.getpid() and self._pid_running(pid):
            return False
        return self._unlink_with_retries() is None

    def _unlink_with_retries(self) -> OSError | None:
        for attempt in range(3):
            try:
                self.path.unlink(missing_ok=True)
                return None
            except OSError as exc:
                if attempt == 2:
                    return exc
                time.sleep(0.01)
        return None

    @staticmethod
    def _pid_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


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
        result = None
        primary = None
        try:
            self._check_cancel(cancel)
            self.media.probe(request.source)
            self._check_cancel(cancel)
            workspace.mkdir(parents=True, exist_ok=True)
            audio = self.media.extract_audio(request.source, workspace / "audio.wav", cancel)
            self._check_cancel(cancel)
            language, segments = self.transcriber.transcribe(audio, request.source_language, progress, cancel)
            self._check_cancel(cancel)
            source_track = SubtitleTrack(language, segments, "Source")
            tracks = [source_track]
            for target in request.target_languages:
                if target == language:
                    continue
                if self.translator is None:
                    raise ValueError(f"No offline translation model is configured for {language} → {target}")
                self._check_cancel(cancel)
                texts = self._translate([item.text for item in segments], language, target, cancel)
                self._check_cancel(cancel)
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
                    self._check_cancel(cancel)
                    path = request.output_directory / f"{selection.base_name}.{track.language}.{extension}"
                    rendered_exports.append((path, writers[extension].render(track)))
                    self._check_cancel(cancel)

            contents = {project_path: project_json(project)}
            contents.update(rendered_exports)
            self._check_cancel(cancel)
            try:
                publication = publish_text_batch(
                    contents,
                    replace_existing=request.collision_policy == "replace",
                )
            except FileExistsError as exc:
                conflicts = self._namespace_conflicts(request.output_directory, selection.base_name)
                collision = CollisionError(conflicts or tuple(contents))
                if hasattr(exc, "rollback_failures"):
                    collision.rollback_failures = exc.rollback_failures
                raise collision from exc
            exports = [path for path, _ in rendered_exports]
            retained_warning = ()
            if publication.retained_backups:
                paths = ", ".join(str(path) for path in publication.retained_backups)
                retained_warning = (f"Publication committed, but backup files containing user data were retained at: {paths}",)
            result = PipelineResult(project_path, exports, warnings=retained_warning)
        except Exception as exc:
            primary = exc
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
        cleanup_warning = selection.reservation.release()
        if primary is not None:
            if cleanup_warning:
                primary.cleanup_warning = OSError(cleanup_warning)
                primary.add_note(cleanup_warning)
            raise primary
        if cleanup_warning:
            result = PipelineResult(
                result.project_path,
                result.exports,
                result.skipped,
                (*result.warnings, cleanup_warning),
            )
        return result

    def _translate(self, texts, source_language, target_language, cancel):
        parameters = inspect.signature(self.translator.translate).parameters
        if "cancel" in parameters:
            return self.translator.translate(texts, source_language, target_language, cancel=cancel)
        return self.translator.translate(texts, source_language, target_language)

    @staticmethod
    def _check_cancel(cancel) -> None:
        if cancel is not None and cancel.cancelled:
            raise InterruptedError("Job cancelled")

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
