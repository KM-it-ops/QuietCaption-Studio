from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = collect_data_files("quietcaption")
binaries = []
hiddenimports = ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
for package in ("faster_whisper", "ctranslate2", "sentencepiece", "av"):
    filter_submodules = (
        (lambda name: not name.startswith("ctranslate2.converters"))
        if package == "ctranslate2"
        else (lambda name: True)
    )
    package_datas, package_binaries, package_hidden = collect_all(package, filter_submodules=filter_submodules)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    ["entrypoint.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas + [("../README.md", "."), ("../LICENSE", "."), ("../THIRD_PARTY_NOTICES.md", ".")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "deep_translator", "googletrans", "transformers", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="QuietCaption Studio", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="QuietCaption Studio")
