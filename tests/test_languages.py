from quietcaption.languages import CapabilityTier, LanguageRegistry, default_registry, resolve_nllb_code
from quietcaption.models import built_in_catalog


def test_registry_contains_broad_whisper_and_nllb_capabilities():
    registry = default_registry()
    catalog = built_in_catalog(registry)
    whisper = next(model for model in catalog if model.id == "whisper-large-v3")
    nllb = next(model for model in catalog if model.id == "nllb-200-distilled-600m")
    assert len(whisper.languages) >= 99
    assert len(nllb.languages) >= 190
    assert all(registry.get(code) for code in whisper.languages | nllb.languages)


def test_language_search_finds_names_codes_and_rtl_metadata():
    registry = default_registry()
    arabic = registry.get("arb_Arab")
    assert arabic.direction == "rtl"
    assert arabic.tier in CapabilityTier
    assert arabic in registry.search("Arabic")
    assert registry.get("eng_Latn") in registry.search("eng_Latn")


def test_active_model_capabilities_drive_selector_options():
    registry = default_registry()
    catalog = built_in_catalog(registry)
    whisper = next(model for model in catalog if model.kind == "transcription")
    options = registry.for_model(whisper)
    assert {item.code for item in options} == whisper.languages


def test_whisper_codes_resolve_to_nllb_tokens():
    assert resolve_nllb_code("en") == "eng_Latn"
    assert resolve_nllb_code("ar") == "arb_Arab"
    assert resolve_nllb_code("zh") == "zho_Hans"
    assert resolve_nllb_code("spa_Latn") == "spa_Latn"
