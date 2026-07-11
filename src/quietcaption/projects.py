import json
import os
from pathlib import Path

from .domain import Project


class ProjectStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Project:
        return Project.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, project: Project) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

