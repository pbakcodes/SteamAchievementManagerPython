"""Entry point that mirrors ``SAM.Picker/Program.cs``.

Usage::

    python sam_picker.py
"""

from __future__ import annotations

import os
import sys

from PySide6 import QtWidgets

from sam.api import Client, ClientInitializeException, steam
from sam.picker.picker import GamePicker


def _show_error(message: str, title: str = "Error") -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    QtWidgets.QMessageBox.critical(None, title, message)


def main() -> int:
    install_path = steam.get_install_path()
    startup_path = os.path.dirname(os.path.abspath(__file__))
    if install_path and os.path.normcase(install_path) == os.path.normcase(startup_path):
        _show_error("This tool declines to being run from the Steam directory.")
        return 1

    app = QtWidgets.QApplication(sys.argv)

    with Client() as client:
        try:
            client.initialize(0)
        except ClientInitializeException as exc:
            if str(exc):
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

        window = GamePicker(client)
        window.show()
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
