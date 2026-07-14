from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    kind: str
    languages: frozenset[str]
    size_mb: int
    url: str
    sha256: str
    license: str = "See model source"
    revision: str = "main"

    def __post_init__(self):
        object.__setattr__(self, "languages", frozenset(self.languages))


class ModelRegistry:
    def __init__(self, root: Path, catalog: list[ModelDescriptor]):
        self.root, self.catalog = root, catalog

    def available(self, kind: str, language: str | None = None) -> list[ModelDescriptor]:
        return [item for item in self.catalog if item.kind == kind and (language is None or "*" in item.languages or language in item.languages)]

    def is_installed(self, model_id: str) -> bool:
        return (self.root / model_id / ".complete").exists()


def built_in_catalog(registry=None) -> list[ModelDescriptor]:
    from .languages import NLLB_CODES, WHISPER_LANGUAGES
    return [
        ModelDescriptor("whisper-small", "transcription", frozenset(WHISPER_LANGUAGES), 500, "Systran/faster-whisper-small", "0" * 64, "MIT / model terms", "536b0662742c02347bc0e980a01041f333bce120"),
        ModelDescriptor("whisper-large-v3", "transcription", frozenset(WHISPER_LANGUAGES), 3100, "Systran/faster-whisper-large-v3", "0" * 64, "MIT / model terms", "edaa852ec7e145841d8ffdb056a99866b5f0a478"),
        ModelDescriptor("nllb-200-distilled-600m", "translation", frozenset(NLLB_CODES), 651, "mijuanlo/nllb-200-distilled-600M-ct2-int8", "0" * 64, "CC-BY-NC-4.0 (non-commercial use)", "16bc5ff"),
    ]
