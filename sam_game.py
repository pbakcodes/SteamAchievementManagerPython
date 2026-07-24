"""Entry point that mirrors ``SAM.Game/Program.cs``.

Usage::

    python sam_game.py <app_id>

If invoked with no arguments, launches the picker instead.
"""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6 import QtWidgets

from sam.api import Client, ClientInitializeException, ClientInitializeFailure, steam
from sam.game.manager import Manager


def _show_error(message: str, title: str = "Error") -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    QtWidgets.QMessageBox.critical(None, title, message)


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        # Original SAM.Game shells out to SAM.Picker; we do the same.
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            for name in ("SAM.Picker.exe", "sam_picker.exe"):
                candidate = os.path.join(exe_dir, name)
                if os.path.isfile(candidate):
                    subprocess.Popen([candidate], close_fds=True)
                    return 0
        else:
            here = os.path.dirname(os.path.abspath(__file__))
            picker = os.path.join(here, "sam_picker.py")
            if os.path.isfile(picker):
                subprocess.Popen([sys.executable, picker], close_fds=True)
        return 0

    try:
        app_id = int(argv[0])
    except ValueError:
        _show_error("Could not parse application ID from command line argument.")
        return 1

    install_path = steam.get_install_path()
    startup_path = os.path.dirname(os.path.abspath(__file__))
    if install_path and os.path.normcase(install_path) == os.path.normcase(startup_path):
        _show_error("This tool declines to being run from the Steam directory.")
        return 1

    app = QtWidgets.QApplication(sys.argv)

    with Client() as client:
        try:
            client.initialize(app_id)
        except ClientInitializeException as exc:
            if exc.failure == ClientInitializeFailure.ConnectToGlobalUser:
                _show_error(
                    "Steam is not running. Please start Steam then run this tool again.\n\n"
                    "If you have the game through Family Share, the game may be locked due to\n"
                    "the Family Share account actively playing a game.\n\n"
                    f"({exc})"
                )
            elif str(exc):
                _show_error(
                    "Steam is not running. Please start Steam then run this tool again.\n\n"
                    f"({exc})"
                )
            else:
                _show_error(
                    "Steam is not running. Please start Steam then run this tool again."
                )
            return 1
        except OSError as exc:
            _show_error(f"You've caused an exceptional error!\n\n({exc})")
            return 1

        window = Manager(app_id, client)
        window.show()
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
