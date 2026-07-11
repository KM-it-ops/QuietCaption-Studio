from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("quietcaption")

a = Analysis(
    ["entrypoint.py"],
    pathex=["../src"],
    binaries=[],
    datas=datas + [("../README.md", "."), ("../LICENSE", "."), ("../THIRD_PARTY_NOTICES.md", ".")],
    hiddenimports=["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "deep_translator", "googletrans"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="QuietCaption Studio", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="QuietCaption Studio")
