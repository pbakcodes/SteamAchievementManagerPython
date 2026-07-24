# Steam Achievement Manager (Python)

A Python port of [gibbed's Steam Achievement Manager](https://github.com/gibbed/SteamAchievementManager).

Steam Achievement Manager (SAM) is a lightweight tool that manages achievements and
statistics in the Steam client. It requires:

- The Steam client to be installed and running.
- The user to be logged in.
- Ownership of the game whose stats you want to manage.

This is a functional Python 3 reimplementation of the original C# / WinForms SAM.
The Steam client library is accessed directly via `ctypes` (loading `steamclient64.dll`),
and the GUI is built with **PySide6** (Qt for Python).

## Requirements

- Windows (Steam client is Windows-only for the DLL layout SAM uses).
- **64-bit Python 3.9 or newer.** The Steam client interfaces use C++ virtual method
  tables. On 64-bit Windows the calling convention is uniform, which `ctypes` supports.
  On 32-bit Python this would require `__thiscall`, which `ctypes` cannot express, so
  a 64-bit interpreter is required.
- PySide6.

```powershell
py -3 -m pip install -r requirements.txt
```

## Usage

Launch the picker to browse games you own:

```powershell
py -3 sam_picker.py
```

Or launch the manager directly for a specific App ID:

```powershell
py -3 sam_game.py 480
```

Double-clicking a game in the picker will spawn the manager for that game.

## Layout

```
sam/
    api/          - Steam client interop (ctypes wrappers)
    keyvalue.py   - Binary VDF parser (for UserGameStatsSchema)
    stats.py      - Stat / achievement data classes
    game/         - Achievement / statistics manager GUI
    picker/       - Game picker GUI
sam_game.py       - Manager entry point (mirrors SAM.Game/Program.cs)
sam_picker.py     - Picker entry point (mirrors SAM.Picker/Program.cs)
build.py          - PyInstaller build helper
sam.spec          - PyInstaller spec (multipackage build)
```

## Building a redistributable .exe

Users who don't have Python installed can be given a standalone build made
with [PyInstaller](https://pyinstaller.org). PyInstaller bundles a copy of
the Python interpreter, all Python dependencies and the Qt runtime into a
folder that runs as-is on any 64-bit Windows machine.

```powershell
# From an activated venv with the runtime deps installed:
.\.venv\Scripts\python.exe build.py            # build
.\.venv\Scripts\python.exe build.py --clean    # rebuild from scratch
```

Output goes to `artifacts/SAM-Python/`:

```
artifacts/
    SAM-Python/
        SAM.Picker.exe    <- double-click to launch the picker
        SAM.Game.exe      <- runs the manager for a specific app id
        _internal/        (Python, Qt, all runtime files)
```

The `sam.spec` file uses PyInstaller's `MERGE` feature so the two executables
share the same `_internal` bundle instead of shipping two copies of Qt
(saves roughly 150 MB).

To distribute, zip the whole `SAM-Python` folder. The target machine only
needs Steam installed and running — Python is embedded inside the exe.

## Attribution

This is a Python port. All credit for the original design, protocol
reverse-engineering and Steam interop belongs to **Rick "gibbed"** and the
contributors to the [upstream C# project](https://github.com/gibbed/SteamAchievementManager).

The Python port (translation of the C# code, PySide6 GUI, ctypes bindings,
packaging scripts) is a derivative work released under the **same zlib
license** as the original. See [LICENSE.txt](LICENSE.txt) for the full text
and the mandatory original copyright notice.

If you use this port in a product, an acknowledgment of the original SAM
project in your product documentation is appreciated (not required).
