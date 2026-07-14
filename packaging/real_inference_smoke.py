from __future__ import annotations

import argparse
import json
import os
import socket
from contextlib import contextmanager
from pathlib import Path

from quietcaption.hardware import choose_compute, detect_hardware
from quietcaption.languages import default_registry
from quietcaption.media import PyAVMediaService
from quietcaption.model_service import ModelService
from quietcaption.models import ModelRegistry, built_in_catalog
from quietcaption.transcription import FasterWhisperTranscriber
from quietcaption.translation import NllbCTranslate2Translator


@contextmanager
def network_blocked():
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def blocked(*args, **kwargs):
        raise RuntimeError("Network access attempted during offline inference smoke test")

    socket.socket.connect = blocked
    socket.create_connection = blocked
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create_connection


def main() -> int:
    parser = argparse.ArgumentParser(description="Opt-in real offline inference smoke test")
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()

    catalog = built_in_catalog(default_registry())
    registry = ModelRegistry(args.model_root, catalog)
    service = ModelService(registry)
    transcription = next(item for item in catalog if item.id == "whisper-small")
    translation = next(item for item in catalog if item.id == "nllb-200-distilled-600m")

    if args.download:
        for descriptor in (transcription, translation):
            if not service.verify(descriptor):
                print(f"Installing {descriptor.id} from pinned revision {descriptor.revision}", flush=True)
                service.install(descriptor)

    for descriptor in (transcription, translation):
        if not service.verify(descriptor):
            raise RuntimeError(f"Model integrity verification failed: {descriptor.id}")

    decoded = args.audio.with_name("decoded-smoke.wav")
    PyAVMediaService().extract_audio(args.audio, decoded)
    compute = choose_compute(detect_hardware())

    with network_blocked():
        language, segments = FasterWhisperTranscriber(
            str(args.model_root / transcription.id), compute
        ).transcribe(decoded, "en")
        if not segments:
            raise RuntimeError("Real transcription produced no subtitle segments")
        source_texts = [segment.text for segment in segments]
        source_text = " ".join(source_texts)
        translated = NllbCTranslate2Translator(
            args.model_root / translation.id, compute.device
        ).translate(source_texts, "en", "spa_Latn")
        if len(translated) != len(source_texts) or any(not text.strip() for text in translated):
            raise RuntimeError("Real translation did not produce one result per subtitle segment")

    print(json.dumps({
        "compute": {"device": compute.device, "type": compute.compute_type},
        "detected_language": language,
        "segments": len(segments),
        "transcription": source_text,
        "translation_spa_Latn": translated,
        "network_during_inference": "blocked",
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
