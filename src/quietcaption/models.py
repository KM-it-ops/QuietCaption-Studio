from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    kind: str
    languages: list[str]
    size_mb: int
    url: str
    sha256: str
    license: str = "See model source"


class ModelRegistry:
    def __init__(self, root: Path, catalog: list[ModelDescriptor]):
        self.root, self.catalog = root, catalog

    def available(self, kind: str, language: str | None = None) -> list[ModelDescriptor]:
        return [item for item in self.catalog if item.kind == kind and (language is None or "*" in item.languages or language in item.languages)]

    def is_installed(self, model_id: str) -> bool:
        return (self.root / model_id / ".complete").exists()

