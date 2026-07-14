from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import wave


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


class PyAVMediaService:
    """Bundled local decoder used when external FFmpeg tools are unavailable."""

    @staticmethod
    def _av():
        try:
            import av
        except ImportError as exc:
            raise MediaError("The packaged media decoder is unavailable; repair the application installation") from exc
        return av

    def probe(self, path: Path) -> MediaInfo:
        av = self._av()
        try:
            with av.open(str(path)) as container:
                duration = float(container.duration * av.time_base) if container.duration is not None else 0.0
                streams = [{"type": stream.type, "codec": stream.codec_context.name} for stream in container.streams]
                return MediaInfo(duration, streams)
        except Exception as exc:
            raise MediaError(f"The bundled decoder could not read this media: {exc}") from exc

    def extract_audio(self, source: Path, destination: Path, cancel=None) -> Path:
        av = self._av()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with av.open(str(source)) as container, wave.open(str(destination), "wb") as output:
                if not container.streams.audio:
                    raise MediaError("This media does not contain an audio stream")
                output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in container.decode(audio=0):
                    if cancel and cancel.cancelled:
                        raise InterruptedError("Job cancelled")
                    for converted in resampler.resample(frame):
                        output.writeframes(bytes(converted.planes[0]))
                for converted in resampler.resample(None):
                    output.writeframes(bytes(converted.planes[0]))
            return destination
        except (MediaError, InterruptedError):
            destination.unlink(missing_ok=True)
            raise
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise MediaError(f"The bundled decoder could not extract audio: {exc}") from exc

    def burn_subtitles(self, source: Path, subtitle: Path, destination: Path) -> Path:
        raise MediaError("Burn-in export requires an external FFmpeg installation; subtitle file export remains available")


def best_available_media_service(which=shutil.which):
    if which("ffmpeg") and which("ffprobe"):
        return FFmpegService()
    return PyAVMediaService()

    def burn_subtitles(self, source: Path, subtitle: Path, destination: Path) -> Path:
        escaped = str(subtitle.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        result = self.runner([self.ffmpeg, "-y", "-i", str(source), "-vf", f"subtitles='{escaped}'", "-c:a", "copy", str(destination)], capture_output=True, text=True)
        if result.returncode:
            raise MediaError(result.stderr.strip() or "FFmpeg could not burn subtitles")
        return destination
