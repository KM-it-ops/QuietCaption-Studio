import json

import pytest

from quietcaption.settings import AppSettings, SettingsStore, SettingsValidationError


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
