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


def test_build_bootstraps_wheel_before_editable_install():
    script = Path("packaging/build.ps1").read_text(encoding="utf-8")
    bootstrap = 'pip install --upgrade pip setuptools wheel'
    editable = 'pip install --no-build-isolation -e ".[dev]"'
    assert bootstrap in script
    assert script.index(bootstrap) < script.index(editable)


def test_pyinstaller_uses_package_safe_entrypoint():
    spec = Path("packaging/quietcaption.spec").read_text(encoding="utf-8")
    launcher = Path("packaging/entrypoint.py")
    assert launcher.is_file()
    source = launcher.read_text(encoding="utf-8")
    assert "from quietcaption.app import main" in source
    assert '"entrypoint.py"' in spec
    assert "src/quietcaption/app.py" not in spec


def test_build_finds_per_user_inno_setup_installation():
    script = Path("packaging/build.ps1").read_text(encoding="utf-8")
    assert "$env:LOCALAPPDATA" in script
    assert 'Programs\\Inno Setup 6\\ISCC.exe' in script
