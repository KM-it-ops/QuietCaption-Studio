from quietcaption.hardware import HardwareProfile
from quietcaption.setup import FindingStatus, RecommendationEngine, SetupScanner


def test_scanner_explains_hardware_and_missing_ffmpeg():
    scanner = SetupScanner(
        hardware_probe=lambda: HardwareProfile(True, "RTX 4070", 12, 32),
        disk_probe=lambda: 100,
        ffmpeg_probe=lambda: False,
    )
    scan = scanner.scan()
    assert any(item.status is FindingStatus.READY and "RTX 4070" in item.summary for item in scan.findings)
    assert any(item.status is FindingStatus.ACTION and "FFmpeg" in item.summary for item in scan.findings)


def test_recommendation_selects_automatic_bundle_with_rationale():
    scanner = SetupScanner(lambda: HardwareProfile(True, "RTX", 12, 32), lambda: 100, lambda: True)
    plan = RecommendationEngine().recommend(scanner.scan())
    assert plan.transcription_model == "whisper-large-v3"
    assert plan.translation_model == "nllb-200-distilled-600m"
    assert plan.download_gb > 1
    assert plan.reasons


def test_low_memory_system_gets_smaller_transcription_model():
    scanner = SetupScanner(lambda: HardwareProfile(False, None, 0, 8), lambda: 20, lambda: True)
    assert RecommendationEngine().recommend(scanner.scan()).transcription_model == "whisper-small"

