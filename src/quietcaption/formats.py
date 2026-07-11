from __future__ import annotations

from datetime import timedelta

from .domain import SubtitleTrack


def format_timestamp(seconds: float, decimal: str = ",") -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal}{millis:03d}"


class SrtWriter:
    def render(self, track: SubtitleTrack) -> str:
        blocks = [f"{index}\n{format_timestamp(item.start)} --> {format_timestamp(item.end)}\n{item.text}" for index, item in enumerate(track.segments, 1)]
        return "\n\n".join(blocks) + ("\n" if blocks else "")


class VttWriter:
    def render(self, track: SubtitleTrack) -> str:
        blocks = [f"{format_timestamp(item.start, '.')} --> {format_timestamp(item.end, '.')}\n{item.text}" for item in track.segments]
        return "WEBVTT\n\n" + "\n\n".join(blocks) + ("\n" if blocks else "")


class TextWriter:
    def render(self, track: SubtitleTrack) -> str:
        return "\n".join(item.text for item in track.segments) + ("\n" if track.segments else "")

