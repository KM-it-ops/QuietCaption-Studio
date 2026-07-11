import tomllib
from pathlib import Path


def test_package_has_desktop_entrypoint_and_no_online_translation_dependency():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["quietcaption"] == "quietcaption.app:main"
    dependencies = " ".join(data["project"].get("dependencies", []) + data["project"]["optional-dependencies"]["inference"])
    assert "deep-translator" not in dependencies
    assert "googletrans" not in dependencies


def test_release_files_exist():
    for path in ["README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "packaging/quietcaption.spec", "packaging/build.ps1", "packaging/installer.iss"]:
        assert Path(path).is_file(), path

