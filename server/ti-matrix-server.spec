# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the desktop app's sidecar — one directory, console, no window.

One-dir rather than one-file on purpose: a one-file bundle unpacks itself to a temp dir on every
launch, which is seconds of startup and disk churn the app pays on every open. The engine is
standard library only, so the bundle is small; the dynamic imports (the worlds' lazy `BrowserEnvironment`,
the learning layer) are collected explicitly rather than hoped for.
"""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = (
    collect_submodules("appserver")
    + collect_submodules("ti_matrix")
    + ["aiohttp"]
)

a = Analysis(
    ["sidecar_entry.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ti-matrix-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # stdout carries the handshake; the parent reads it
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ti-matrix-server",
)
