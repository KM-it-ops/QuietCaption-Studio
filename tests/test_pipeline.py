from pathlib import Path

from quietcaption.domain import SubtitleSegment
from quietcaption.pipeline import PipelineRequest, SubtitlePipeline


class FakeMedia:
    def probe(self, path):
        return type("Info", (), {"duration": 3.0})()
    def extract_audio(self, source, destination, cancel=None):
        destination.write_bytes(b"audio")
        return destination


class FakeTranscriber:
    def transcribe(self, path, language="auto", progress=None, cancel=None):
        return "en", [SubtitleSegment("a", 0, 2, "hello world")]


class FakeTranslator:
    def translate(self, texts, source_language, target_language):
        return ["hola mundo"]


def test_pipeline_creates_editable_project_and_exports(tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    pipeline = SubtitlePipeline(FakeMedia(), FakeTranscriber(), FakeTranslator())
    result = pipeline.run(PipelineRequest(source, tmp_path / "out", ["es"], ["srt", "vtt", "txt"]))
    assert result.project_path.exists()
    assert {path.suffix for path in result.exports} == {".srt", ".vtt", ".txt"}
    assert "hola mundo" in (tmp_path / "out" / "clip.es.srt").read_text(encoding="utf-8")

