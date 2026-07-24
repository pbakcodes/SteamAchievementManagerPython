"""GamePicker window: pick a game to launch the Manager for.

Ported from ``SAM.Picker.GamePicker``. XML game list is downloaded from
``https://gib.me/sam/games.xml`` just like the original.
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.request import Request, urlopen

from PySide6 import QtCore, QtGui, QtWidgets

from ..api import Client, callbacks as api_callbacks, types as api_types


LOGO_SIZE = QtCore.QSize(184, 69)


@dataclass
class GameInfo:
    id: int
    type: str
    name: Optional[str] = None
    image_url: Optional[str] = None
    image_key: Optional[str] = None  # cache key for the QIcon
    icon: Optional[QtGui.QIcon] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------
class _ListDownloader(QtCore.QObject):
    finished = QtCore.Signal(list, str)  # (list[tuple[int, str]], error)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            req = Request(
                "https://gib.me/sam/games.xml",
                headers={"User-Agent": "SAM-Python/7.0"},
            )
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
        except Exception as exc:
            self.finished.emit([], str(exc))
            return

        pairs: List[tuple[int, str]] = []
        try:
            root = ET.fromstring(data)
            for elem in root.findall("game"):
                if elem.text is None:
                    continue
                try:
                    app_id = int(elem.text.strip())
                except ValueError:
                    continue
                game_type = elem.get("type") or "normal"
                pairs.append((app_id, game_type))
        except ET.ParseError as exc:
            self.finished.emit([], f"failed to parse game list: {exc}")
            return

        self.finished.emit(pairs, "")


class _LogoDownloader(QtCore.QObject):
    finished = QtCore.Signal(int, str, bytes)  # (app_id, url, jpeg bytes)

    @QtCore.Slot(int, str)
    def download(self, app_id: int, url: str) -> None:
        try:
            req = Request(url, headers={"User-Agent": "SAM-Python/7.0"})
            with urlopen(req, timeout=15) as resp:
                data = resp.read()
        except Exception:
            data = b""
        self.finished.emit(app_id, url, data)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class GamePicker(QtWidgets.QMainWindow):
    _logo_request = QtCore.Signal(int, str)

    def __init__(self, client: Client):
        super().__init__()
        self._client = client
        self._games: Dict[int, GameInfo] = {}
        self._filtered: List[GameInfo] = []
        self._logos: Dict[str, QtGui.QIcon] = {}
        self._logo_queue: List[GameInfo] = []
        self._logos_attempting: set[str] = set()
        self._logos_attempted: set[str] = set()
        self._logo_busy = False

        # Icon cache: fall back to a solid grey icon for games without a logo.
        blank = QtGui.QPixmap(LOGO_SIZE)
        blank.fill(QtGui.QColor(105, 105, 105))
        self._blank_icon = QtGui.QIcon(blank)

        self._build_ui()

        # AppDataChanged callback is fired by Steam when app metadata arrives.
        self._app_data_cb = client.create_and_register_callback(
            api_callbacks.AppDataChanged
        )
        self._app_data_cb.add_handler(self._on_app_data_changed)

        # Logo downloader lives on its own thread.
        self._logo_thread = QtCore.QThread(self)
        self._logo_worker = _LogoDownloader()
        self._logo_worker.moveToThread(self._logo_thread)
        self._logo_request.connect(self._logo_worker.download)
        self._logo_worker.finished.connect(self._on_logo_downloaded)
        self._logo_thread.start()

        # Callback pump.
        self._callback_timer = QtCore.QTimer(self)
        self._callback_timer.setInterval(100)
        self._callback_timer.timeout.connect(lambda: self._client.run_callbacks(False))
        self._callback_timer.start()

        self._start_list_download()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle("Steam Achievement Manager Python 7.0 — Game Picker")
        self.resize(720, 620)

        # -- Menu bar (filters) ------------------------------------
        menubar = self.menuBar()
        filter_menu = menubar.addMenu("&Filter")
        self._filter_normals = filter_menu.addAction("&Games")
        self._filter_normals.setCheckable(True)
        self._filter_normals.setChecked(True)
        self._filter_normals.toggled.connect(self._refresh_games)

        self._filter_demos = filter_menu.addAction("&Demos")
        self._filter_demos.setCheckable(True)
        self._filter_demos.toggled.connect(self._refresh_games)

        self._filter_mods = filter_menu.addAction("&Mods")
        self._filter_mods.setCheckable(True)
        self._filter_mods.toggled.connect(self._refresh_games)

        self._filter_junk = filter_menu.addAction("&Junk")
        self._filter_junk.setCheckable(True)
        self._filter_junk.toggled.connect(self._refresh_games)

        # -- Top toolbar (refresh, add, search) --------------------
        toolbar = self.addToolBar("Games")
        toolbar.setMovable(False)

        self._refresh_button = QtWidgets.QPushButton("Refresh")
        self._refresh_button.clicked.connect(self._on_refresh)
        toolbar.addWidget(self._refresh_button)

        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel(" Add game "))
        self._add_edit = QtWidgets.QLineEdit()
        self._add_edit.setMaximumWidth(120)
        self._add_edit.setPlaceholderText("app id")
        self._add_edit.returnPressed.connect(self._on_add_game)
        toolbar.addWidget(self._add_edit)
        add_button = QtWidgets.QPushButton("Add")
        add_button.clicked.connect(self._on_add_game)
        toolbar.addWidget(add_button)

        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel(" Search "))
        self._search_edit = QtWidgets.QLineEdit()
        self._search_edit.setMaximumWidth(200)
        self._search_edit.textChanged.connect(lambda _t: self._refresh_games())
        toolbar.addWidget(self._search_edit)

        # -- Central game list -------------------------------------
        self._list = QtWidgets.QListWidget()
        self._list.setViewMode(QtWidgets.QListView.IconMode)
        self._list.setResizeMode(QtWidgets.QListView.Adjust)
        self._list.setMovement(QtWidgets.QListView.Static)
        self._list.setIconSize(LOGO_SIZE)
        self._list.setGridSize(QtCore.QSize(LOGO_SIZE.width() + 20, LOGO_SIZE.height() + 40))
        self._list.setSpacing(6)
        self._list.setUniformItemSizes(True)
        self._list.setWordWrap(True)
        self._list.itemActivated.connect(self._on_activate_game)
        self.setCentralWidget(self._list)

        # -- Status bar --------------------------------------------
        self._status_message = QtWidgets.QLabel()
        self._status_download = QtWidgets.QLabel()
        self._status_download.hide()
        self.statusBar().addWidget(self._status_message, 1)
        self.statusBar().addPermanentWidget(self._status_download)

    # ------------------------------------------------------------------
    def _start_list_download(self) -> None:
        self._refresh_button.setEnabled(False)
        self._status_message.setText("Downloading game list...")

        self._list_thread = QtCore.QThread(self)
        self._list_worker = _ListDownloader()
        self._list_worker.moveToThread(self._list_thread)
        self._list_thread.started.connect(self._list_worker.run)
        self._list_worker.finished.connect(self._on_list_downloaded)
        self._list_thread.start()

    @QtCore.Slot(list, str)
    def _on_list_downloaded(self, pairs: list, error: str) -> None:
        self._list_thread.quit()
        self._list_thread.wait(2000)

        if error and not pairs:
            self._add_default_games()
            QtWidgets.QMessageBox.warning(self, "Error", error)
        else:
            self._status_message.setText("Checking game ownership...")
            for app_id, game_type in pairs:
                self._add_game(app_id, game_type)

        self._refresh_games()
        self._refresh_button.setEnabled(True)
        self._download_next_logo()

    # ------------------------------------------------------------------
    def _owns_game(self, app_id: int) -> bool:
        if self._client.steam_apps008 is None:
            return False
        return self._client.steam_apps008.is_subscribed_app(app_id)

    def _add_game(self, app_id: int, game_type: str) -> None:
        if app_id in self._games:
            return
        if not self._owns_game(app_id):
            return
        info = GameInfo(id=app_id, type=game_type)
        info.name = self._client.steam_apps001.get_app_data(app_id, "name") if self._client.steam_apps001 else None
        if not info.name:
            info.name = f"App {app_id}"
        self._games[app_id] = info

    def _add_default_games(self) -> None:
        self._add_game(480, "normal")  # Spacewar

    # ------------------------------------------------------------------
    def _refresh_games(self) -> None:
        want_normals = self._filter_normals.isChecked()
        want_demos = self._filter_demos.isChecked()
        want_mods = self._filter_mods.isChecked()
        want_junk = self._filter_junk.isChecked()

        search = self._search_edit.text().strip().lower() if self._search_edit.text() else ""

        self._filtered.clear()
        self._list.clear()
        for info in sorted(self._games.values(), key=lambda g: (g.name or "").lower()):
            if search and search not in (info.name or "").lower():
                continue
            wanted = {
                "normal": want_normals,
                "demo": want_demos,
                "mod": want_mods,
                "junk": want_junk,
            }.get(info.type, True)
            if not wanted:
                continue
            self._filtered.append(info)
            item = QtWidgets.QListWidgetItem(info.name or f"App {info.id}")
            item.setIcon(info.icon or self._blank_icon)
            item.setData(QtCore.Qt.UserRole, info.id)
            item.setToolTip(f"App ID: {info.id}\nType: {info.type}")
            self._list.addItem(item)
            # Queue logo download if we haven't attempted it yet.
            if info.icon is None:
                self._add_game_to_logo_queue(info)

        self._status_message.setText(
            f"Displaying {len(self._filtered)} games. Total {len(self._games)} games."
        )
        if self._filtered:
            self._list.setCurrentRow(0)
        self._download_next_logo()

    # ------------------------------------------------------------------
    def _get_game_image_url(self, app_id: int) -> Optional[str]:
        apps001 = self._client.steam_apps001
        apps008 = self._client.steam_apps008
        if apps001 is None:
            return None
        current_language = (apps008.get_current_game_language() if apps008 else None) or "english"

        candidate = apps001.get_app_data(app_id, f"small_capsule/{current_language}")
        if candidate:
            return (
                "https://shared.cloudflare.steamstatic.com/store_item_assets/"
                f"steam/apps/{app_id}/{candidate}"
            )
        if current_language != "english":
            candidate = apps001.get_app_data(app_id, "small_capsule/english")
            if candidate:
                return (
                    "https://shared.cloudflare.steamstatic.com/store_item_assets/"
                    f"steam/apps/{app_id}/{candidate}"
                )
        candidate = apps001.get_app_data(app_id, "logo")
        if candidate:
            return (
                "https://cdn.steamstatic.com/steamcommunity/public/images/apps/"
                f"{app_id}/{candidate}.jpg"
            )
        return None

    def _add_game_to_logo_queue(self, info: GameInfo) -> None:
        if info.icon is not None:
            return
        image_url = self._get_game_image_url(info.id)
        if not image_url:
            return
        info.image_url = image_url
        cached = self._logos.get(image_url)
        if cached is not None:
            info.icon = cached
            self._update_item_icon(info)
            return
        if image_url in self._logos_attempting or image_url in self._logos_attempted:
            return
        self._logos_attempting.add(image_url)
        self._logo_queue.append(info)

    def _download_next_logo(self) -> None:
        if self._logo_busy:
            return
        while self._logo_queue:
            info = self._logo_queue.pop(0)
            if not info.image_url:
                continue
            if info not in self._filtered:
                self._logos_attempting.discard(info.image_url)
                continue
            self._status_download.setText(
                f"Downloading {1 + len(self._logo_queue)} game icons..."
            )
            self._status_download.show()
            self._logo_busy = True
            self._logo_request.emit(info.id, info.image_url)
            return
        self._status_download.hide()

    @QtCore.Slot(int, str, bytes)
    def _on_logo_downloaded(self, app_id: int, url: str, data: bytes) -> None:
        self._logo_busy = False
        self._logos_attempting.discard(url)
        self._logos_attempted.add(url)
        info = self._games.get(app_id)
        if data and info is not None:
            pixmap = QtGui.QPixmap()
            if pixmap.loadFromData(data):
                icon = QtGui.QIcon(pixmap)
                self._logos[url] = icon
                info.icon = icon
                self._update_item_icon(info)
        self._download_next_logo()

    def _update_item_icon(self, info: GameInfo) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(QtCore.Qt.UserRole) == info.id:
                item.setIcon(info.icon or self._blank_icon)
                break

    # ------------------------------------------------------------------
    # Actions.
    # ------------------------------------------------------------------
    def _on_activate_game(self, item: QtWidgets.QListWidgetItem) -> None:
        app_id = item.data(QtCore.Qt.UserRole)
        if app_id is None:
            return

        args = self._build_manager_argv(int(app_id))
        if args is None:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                "Could not locate sam_game.py next to sam_picker.py.",
            )
            return

        try:
            subprocess.Popen(args, close_fds=True)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Failed to start manager: {exc}"
            )

    @staticmethod
    def _build_manager_argv(app_id: int) -> Optional[list[str]]:
        """Return the command-line to launch the manager for ``app_id``.

        Handles both "frozen" (PyInstaller .exe) and development (running via
        Python interpreter) modes.
        """
        import os

        if getattr(sys, "frozen", False):
            # In a frozen build ``sys.executable`` is the .exe itself. When
            # invoked with just an app id, our entry point launches the
            # manager. If a companion SAM.Game.exe was built (multipackage
            # build), prefer that.
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            for name in ("SAM.Game.exe", "sam_game.exe"):
                candidate = os.path.join(exe_dir, name)
                if os.path.isfile(candidate):
                    return [candidate, str(app_id)]
            return [sys.executable, str(app_id)]

        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidate = os.path.join(here, "sam_game.py")
        if not os.path.isfile(candidate):
            return None
        return [sys.executable, candidate, str(app_id)]

    def _on_refresh(self) -> None:
        self._add_edit.setText("")
        self._games.clear()
        self._logo_queue.clear()
        self._logos_attempting.clear()
        self._logos_attempted.clear()
        self._start_list_download()

    def _on_add_game(self) -> None:
        text = self._add_edit.text().strip()
        try:
            app_id = int(text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Error", "Please enter a valid game ID.")
            return
        if not self._owns_game(app_id):
            QtWidgets.QMessageBox.warning(self, "Error", "You don't own that game.")
            return

        # Clear queue — we're switching to a single-app view.
        for info in list(self._logo_queue):
            if info.image_url:
                self._logos_attempted.discard(info.image_url)
        self._logo_queue.clear()

        self._add_edit.setText("")
        self._games.clear()
        self._add_game(app_id, "normal")
        self._filter_normals.setChecked(True)
        self._refresh_games()
        self._download_next_logo()

    # ------------------------------------------------------------------
    # Steam callbacks.
    # ------------------------------------------------------------------
    def _on_app_data_changed(self, param: api_types.AppDataChanged) -> None:
        if not param.result:
            return
        info = self._games.get(int(param.id))
        if info is None:
            return
        if self._client.steam_apps001 is not None:
            info.name = (
                self._client.steam_apps001.get_app_data(info.id, "name")
                or info.name
            )
        self._add_game_to_logo_queue(info)
        self._download_next_logo()

    # ------------------------------------------------------------------
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._callback_timer.stop()
        self._logo_thread.quit()
        self._logo_thread.wait(2000)
        super().closeEvent(event)
