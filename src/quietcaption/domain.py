from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    segment_id: str
    message: str


@dataclass(frozen=True)
class SubtitleSegment:
    id: str
    start: float
    end: float
    text: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("A segment must have non-negative, increasing timestamps")

    def split(self, at: float, character: int) -> tuple[SubtitleSegment, SubtitleSegment]:
        if not self.start < at < self.end or not 0 < character < len(self.text):
            raise ValueError("Split point must be inside the segment")
        left_text = self.text[:character].rstrip()
        right_text = self.text[character:].lstrip()
        return (
            SubtitleSegment(self.id, self.start, at, left_text),
            SubtitleSegment(uuid4().hex, at, self.end, right_text),
        )

    def merge(self, other: SubtitleSegment) -> SubtitleSegment:
        return SubtitleSegment(self.id, min(self.start, other.start), max(self.end, other.end), f"{self.text.rstrip()} {other.text.lstrip()}".strip())


@dataclass(frozen=True)
class SubtitleTrack:
    language: str
    segments: list[SubtitleSegment] = field(default_factory=list)
    name: str = "Source"

    def validate(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        ordered = sorted(self.segments, key=lambda item: item.start)
        for index, segment in enumerate(ordered):
            if not segment.text.strip():
                issues.append(ValidationIssue("empty", segment.id, "Subtitle text is empty"))
            if index and segment.start < ordered[index - 1].end:
                issues.append(ValidationIssue("overlap", segment.id, "Subtitle overlaps the previous segment"))
            duration = segment.end - segment.start
            if duration and len(segment.text) / duration > 25:
                issues.append(ValidationIssue("reading_speed", segment.id, "Subtitle may be too fast to read"))
        return issues


@dataclass(frozen=True)
class Project:
    id: str
    media_path: str
    tracks: list[SubtitleTrack]
    schema_version: int = 1

    @classmethod
    def new(cls, media_path: str | Path, source_track: SubtitleTrack) -> Project:
        return cls(uuid4().hex, str(media_path), [source_track])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        tracks = [SubtitleTrack(track["language"], [SubtitleSegment(**item) for item in track["segments"]], track.get("name", "Source")) for track in data["tracks"]]
        return cls(data["id"], data["media_path"], tracks, data.get("schema_version", 1))

