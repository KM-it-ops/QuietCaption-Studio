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


def test_export_partial_temp_is_removed_when_write_raises(tmp_path, monkeypatch):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    real_write_text = Path.write_text

    def partial_write_then_fail(path, content, *args, **kwargs):
        if ".srt." in path.name and path.name.endswith(".tmp"):
            real_write_text(path, "partial", encoding="utf-8")
            raise OSError("disk write failed")
        return real_write_text(path, content, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", partial_write_then_fail)

    with pytest.raises(OSError, match="disk write failed"):
        SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "replace"))

    assert not list(output.glob("*.tmp"))


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


def test_reservation_acquire_survives_another_reservation_release(tmp_path, monkeypatch):
    output = tmp_path / "out"
    output.mkdir()
    first = pipeline_module._NamespaceReservation(output, "first")
    second = pipeline_module._NamespaceReservation(output, "second")
    assert first.acquire()
    real_open = pipeline_module.os.open

    def release_first_before_second_open(path, flags):
        if Path(path) == second.path:
            first.release()
        return real_open(path, flags)

    monkeypatch.setattr(pipeline_module.os, "open", release_first_before_second_open)

    assert second.acquire()
    second.release()
    assert not first.path.exists()
    assert not second.path.exists()


def test_reservation_is_released_after_failure(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"

    with pytest.raises(RuntimeError, match="transcription failed"):
        SubtitlePipeline(RecordingMedia(), FailingTranscriber()).run(request(source, output, "increment"))

    result = SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "increment"))
    assert result.project_path == output / "clip.qcp"
    assert not (output / ".quietcaption-reservations").exists()


def test_reservation_is_released_after_application_cancellation(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    cancel = type("Token", (), {"cancelled": True})()

    class CancelAwareTranscriber:
        def transcribe(self, path, language="auto", progress=None, cancel=None):
            assert cancel.cancelled
            raise InterruptedError("Transcription cancelled")

    with pytest.raises(InterruptedError, match="cancelled"):
        SubtitlePipeline(RecordingMedia(), CancelAwareTranscriber()).run(
            request(source, output, "increment"), cancel=cancel
        )

    result = SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "increment"))
    assert result.project_path == output / "clip.qcp"
    assert not list(output.glob(".quietcaption-reservation-*.lock"))


def test_invalid_collision_policy_is_rejected_before_processing(tmp_path):
    source = source_file(tmp_path)
    media = RecordingMedia()

    with pytest.raises(ValueError, match="collision policy"):
        SubtitlePipeline(media, Transcriber()).run(request(source, tmp_path / "out", "rename"))

    assert media.calls == []


@pytest.mark.parametrize("collision_kind", ["project", "export"])
@pytest.mark.parametrize("policy", ["ask", "increment"])
def test_late_collision_never_overwrites_external_output(tmp_path, monkeypatch, collision_kind, policy):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    real_publish = pipeline_module.publish_text_batch
    raced = None

    def race_then_publish(contents, *args, **kwargs):
        nonlocal raced
        raced = next(path for path in contents if (path.suffix == ".qcp") == (collision_kind == "project"))
        raced.write_text("external racer", encoding="utf-8")
        return real_publish(contents, *args, **kwargs)

    monkeypatch.setattr(pipeline_module, "publish_text_batch", race_then_publish)

    with pytest.raises(pipeline_module.CollisionError) as caught:
        SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, policy))

    assert raced in caught.value.conflicts
    assert raced.read_text(encoding="utf-8") == "external racer"
    assert not any(path.exists() for path in (output / "clip.qcp", output / "clip.en.srt") if path != raced)


def test_cancellation_during_translation_publishes_nothing(tmp_path):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    cancel = type("Token", (), {"cancelled": False})()

    class CancellingTranslator:
        def translate(self, texts, source_language, target_language, cancel=None):
            cancel.cancelled = True
            return ["translated"]

    req = PipelineRequest(source, output, ["es"], ["srt"], collision_policy="increment")
    with pytest.raises(InterruptedError, match="cancelled"):
        SubtitlePipeline(RecordingMedia(), Transcriber(), CancellingTranslator()).run(req, cancel=cancel)

    assert not list(output.glob("*.qcp"))
    assert not list(output.glob("*.srt"))


def test_cancellation_immediately_before_publication_publishes_nothing(tmp_path, monkeypatch):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    cancel = type("Token", (), {"cancelled": False})()
    real_render = pipeline_module.SrtWriter.render

    def render_then_cancel(writer, track):
        rendered = real_render(writer, track)
        cancel.cancelled = True
        return rendered

    monkeypatch.setattr(pipeline_module.SrtWriter, "render", render_then_cancel)

    with pytest.raises(InterruptedError, match="cancelled"):
        SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "increment"), cancel=cancel)

    assert not list(output.glob("*.qcp"))
    assert not list(output.glob("*.srt"))


@pytest.mark.parametrize("processing_succeeds", [False, True])
def test_reservation_release_failure_is_non_masking_and_namespace_is_reusable(
    tmp_path, monkeypatch, processing_succeeds
):
    source = source_file(tmp_path)
    output = tmp_path / "out"
    real_unlink = Path.unlink

    def deny_lock_release(path, *args, **kwargs):
        if path.name.startswith(".quietcaption-reservation-"):
            raise PermissionError("sharing violation")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_lock_release)
    pipeline = SubtitlePipeline(RecordingMedia(), Transcriber() if processing_succeeds else FailingTranscriber())
    if processing_succeeds:
        result = pipeline.run(request(source, output, "increment"))
        assert result.project_path == output / "clip.qcp"
        assert result.warnings and "reservation" in result.warnings[0].lower()
    else:
        with pytest.raises(RuntimeError, match="transcription failed") as caught:
            pipeline.run(request(source, output, "increment"))
        assert "sharing violation" in str(caught.value.cleanup_warning)

    monkeypatch.setattr(Path, "unlink", real_unlink)
    if processing_succeeds:
        (output / "clip.qcp").unlink()
        (output / "clip.en.srt").unlink()
    reused = SubtitlePipeline(RecordingMedia(), Transcriber()).run(request(source, output, "increment"))
    assert reused.project_path == output / "clip.qcp"
