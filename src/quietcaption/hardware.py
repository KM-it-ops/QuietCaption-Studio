from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class HardwareProfile:
    cuda_available: bool
    gpu_name: str | None
    vram_gb: float
    ram_gb: float


@dataclass(frozen=True)
class ComputeConfig:
    device: str
    compute_type: str
    label: str


def choose_compute(profile: HardwareProfile) -> ComputeConfig:
    if profile.cuda_available:
        return ComputeConfig("cuda", "float16" if profile.vram_gb >= 4 else "int8_float16", profile.gpu_name or "NVIDIA GPU")
    return ComputeConfig("cpu", "int8", "CPU")


def detect_hardware() -> HardwareProfile:
    ram = 0.0
    try:
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]
        status = MemoryStatus(); status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            ram = round(status.total / 1024**3, 1)
    except Exception:
        pass
    try:
        import ctranslate2
        count = ctranslate2.get_cuda_device_count()
        return HardwareProfile(count > 0, "NVIDIA GPU" if count else None, 4.0 if count else 0.0, ram)
    except Exception:
        return HardwareProfile(False, None, 0.0, ram)

