from __future__ import annotations

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


@dataclass(frozen=True)
class PipelineResult:
    project_path: Path
    exports: list[Path]


class SubtitlePipeline:
    def __init__(self, media, transcriber, translator=None):
        self.media, self.transcriber, self.translator = media, transcriber, translator

    def run(self, request: PipelineRequest, progress=None, cancel=None) -> PipelineResult:
        if not request.source.is_file():
            raise FileNotFoundError(request.source)
        request.output_directory.mkdir(parents=True, exist_ok=True)
        self.media.probe(request.source)
        workspace = request.output_directory / ".quietcaption" / uuid4().hex
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
        project_path = request.output_directory / f"{request.source.stem}.qcp"
        ProjectStore(project_path).save(project)
        writers = {"srt": SrtWriter(), "vtt": VttWriter(), "txt": TextWriter()}
        exports = []
        for track in tracks:
            for extension in request.formats:
                if extension not in writers:
                    continue
                path = request.output_directory / f"{request.source.stem}.{track.language}.{extension}"
                path.write_text(writers[extension].render(track), encoding="utf-8")
                exports.append(path)
        return PipelineResult(project_path, exports)

