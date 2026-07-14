from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .domain import SubtitleSegment
from .hardware import ComputeConfig


@dataclass(frozen=True)
class TranscriptionOptions:
    beam_size: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.beam_size <= 20:
            raise ValueError("beam_size must be between 1 and 20")


class Transcriber(Protocol):
    def transcribe(self, path: Path, language: str = "auto", progress=None, cancel=None) -> tuple[str, list[SubtitleSegment]]: ...


class FasterWhisperTranscriber:
    def __init__(self, model: str, compute: ComputeConfig, options: TranscriptionOptions | None = None):
        self.model_name, self.compute = model, compute
        self.options = options or TranscriptionOptions()

    def transcribe(self, path: Path, language: str = "auto", progress=None, cancel=None) -> tuple[str, list[SubtitleSegment]]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Install the inference extra to use Faster-Whisper") from exc
        model = WhisperModel(self.model_name, device=self.compute.device, compute_type=self.compute.compute_type)
        segments, info = model.transcribe(str(path), language=None if language == "auto" else language, vad_filter=True, beam_size=self.options.beam_size)
        output = []
        for item in segments:
            if cancel and cancel.cancelled:
                raise InterruptedError("Transcription cancelled")
            output.append(SubtitleSegment(uuid4().hex, item.start, item.end, item.text.strip()))
            if progress:
                progress(item.end)
        return info.language, output
