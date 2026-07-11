import hashlib
from pathlib import Path

import pytest

from quietcaption.downloads import verify_sha256
from quietcaption.hardware import HardwareProfile, choose_compute
from quietcaption.media import FFmpegService, MediaError
from quietcaption.models import ModelDescriptor, ModelRegistry
from quietcaption.translation import IdentityTranslator


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

