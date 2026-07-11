from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_path, user_data_path


@dataclass(frozen=True)
class AppSettings:
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


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or user_config_path("QuietCaption Studio") / "settings.json"

    def load(self) -> AppSettings:
        try:
            return AppSettings(**json.loads(self.path.read_text(encoding="utf-8")))
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
