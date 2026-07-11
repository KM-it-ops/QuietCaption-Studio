from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import subprocess


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    streams: list[dict]


class FFmpegService:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", runner=subprocess.run):
        self.ffmpeg, self.ffprobe, self.runner = ffmpeg, ffprobe, runner

    def probe(self, path: Path) -> MediaInfo:
        result = self.runner([self.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise MediaError(result.stderr.strip() or "FFprobe could not read the media")
        data = json.loads(result.stdout)
        return MediaInfo(float(data.get("format", {}).get("duration", 0)), data.get("streams", []))

    def extract_audio(self, source: Path, destination: Path, cancel=None) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self.runner([self.ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination)], capture_output=True, text=True)
        if result.returncode:
            raise MediaError(result.stderr.strip() or "FFmpeg could not extract audio")
        return destination

    def burn_subtitles(self, source: Path, subtitle: Path, destination: Path) -> Path:
        escaped = str(subtitle.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        result = self.runner([self.ffmpeg, "-y", "-i", str(source), "-vf", f"subtitles='{escaped}'", "-c:a", "copy", str(destination)], capture_output=True, text=True)
        if result.returncode:
            raise MediaError(result.stderr.strip() or "FFmpeg could not burn subtitles")
        return destination

