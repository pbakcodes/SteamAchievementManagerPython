# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds SAM.Picker.exe and SAM.Game.exe into a single
folder distribution where they share the bundled Python runtime and PySide6.

Run via ``python build.py`` (which invokes PyInstaller) rather than editing.
"""

from PyInstaller.building.api import COLLECT, EXE, MERGE, PYZ
from PyInstaller.building.build_main import Analysis


block_cipher = None


# ---------------------------------------------------------------------------
# Analyse each entry point.
# ---------------------------------------------------------------------------
picker_a = Analysis(
    ["sam_picker.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

game_a = Analysis(
    ["sam_game.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)


# ---------------------------------------------------------------------------
# MERGE identifies files common to both analyses so we don't ship two copies
# of Qt (~200 MB).  The first analysis "owns" the shared files; the second
# only records that it depends on them.
# ---------------------------------------------------------------------------
MERGE(
    (picker_a, "sam_picker", "SAM.Picker"),
    (game_a, "sam_game", "SAM.Game"),
)

picker_pyz = PYZ(picker_a.pure, picker_a.zipped_data, cipher=block_cipher)
game_pyz = PYZ(game_a.pure, game_a.zipped_data, cipher=block_cipher)


picker_exe = EXE(
    picker_pyz,
    picker_a.scripts,
    [],
    exclude_binaries=True,
    name="SAM.Picker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed app (no black cmd window)
    disable_windowed_traceback=False,
    icon=None,
)

game_exe = EXE(
    game_pyz,
    game_a.scripts,
    [],
    exclude_binaries=True,
    name="SAM.Game",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)


# ---------------------------------------------------------------------------
# Collect everything into a single distribution folder.
# ---------------------------------------------------------------------------
coll = COLLECT(
    picker_exe,
    picker_a.binaries,
    picker_a.zipfiles,
    picker_a.datas,
    game_exe,
    game_a.binaries,
    game_a.zipfiles,
    game_a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SAM-Python",
)
