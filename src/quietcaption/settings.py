from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_path, user_data_path


CURRENT_SCHEMA_VERSION = 3


class SettingsValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AppSettings:
    schema_version: int = CURRENT_SCHEMA_VERSION
    interface_mode: str = "everyday"
    theme: str = "system"
    output_directory: str = str(Path.home() / "Videos" / "QuietCaption")
    model_directory: str = str(user_data_path("QuietCaption Studio") / "models")
    transcription_model: str = "small"
    source_language: str = "auto"
    translation_language: str = "none"
    onboarding_complete: bool = False
    update_checks: bool = True
    reduced_motion: bool = False
    cache_limit_gb: int = 20
    cpu_threads: int = 0
    compute_device: str = "automatic"
    gpu_fallback: bool = True
    queue_concurrency: int = 1
    subtitle_font_size: int = 24
    subtitle_line_length: int = 42
    log_level: str = "standard"


@dataclass(frozen=True)
class SettingsLoadResult:
    settings: AppSettings
    warning: str | None


_BOOLEAN_FIELDS = frozenset({
    "onboarding_complete",
    "update_checks",
    "reduced_motion",
    "gpu_fallback",
})
_FREE_STRING_FIELDS = frozenset({
    "output_directory",
    "model_directory",
    "transcription_model",
    "source_language",
    "translation_language",
})
_STRING_CHOICES = {
    "interface_mode": {"everyday", "technical"},
    "theme": {"system", "light", "dark"},
    "compute_device": {"automatic", "cpu", "cuda"},
    "log_level": {"minimal", "standard", "technical"},
}
_INTEGER_RANGES = {
    "schema_version": (CURRENT_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION),
    "cache_limit_gb": (1, 1000),
    "cpu_threads": (0, 256),
    "queue_concurrency": (1, 8),
    "subtitle_font_size": (10, 96),
    "subtitle_line_length": (20, 80),
}


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or user_config_path("QuietCaption Studio") / "settings.json"

    def load(self) -> AppSettings:
        return self.load_result().settings

    def load_result(self) -> SettingsLoadResult:
        try:
            contents = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return SettingsLoadResult(AppSettings(), None)
        except (OSError, UnicodeError) as exc:
            return self._recovery_result(f"could not be read: {exc}")

        try:
            payload = json.loads(contents)
        except json.JSONDecodeError as exc:
            return self._recovery_result(f"could not be parsed: {exc}")

        try:
            settings = self._settings_from_payload(payload)
        except SettingsValidationError as exc:
            return self._recovery_result(str(exc))
        return SettingsLoadResult(settings, None)

    def save(self, settings: AppSettings) -> None:
        self.validate(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def validate(settings: AppSettings) -> None:
        if not isinstance(settings, AppSettings):
            raise SettingsValidationError("settings must be an AppSettings instance")

        for field in _BOOLEAN_FIELDS:
            if type(getattr(settings, field)) is not bool:
                raise SettingsValidationError(f"{field} must be a boolean")

        for field in _FREE_STRING_FIELDS | set(_STRING_CHOICES):
            if type(getattr(settings, field)) is not str:
                raise SettingsValidationError(f"{field} must be a string")

        for field in _INTEGER_RANGES:
            if type(getattr(settings, field)) is not int:
                raise SettingsValidationError(f"{field} must be an integer")

        for field, allowed in _STRING_CHOICES.items():
            value = getattr(settings, field)
            if value not in allowed:
                raise SettingsValidationError(f"{field} must be one of {sorted(allowed)}")

        if settings.schema_version != CURRENT_SCHEMA_VERSION:
            raise SettingsValidationError(
                f"schema_version must be {CURRENT_SCHEMA_VERSION}"
            )

        for field, (minimum, maximum) in _INTEGER_RANGES.items():
            if field == "schema_version":
                continue
            value = getattr(settings, field)
            if not minimum <= value <= maximum:
                raise SettingsValidationError(f"{field} must be between {minimum} and {maximum}")

    def export_to(self, destination: Path) -> Path:
        payload = asdict(self.load())
        for field in ("model_directory", "output_directory"):
            payload.pop(field, None)
        self._write_json_atomic(Path(destination), payload)
        return Path(destination)

    def import_from(self, source: Path) -> AppSettings:
        source = Path(source)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SettingsValidationError(
                f"settings import from {source} could not be parsed: {exc}"
            ) from exc
        self._require_json_object(payload)
        allowed = set(AppSettings.__dataclass_fields__) - {"model_directory", "output_directory"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise SettingsValidationError(f"Unknown or unsafe settings fields: {', '.join(unknown)}")
        current = asdict(self.load())
        current.update(payload)
        settings = self._settings_from_payload(current)
        self.save(settings)
        return settings

    def reset_section(self, section: str) -> AppSettings:
        sections = {
            "general": {"interface_mode", "theme"},
            "output": {"output_directory"},
            "models": {"model_directory", "transcription_model", "cache_limit_gb"},
            "processing": {"source_language", "translation_language", "cpu_threads", "compute_device", "gpu_fallback", "queue_concurrency"},
            "subtitle": {"subtitle_font_size", "subtitle_line_length"},
            "privacy": {"update_checks", "reduced_motion"},
            "diagnostics": {"log_level"},
        }
        if section not in sections:
            raise SettingsValidationError(f"Unknown settings section: {section}")
        current, defaults = asdict(self.load()), asdict(AppSettings())
        for field in sections[section]:
            current[field] = defaults[field]
        settings = AppSettings(**current)
        self.save(settings)
        return settings

    @staticmethod
    def _migrate(payload: dict) -> dict:
        SettingsStore._require_json_object(payload)
        if "schema_version" in payload:
            schema_version = payload["schema_version"]
            if type(schema_version) is not int:
                raise SettingsValidationError("schema_version must be an integer")
            if not 1 <= schema_version <= CURRENT_SCHEMA_VERSION:
                raise SettingsValidationError(
                    f"schema_version must be between 1 and {CURRENT_SCHEMA_VERSION}"
                )
        known = set(AppSettings.__dataclass_fields__)
        migrated = {key: value for key, value in payload.items() if key in known}
        migrated["schema_version"] = CURRENT_SCHEMA_VERSION
        return migrated

    @classmethod
    def _settings_from_payload(cls, payload: object) -> AppSettings:
        migrated = cls._migrate(payload)
        try:
            settings = AppSettings(**migrated)
        except (TypeError, ValueError) as exc:
            raise SettingsValidationError(f"settings payload is invalid: {exc}") from exc
        cls.validate(settings)
        return settings

    @staticmethod
    def _require_json_object(payload: object) -> None:
        if type(payload) is not dict:
            raise SettingsValidationError("settings payload must be a JSON object")

    def _recovery_result(self, failure: str) -> SettingsLoadResult:
        warning = (
            f"Settings recovery for {self.path}: {failure}. "
            "Using clean defaults; the settings file was left unchanged."
        )
        return SettingsLoadResult(AppSettings(), warning)

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, path)
