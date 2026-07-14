from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_path, user_data_path


CURRENT_SCHEMA_VERSION = 2


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
    queue_concurrency: int = 1
    subtitle_font_size: int = 24
    subtitle_line_length: int = 42
    log_level: str = "standard"


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or user_config_path("QuietCaption Studio") / "settings.json"

    def load(self) -> AppSettings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            settings = AppSettings(**self._migrate(payload))
            self.validate(settings)
            return settings
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.validate(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def validate(settings: AppSettings) -> None:
        choices = {
            "interface_mode": {"everyday", "technical"},
            "theme": {"system", "light", "dark"},
            "compute_device": {"automatic", "cpu", "cuda"},
            "log_level": {"minimal", "standard", "technical"},
        }
        for field, allowed in choices.items():
            value = getattr(settings, field)
            if value not in allowed:
                raise SettingsValidationError(f"{field} must be one of {sorted(allowed)}")
        ranges = {
            "cache_limit_gb": (1, 1000),
            "cpu_threads": (0, 256),
            "queue_concurrency": (1, 8),
            "subtitle_font_size": (10, 96),
            "subtitle_line_length": (20, 80),
        }
        for field, (minimum, maximum) in ranges.items():
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
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        allowed = set(AppSettings.__dataclass_fields__) - {"model_directory", "output_directory"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise SettingsValidationError(f"Unknown or unsafe settings fields: {', '.join(unknown)}")
        current = asdict(self.load())
        current.update(payload)
        settings = AppSettings(**self._migrate(current))
        self.save(settings)
        return settings

    def reset_section(self, section: str) -> AppSettings:
        sections = {
            "general": {"interface_mode", "theme"},
            "output": {"output_directory"},
            "models": {"model_directory", "transcription_model", "cache_limit_gb"},
            "processing": {"source_language", "translation_language", "cpu_threads", "compute_device", "queue_concurrency"},
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
        known = set(AppSettings.__dataclass_fields__)
        migrated = {key: value for key, value in payload.items() if key in known}
        migrated["schema_version"] = CURRENT_SCHEMA_VERSION
        return migrated

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, path)
