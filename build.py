"""Build a redistributable Windows package with PyInstaller.

Usage::

    python build.py            # build both executables into artifacts/
    python build.py --clean    # wipe build/ and artifacts/ first

Output::

    artifacts/
        SAM-Python/
            SAM.Picker.exe
            SAM.Game.exe
            _internal/         (Python runtime, Qt DLLs, resources)

The whole ``SAM-Python`` folder is what you ship — zip it up and hand it to
someone who does not have Python installed. Double-clicking ``SAM.Picker.exe``
just works, provided Steam is installed and running on the target machine.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BUILD_DIR = ROOT / "build"
ARTIFACTS_DIR = ROOT / "artifacts"
SPEC_FILE = ROOT / "sam.spec"


def _venv_python() -> str:
    """Return the interpreter path — prefer the project's ``.venv`` if present."""
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return str(venv)
    return sys.executable


def _ensure_pyinstaller(python: str) -> None:
    try:
        subprocess.check_call(
            [python, "-c", "import PyInstaller"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    except subprocess.CalledProcessError:
        pass

    print("[build] Installing PyInstaller...")
    subprocess.check_call(
        [python, "-m", "pip", "install", "-r", str(ROOT / "requirements-dev.txt")]
    )


def _clean() -> None:
    for path in (BUILD_DIR, ARTIFACTS_DIR):
        if path.exists():
            print(f"[build] Removing {path}")
            shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="wipe build/ and artifacts/ first")
    args = parser.parse_args()

    python = _venv_python()
    _ensure_pyinstaller(python)

    if args.clean:
        _clean()

    ARTIFACTS_DIR.mkdir(exist_ok=True)

    cmd = [
        python,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--workpath",
        str(BUILD_DIR),
        "--distpath",
        str(ARTIFACTS_DIR),
        str(SPEC_FILE),
    ]

    print("[build] Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        print(f"[build] PyInstaller failed (exit {proc.returncode}).")
        return proc.returncode

    dist_folder = ARTIFACTS_DIR / "SAM-Python"
    picker = dist_folder / "SAM.Picker.exe"
    game = dist_folder / "SAM.Game.exe"

    print()
    print(f"[build] Distribution folder: {dist_folder}")
    print(f"[build]   picker : {picker}  {'(OK)' if picker.exists() else '(MISSING)'}")
    print(f"[build]   manager: {game}    {'(OK)' if game.exists() else '(MISSING)'}")
    print()
    print("[build] To distribute, zip the SAM-Python folder and share it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
