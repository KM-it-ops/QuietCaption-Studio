from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import shutil

from .hardware import HardwareProfile, detect_hardware


class FindingStatus(str, Enum):
    READY = "ready"
    ACTION = "action"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class HardwareFinding:
    status: FindingStatus
    summary: str
    detail: str
    action: str = ""


@dataclass(frozen=True)
class SystemScan:
    hardware: HardwareProfile
    free_disk_gb: float
    ffmpeg_ready: bool
    findings: tuple[HardwareFinding, ...]


@dataclass(frozen=True)
class SetupPlan:
    transcription_model: str
    translation_model: str
    download_gb: float
    disk_gb: float
    reasons: tuple[str, ...]


class SetupScanner:
    def __init__(self, hardware_probe=detect_hardware, disk_probe=None, ffmpeg_probe=None):
        self.hardware_probe = hardware_probe
        self.disk_probe = disk_probe or (lambda: round(shutil.disk_usage(".").free / 1024**3, 1))
        self.ffmpeg_probe = ffmpeg_probe or (lambda: bool(shutil.which("ffmpeg") and shutil.which("ffprobe")))

    def scan(self) -> SystemScan:
        hardware, disk, ffmpeg = self.hardware_probe(), self.disk_probe(), self.ffmpeg_probe()
        findings = []
        if hardware.cuda_available:
            findings.append(HardwareFinding(FindingStatus.READY, f"{hardware.gpu_name or 'NVIDIA GPU'} is ready", f"{hardware.vram_gb:g} GB VRAM; CUDA inference available"))
        else:
            findings.append(HardwareFinding(FindingStatus.READY, "CPU processing is available", f"{hardware.ram_gb:g} GB system RAM", "Use a smaller model for faster results"))
        findings.append(HardwareFinding(FindingStatus.READY if hardware.ram_gb >= 8 else FindingStatus.BLOCKING, f"{hardware.ram_gb:g} GB system memory detected", "8 GB minimum; 16 GB or more recommended"))
        findings.append(HardwareFinding(FindingStatus.READY if disk >= 8 else FindingStatus.BLOCKING, f"{disk:g} GB free model storage", "Recommended setup needs approximately 6 GB"))
        findings.append(HardwareFinding(FindingStatus.READY if ffmpeg else FindingStatus.ACTION, "FFmpeg is ready" if ffmpeg else "FFmpeg setup is recommended", "Required to decode media", "Install or choose a local FFmpeg build" if not ffmpeg else ""))
        return SystemScan(hardware, disk, ffmpeg, tuple(findings))


class RecommendationEngine:
    def recommend(self, scan: SystemScan) -> SetupPlan:
        if scan.hardware.cuda_available and scan.hardware.vram_gb >= 8 and scan.hardware.ram_gb >= 16:
            transcription = "whisper-large-v3"
            reason = "Your NVIDIA GPU and memory can run the highest-quality multilingual transcription bundle."
            size = 5.6
        else:
            transcription = "whisper-small"
            reason = "A compact transcription model is recommended for reliable CPU and lower-memory operation."
            size = 3.4
        return SetupPlan(transcription, "nllb-200-distilled-600m", size, round(size * 1.15, 1), (reason, "NLLB-200 adds broad offline translation coverage."))

