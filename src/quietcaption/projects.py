import json
from pathlib import Path

from .atomic_files import publish_text_batch
from .domain import Project


class ProjectStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Project:
        return Project.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, project: Project) -> None:
        publish_text_batch(
            {self.path: project_json(project)},
            {self.path: self.path.with_suffix(self.path.suffix + ".tmp")},
        )


def project_json(project: Project) -> str:
    return json.dumps(project.to_dict(), ensure_ascii=False, indent=2)
