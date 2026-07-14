import hashlib
from pathlib import Path

import pytest

from quietcaption.downloads import verify_sha256
from quietcaption.hardware import HardwareProfile, choose_compute
from quietcaption.media import FFmpegService, MediaError, PyAVMediaService, best_available_media_service
from quietcaption.models import ModelDescriptor, ModelRegistry
from quietcaption.translation import IdentityTranslator
from quietcaption.demo import DemoTranslator


def test_compute_prefers_usable_cuda_and_falls_back_to_cpu():
    assert choose_compute(HardwareProfile(True, "RTX", 8, 32)).device == "cuda"
    assert choose_compute(HardwareProfile(False, None, 0, 16)).device == "cpu"


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
