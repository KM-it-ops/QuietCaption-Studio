import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from quietcaption.downloads import verify_sha256
from quietcaption.hardware import HardwareProfile, choose_compute, resolve_compute
from quietcaption.hardware import ComputeConfig
from quietcaption.media import FFmpegService, MediaError, PyAVMediaService, best_available_media_service
from quietcaption.models import ModelDescriptor, ModelRegistry
from quietcaption import transcription
from quietcaption.translation import IdentityTranslator
from quietcaption.demo import DemoTranslator


def test_compute_prefers_usable_cuda_and_falls_back_to_cpu():
    assert choose_compute(HardwareProfile(True, "RTX", 8, 32)).device == "cuda"
    assert choose_compute(HardwareProfile(False, None, 0, 16)).device == "cpu"


@pytest.mark.parametrize(
    ("preference", "fallback", "profile", "device", "compute_type", "used_fallback", "can_run"),
    [
        ("automatic", True, HardwareProfile(True, "RTX", 8, 32), "cuda", "float16", False, True),
        ("automatic", True, HardwareProfile(False, None, 0, 16), "cpu", "int8", False, True),
        ("cpu", False, HardwareProfile(True, "RTX", 8, 32), "cpu", "int8", False, True),
        ("cuda", False, HardwareProfile(True, "RTX", 3, 32), "cuda", "int8_float16", False, True),
        ("cuda", True, HardwareProfile(False, None, 0, 16), "cpu", "int8", True, True),
        ("cuda", False, HardwareProfile(False, None, 0, 16), None, None, False, False),
    ],
)
def test_compute_resolution_honors_preference_and_fallback(
    preference, fallback, profile, device, compute_type, used_fallback, can_run
):
    resolution = resolve_compute(preference, fallback, profile)

    assert resolution.can_run is can_run
    assert resolution.used_fallback is used_fallback
    assert (resolution.config.device if resolution.config else None) == device
    assert (resolution.config.compute_type if resolution.config else None) == compute_type


def test_compute_resolution_explains_blocked_cuda_request():
    resolution = resolve_compute("cuda", False, HardwareProfile(False, None, 0, 16))

    assert "CUDA unavailable" in resolution.label
    assert "Enable GPU fallback or select CPU" in resolution.blocking_reason


def test_compute_resolution_rejects_invalid_preference():
    with pytest.raises(ValueError, match="automatic, cpu, or cuda"):
        resolve_compute("gpu", True, HardwareProfile(False, None, 0, 16))


def test_model_registry_filters_by_kind_and_language(tmp_path):
    registry = ModelRegistry(tmp_path, [ModelDescriptor("whisper-small", "transcription", ["*"], 500, "x", "0" * 64)])
    assert [item.id for item in registry.available("transcription", "en")] == ["whisper-small"]
    assert not registry.is_installed("whisper-small")


def test_checksum_verification_rejects_modified_file(tmp_path):
    path = tmp_path / "model.bin"
    path.write_bytes(b"safe")
    assert verify_sha256(path, hashlib.sha256(b"safe").hexdigest())
    assert not verify_sha256(path, "0" * 64)


def test_ffmpeg_uses_argument_arrays_and_maps_errors(tmp_path):
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        class Result: returncode = 0; stdout = '{"format":{"duration":"2.5"},"streams":[]}' ; stderr = ""
        return Result()
    info = FFmpegService(runner=runner).probe(tmp_path / "clip with space.mp4")
    assert info.duration == 2.5
    assert calls[0][-1].endswith("clip with space.mp4")


def test_identity_translation_is_explicitly_local():
    assert IdentityTranslator().translate(["hello"], "en", "en") == ["hello"]


def test_media_service_falls_back_to_bundled_pyav_when_ffmpeg_is_absent():
    service = best_available_media_service(which=lambda _: None)
    assert isinstance(service, PyAVMediaService)


def test_pyav_fallback_decodes_audio_to_whisper_wav(tmp_path):
    import math
    import struct
    import wave

    source = tmp_path / "tone.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
        samples = [int(1000 * math.sin(2 * math.pi * 440 * index / 16000)) for index in range(1600)]
        output.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

    service = PyAVMediaService()
    info = service.probe(source)
    destination = service.extract_audio(source, tmp_path / "decoded.wav")

    assert info.duration > 0
    with wave.open(str(destination), "rb") as decoded:
        assert decoded.getframerate() == 16000
        assert decoded.getnchannels() == 1


def test_demo_translation_accepts_capability_registry_codes():
    translated = DemoTranslator().translate(["Welcome", "Private"], "en", "spa_Latn")
    assert translated[0].startswith("Bienvenido")


def test_faster_whisper_receives_configured_beam_size_and_vad_filter(monkeypatch, tmp_path):
    calls = []

    class FakeWhisperModel:
        def __init__(self, model, **kwargs):
            calls.append(("init", model, kwargs))

        def transcribe(self, path, **kwargs):
            calls.append(("transcribe", path, kwargs))
            return iter([SimpleNamespace(start=0.0, end=1.0, text=" Hello ")]), SimpleNamespace(language="en")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))
    options = transcription.TranscriptionOptions(beam_size=11)
    transcriber = transcription.FasterWhisperTranscriber(
        "local-model",
        ComputeConfig("cpu", "int8", "CPU"),
        options,
    )

    language, segments = transcriber.transcribe(tmp_path / "audio.wav")

    assert language == "en"
    assert [item.text for item in segments] == ["Hello"]
    assert calls[1][2]["beam_size"] == 11
    assert calls[1][2]["vad_filter"] is True


@pytest.mark.parametrize("beam_size", [1, 20])
def test_transcription_options_accepts_inclusive_beam_boundaries(beam_size):
    assert transcription.TranscriptionOptions(beam_size=beam_size).beam_size == beam_size


@pytest.mark.parametrize("beam_size", [0, 21])
def test_transcription_options_rejects_out_of_range_beam_size(beam_size):
    with pytest.raises(ValueError, match="beam_size"):
        transcription.TranscriptionOptions(beam_size=beam_size)
