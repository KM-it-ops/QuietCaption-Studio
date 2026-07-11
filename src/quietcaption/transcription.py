from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .domain import SubtitleSegment
from .hardware import ComputeConfig


class Transcriber(Protocol):
    def transcribe(self, path: Path, language: str = "auto", progress=None, cancel=None) -> tuple[str, list[SubtitleSegment]]: ...


class FasterWhisperTranscriber:
    def __init__(self, model: str, compute: ComputeConfig):
        self.model_name, self.compute = model, compute

    def transcribe(self, path: Path, language: str = "auto", progress=None, cancel=None) -> tuple[str, list[SubtitleSegment]]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Install the inference extra to use Faster-Whisper") from exc
        model = WhisperModel(self.model_name, device=self.compute.device, compute_type=self.compute.compute_type)
        segments, info = model.transcribe(str(path), language=None if language == "auto" else language, vad_filter=True, beam_size=5)
        output = []
        for item in segments:
            if cancel and cancel.cancelled:
                raise InterruptedError("Transcription cancelled")
            output.append(SubtitleSegment(uuid4().hex, item.start, item.end, item.text.strip()))
            if progress:
                progress(item.end)
        return info.language, output

