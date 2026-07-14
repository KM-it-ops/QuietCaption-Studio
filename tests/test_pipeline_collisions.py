from pathlib import Path

import pytest

import quietcaption.pipeline as pipeline_module
from quietcaption.domain import SubtitleSegment
from quietcaption.pipeline import PipelineRequest, SubtitlePipeline


class RecordingMedia:
    def __init__(self):
        self.calls = []

    def probe(self, path):
        self.calls.append("probe")
        return type("Info", (), {"duration": 3.0})()

    def extract_audio(self, source, destination, cancel=None):
        self.calls.append("extract")
        destination.write_bytes(b"audio")
        return destination


class Transcriber:
    def transcribe(self, path, language="auto", progress=None, cancel=None):
        return "en", [SubtitleSegment("a", 0, 2, "new text")]


class FailingTranscriber:
    def transcribe(self, path, language="auto", progress=None, cancel=None):
        raise RuntimeError("transcription failed")


def request(source: Path, output: Path, policy: str, formats=None):
    return PipelineRequest(source, output, [], formats or ["srt"], collision_policy=policy)


def source_file(tmp_path: Path) -> Path:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    return source


def test_ask_reports_all_conflicts_before_media_processing(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    project = output / "clip.qcp"
    export = output / "clip.en.srt"
    project.write_text("old project", encoding="utf-8")
    export.write_text("old subtitle", encoding="utf-8")
    media = RecordingMedia()

    with pytest.raises(pipeline_module.CollisionError) as caught:
        SubtitlePipeline(media, Transcriber()).run(request(source, output, "ask"))

    assert caught.value.conflicts == (project, export)
    assert media.calls == []


def test_existing_export_without_project_is_a_collision(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    export = output / "clip.en.vtt"
    export.write_text("old subtitle", encoding="utf-8")

    with pytest.raises(pipeline_module.CollisionError) as caught:
        SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "ask"))

    assert caught.value.conflicts == (export,)


def test_existing_export_collision_is_case_insensitive_on_windows(tmp_path):
    source = tmp_path / "Clip.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "out"
    output.mkdir()
    export = output / "clip.en.srt"
    export.write_text("old subtitle", encoding="utf-8")

    with pytest.raises(pipeline_module.CollisionError) as caught:
        SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "ask"))

    assert caught.value.conflicts == (export,)


def test_skip_stops_early_without_returning_an_existing_project(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    (output / "clip.qcp").write_text("old project", encoding="utf-8")
    media = RecordingMedia()

    result = SubtitlePipeline(media, Transcriber()).run(request(source, output, "skip"))

    assert result.skipped is True
    assert result.project_path is None
    assert result.exports == []
    assert media.calls == []


def test_increment_uses_one_incremented_base_for_project_and_exports(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    (output / "clip.en.srt").write_text("old subtitle", encoding="utf-8")

    result = SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "increment"))

    assert result.project_path == output / "clip (2).qcp"
    assert result.exports == [output / "clip (2).en.srt"]
    assert (output / "clip.en.srt").read_text(encoding="utf-8") == "old subtitle"


def test_replace_preserves_existing_files_when_rendering_fails(tmp_path, monkeypatch):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    project = output / "clip.qcp"
    export = output / "clip.en.srt"
    project.write_text("old project", encoding="utf-8")
    export.write_text("old subtitle", encoding="utf-8")
    monkeypatch.setattr(pipeline_module.SrtWriter, "render", lambda self, track: (_ for _ in ()).throw(RuntimeError("render failed")))

    with pytest.raises(RuntimeError, match="render failed"):
        SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "replace"))

    assert project.read_text(encoding="utf-8") == "old project"
    assert export.read_text(encoding="utf-8") == "old subtitle"


def test_replace_atomically_publishes_exports_after_success(tmp_path, monkeypatch):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    export = output / "clip.en.srt"
    export.write_text("old subtitle", encoding="utf-8")
    replacements = []
    real_replace = pipeline_module.os.replace

    def record_replace(staged, destination):
        replacements.append((Path(staged), Path(destination)))
        real_replace(staged, destination)

    monkeypatch.setattr(pipeline_module.os, "replace", record_replace)

    result = SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "replace"))

    assert result.skipped is False
    assert "new text" in export.read_text(encoding="utf-8")
    export_replacement = next(item for item in replacements if item[1] == export)
    assert export_replacement[0].parent == export.parent
    assert export_replacement[0] != export
    assert not export_replacement[0].exists()


def test_reservation_prevents_nested_job_from_claiming_same_namespace(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    nested_results = []

    class NestedMedia(RecordingMedia):
        def probe(self, path):
            nested_results.append(
                SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "increment"))
            )
            return super().probe(path)

    first = SubtitlePipeline(NestedMedia(), Transcriber()).run(request(source, output, "increment"))

    assert first.project_path == output / "clip.qcp"
    assert nested_results[0].project_path == output / "clip (2).qcp"


def test_reservation_is_released_after_failure(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"

    with pytest.raises(RuntimeError, match="transcription failed"):
        SubtitlePipeline(RecordingMedia(), FailingTranscriber()).run(request(source, output, "increment"))

    result = SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "increment"))
    assert result.project_path == output / "clip.qcp"
    assert not (output / ".quietcaption-reservations").exists()


def test_invalid_collision_policy_is_rejected_before_processing(tmp_path):
    source = source_file(tmp_path)
    media = RecordingMedia()

    with pytest.raises(ValueError, match="collision policy"):
        SubtitlePipeline(media, Transcriber()).run(request(source, tmp_path / "out", "rename"))

    assert media.calls == []
