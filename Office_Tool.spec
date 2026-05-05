# -*- mode: python ; coding: utf-8 -*-

from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


block_cipher = None
project_dir = Path(SPECPATH)


def optional_hiddenimports(*module_names):
    return [name for name in module_names if find_spec(name) is not None]


hiddenimports = []
hiddenimports += collect_submodules("tools")
hiddenimports += collect_submodules("PIL")
hiddenimports += optional_hiddenimports(
    "bs4",
    "docx",
    "fitz",
    "markdown",
    "pdf2image",
    "pydub",
    "PyPDF2",
    "pythoncom",
    "pywintypes",
    "requests",
    "win32com.client",
)


a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        (str(project_dir / "tools"), "tools"),
        (str(project_dir / "assets"), "assets"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Office_Tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Office_Tool",
)
