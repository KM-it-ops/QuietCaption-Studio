import json
from dataclasses import replace

import pytest
import quietcaption.settings as settings_module

from quietcaption.settings import (
    AppSettings,
    SettingsStore,
    SettingsValidationError,
)


WRONG_TYPE_VALUES = (
    ("schema_version", "3"),
    ("interface_mode", 7),
    ("theme", 7),
    ("output_directory", 7),
    ("model_directory", 7),
    ("transcription_model", 7),
    ("source_language", 7),
    ("translation_language", 7),
    ("onboarding_complete", 1),
    ("update_checks", "yes"),
    ("reduced_motion", 0),
    ("cache_limit_gb", True),
    ("cpu_threads", False),
    ("compute_device", 7),
    ("gpu_fallback", 1),
    ("queue_concurrency", "2"),
    ("queue_concurrency", True),
    ("subtitle_font_size", True),
    ("subtitle_line_length", False),
    ("log_level", 7),
)


def test_settings_validation_field_sets_cover_every_dataclass_field():
    covered = (
        getattr(settings_module, "_BOOLEAN_FIELDS", set())
        | getattr(settings_module, "_FREE_STRING_FIELDS", set())
        | set(getattr(settings_module, "_INTEGER_RANGES", {}))
        | set(getattr(settings_module, "_STRING_CHOICES", {}))
    )

    assert covered == set(AppSettings.__dataclass_fields__)


@pytest.mark.parametrize(("field", "value"), WRONG_TYPE_VALUES)
def test_settings_save_rejects_wrong_field_types_without_replacing_destination(tmp_path, field, value):
    path = tmp_path / "settings.json"
    original = b'{"theme": "dark"}\n'
    path.write_bytes(original)
    store = SettingsStore(path)

    with pytest.raises(SettingsValidationError, match=field):
        store.save(replace(AppSettings(), **{field: value}))

    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("field", "value"),
    tuple((field, value) for field, value in WRONG_TYPE_VALUES if field not in {"model_directory", "output_directory"}),
)
def test_settings_import_rejects_wrong_field_types_without_replacing_destination(tmp_path, field, value):
    path = tmp_path / "settings.json"
    original = b'{"theme": "light"}\n'
    path.write_bytes(original)
    source = tmp_path / "import.json"
    source.write_text(json.dumps({field: value}), encoding="utf-8")
    store = SettingsStore(path)

    with pytest.raises(SettingsValidationError, match=field):
        store.import_from(source)

    assert path.read_bytes() == original


@pytest.mark.parametrize("payload", ["not json", "[]", "42", '"settings"'])
def test_settings_import_normalizes_malformed_payload_failures_without_replacing_destination(tmp_path, payload):
    path = tmp_path / "settings.json"
    original = b'{"theme": "dark"}\n'
    path.write_bytes(original)
    source = tmp_path / "import.json"
    source.write_text(payload, encoding="utf-8")

    with pytest.raises(SettingsValidationError):
        SettingsStore(path).import_from(source)

    assert path.read_bytes() == original


def test_settings_load_result_missing_file_is_clean_defaults(tmp_path):
    result = SettingsStore(tmp_path / "missing.json").load_result()

    assert result.settings == AppSettings()
    assert result.warning is None


def test_settings_load_result_malformed_json_warns_without_rewriting_source(tmp_path):
    path = tmp_path / "settings.json"
    original = b'{"theme":'
    path.write_bytes(original)

    result = SettingsStore(path).load_result()

    assert result.settings == AppSettings()
    assert result.warning is not None
    assert str(path) in result.warning
    assert "parse" in result.warning.lower()
    assert path.read_bytes() == original


def test_settings_load_result_malformed_field_warns_without_rewriting_source(tmp_path):
    path = tmp_path / "settings.json"
    original = json.dumps({"theme": 7}).encode()
    path.write_bytes(original)

    result = SettingsStore(path).load_result()

    assert result.settings == AppSettings()
    assert result.warning is not None
    assert str(path) in result.warning
    assert "theme" in result.warning
    assert path.read_bytes() == original


def test_settings_load_result_migrates_valid_legacy_values_without_warning(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": 1, "theme": "dark", "cpu_threads": 4}), encoding="utf-8")

    result = SettingsStore(path).load_result()

    assert result.settings.schema_version == AppSettings().schema_version
    assert result.settings.theme == "dark"
    assert result.settings.cpu_threads == 4
    assert result.warning is None


def test_settings_load_compatibility_returns_load_result_settings(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    store = SettingsStore(path)

    assert store.load() == store.load_result().settings


def test_settings_migrate_legacy_payload_and_preserve_known_values(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "dark", "cpu_threads": 4}), encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings.schema_version >= 2
    assert settings.theme == "dark"
    assert settings.cpu_threads == 4
    assert settings.gpu_fallback is True


def test_gpu_fallback_round_trips_as_a_boolean(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(compute_device="cuda", gpu_fallback=False))

    loaded = store.load()

    assert loaded.compute_device == "cuda"
    assert loaded.gpu_fallback is False


def test_settings_reject_non_boolean_gpu_fallback(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")

    with pytest.raises(SettingsValidationError, match="gpu_fallback"):
        store.save(AppSettings(gpu_fallback="yes"))


def test_gpu_fallback_survives_portable_transfer_and_processing_reset(tmp_path):
    source = SettingsStore(tmp_path / "source.json")
    destination = SettingsStore(tmp_path / "destination.json")
    portable = tmp_path / "portable.json"
    source.save(AppSettings(compute_device="cuda", gpu_fallback=False))

    source.export_to(portable)
    imported = destination.import_from(portable)

    assert imported.compute_device == "cuda"
    assert imported.gpu_fallback is False

    reset = destination.reset_section("processing")

    assert reset.compute_device == AppSettings().compute_device
    assert reset.gpu_fallback is True


def test_settings_reject_invalid_ranges_before_saving(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")

    with pytest.raises(SettingsValidationError, match="queue_concurrency"):
        store.save(AppSettings(queue_concurrency=0))

    assert not store.path.exists()


def test_settings_export_excludes_machine_local_paths(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    exported = tmp_path / "portable-settings.json"
    store.save(AppSettings(theme="dark", model_directory="C:/private/models"))

    store.export_to(exported)
    payload = json.loads(exported.read_text(encoding="utf-8"))

    assert payload["theme"] == "dark"
    assert "model_directory" not in payload
    assert "output_directory" not in payload


def test_settings_import_rejects_unknown_or_secret_fields(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    imported = tmp_path / "unsafe.json"
    imported.write_text(json.dumps({"theme": "dark", "api_token": "secret"}), encoding="utf-8")

    with pytest.raises(SettingsValidationError, match="api_token"):
        store.import_from(imported)


def test_reset_section_only_resets_that_section(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(theme="dark", subtitle_font_size=40))

    updated = store.reset_section("subtitle")

    assert updated.theme == "dark"
    assert updated.subtitle_font_size == AppSettings().subtitle_font_size
