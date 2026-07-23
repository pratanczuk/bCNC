# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyInstaller.utils.hooks import collect_all


repo_root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
module_paths = [
    repo_root,
    os.path.join(repo_root, "bCNC"),
    os.path.join(repo_root, "bCNC", "lib"),
    os.path.join(repo_root, "bCNC", "plugins"),
    os.path.join(repo_root, "bCNC", "controllers"),
]
sys.path[:0] = module_paths
datas, binaries, hiddenimports = collect_all("bCNC")

analysis = Analysis(
    [os.path.join(repo_root, "bCNC", "__main__.py")],
    pathex=module_paths,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "simpleArc",
        "simpleRectangle",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="bCNC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join(repo_root, "bCNC", "bCNC.ico"),
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="bCNC",
)
