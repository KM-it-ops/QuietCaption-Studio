import tomllib
from pathlib import Path


def test_package_has_desktop_entrypoint_and_no_online_translation_dependency():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["quietcaption"] == "quietcaption.app:main"
    dependencies = " ".join(data["project"].get("dependencies", []) + data["project"]["optional-dependencies"]["inference"])
    assert "deep-translator" not in dependencies
    assert "googletrans" not in dependencies


def test_release_files_exist():
    for path in ["README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "packaging/quietcaption.spec", "packaging/build.ps1", "packaging/smoke.ps1", "packaging/real_inference_smoke.py", "packaging/installer.iss"]:
        assert Path(path).is_file(), path


def test_build_bootstraps_wheel_before_editable_install():
    script = Path("packaging/build.ps1").read_text(encoding="utf-8")
    bootstrap = 'pip install --upgrade pip setuptools wheel'
    editable = 'pip install --no-build-isolation -e ".[dev,inference]"'
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


def test_release_build_installs_native_offline_inference_runtime():
    script = Path("packaging/build.ps1").read_text(encoding="utf-8")
    assert '.[dev,inference]' in script
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    inference = " ".join(data["project"]["optional-dependencies"]["inference"])
    assert "faster-whisper" in inference
    assert "ctranslate2" in inference
    assert "sentencepiece" in inference
    assert "torch" not in inference
    assert "transformers" not in inference


def test_release_build_uses_unique_workspace_pytest_directory():
    script = Path("packaging/build.ps1").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/windows-release.yml").read_text(encoding="utf-8")
    assert ".pytest-runs" in script
    assert "--basetemp" in script
    assert "-p no:cacheprovider" in script
    assert ".tmp-test" not in workflow


def test_pyinstaller_collects_dynamically_loaded_inference_packages():
    spec = Path("packaging/quietcaption.spec").read_text(encoding="utf-8")
    for package in ("faster_whisper", "ctranslate2", "sentencepiece", "av"):
        assert package in spec
    for unused in ("transformers", "torch", "tensorflow"):
        assert f'"{unused}"' in spec
    assert "ctranslate2.converters" in spec


def test_release_pipeline_smoke_tests_portable_and_installed_apps():
    workflow = Path(".github/workflows/windows-release.yml").read_text(encoding="utf-8")
    smoke = Path("packaging/smoke.ps1").read_text(encoding="utf-8")
    assert "packaging\\smoke.ps1" in workflow
    assert "QuietCaption-Studio-Setup-1.0.0.exe" in smoke
    assert "--demo" in smoke
    assert "/VERYSILENT" in smoke


def test_real_inference_smoke_blocks_network_after_model_installation():
    smoke = Path("packaging/real_inference_smoke.py").read_text(encoding="utf-8")
    assert 'os.environ["HF_HUB_OFFLINE"] = "1"' in smoke
    assert "socket.socket.connect = blocked" in smoke
    assert "FasterWhisperTranscriber" in smoke
    assert "NllbCTranslate2Translator" in smoke
