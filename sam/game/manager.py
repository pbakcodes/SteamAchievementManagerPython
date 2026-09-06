"""Manager window: view / edit achievements and statistics for one game.

Direct port of ``SAM.Game.Manager``. UI is built with PySide6, whereas the
original used WinForms.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional
from urllib.request import Request, urlopen

from PySide6 import QtCore, QtGui, QtWidgets

from ..api import Client, callbacks as api_callbacks, steam, types as api_types
from ..keyvalue import KeyValue, load_binary
from .. import stats as stats_module


ICON_SIZE = 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _translate_error(code: int) -> str:
    if code == 2:
        return "generic error -- this usually means you don't own the game"
    return str(code)


def _get_localized_string(kv: KeyValue, language: str, default: str) -> str:
    name = kv[language].as_string("")
    if name:
        return name
    if language != "english":
        name = kv["english"].as_string("")
        if name:
            return name
    name = kv.as_string("")
    if name:
        return name
    return default


# ---------------------------------------------------------------------------
# Background icon downloader
# ---------------------------------------------------------------------------
class _IconWorker(QtCore.QObject):
    finished = QtCore.Signal(object, bytes)  # (AchievementInfo, jpeg bytes or b"")

    def __init__(self, game_id: int):
        super().__init__()
        self._game_id = game_id

    @QtCore.Slot(object, str)
    def download(self, info: "stats_module.AchievementInfo", url: str) -> None:
        try:
            req = Request(url, headers={"User-Agent": "SAM-Python/7.0"})
            with urlopen(req, timeout=15) as resp:
                data = resp.read()
        except Exception:
            data = b""
        self.finished.emit(info, data)


# ---------------------------------------------------------------------------
# Custom item that pairs a check-state with an AchievementInfo payload.
# ---------------------------------------------------------------------------
class _AchievementItem(QtWidgets.QTreeWidgetItem):
    def __init__(self, info: "stats_module.AchievementInfo", columns):
        super().__init__(columns)
        self.info = info
        self.setFlags(
            self.flags()
            | QtCore.Qt.ItemIsUserCheckable
            | QtCore.Qt.ItemIsSelectable
            | QtCore.Qt.ItemIsEnabled
        )
        self.setCheckState(
            0,
            QtCore.Qt.Checked if info.is_achieved else QtCore.Qt.Unchecked,
        )


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class Manager(QtWidgets.QMainWindow):
    _icon_request = QtCore.Signal(object, str)

    def __init__(self, game_id: int, client: Client):
        super().__init__()
        self._game_id = int(game_id)
        self._client = client

        self._achievement_definitions: List[stats_module.AchievementDefinition] = []
        self._stat_definitions: List[stats_module.StatDefinition] = []
        self._statistics: List[stats_module.StatInfo] = []
        self._icons: Dict[str, QtGui.QIcon] = {}
        self._icon_queue: List[stats_module.AchievementInfo] = []
        self._icon_busy = False
        self._is_updating_list = False

        # Icon download runs on a worker thread so the UI stays responsive.
        self._icon_thread = QtCore.QThread(self)
        self._icon_worker = _IconWorker(self._game_id)
        self._icon_worker.moveToThread(self._icon_thread)
        self._icon_request.connect(self._icon_worker.download)
        self._icon_worker.finished.connect(self._on_icon_downloaded)
        self._icon_thread.start()

        self._build_ui()

        self._user_stats_received = client.create_and_register_callback(
            api_callbacks.UserStatsReceived
        )
        self._user_stats_received.add_handler(self._on_user_stats_received)

        self._callback_timer = QtCore.QTimer(self)
        self._callback_timer.setInterval(100)
        self._callback_timer.timeout.connect(self._on_timer)
        self._callback_timer.start()

        # Title = "Steam Achievement Manager Python 7.0 | <game name or app id>"
        name = client.steam_apps001.get_app_data(self._game_id, "name") if client.steam_apps001 else None
        title_suffix = name if name else str(self._game_id)
        self.setWindowTitle(f"Steam Achievement Manager Python 7.0 | {title_suffix}")

        self._refresh_stats()

    # -- UI construction ------------------------------------------------
    def _build_ui(self) -> None:
        self.resize(720, 560)

        # Toolbar
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        self._store_action = toolbar.addAction("Commit Changes")
        self._store_action.setEnabled(False)
        self._store_action.triggered.connect(self._on_store)

        self._reload_action = toolbar.addAction("Refresh")
        self._reload_action.setEnabled(False)
        self._reload_action.triggered.connect(self._refresh_stats)

        self._reset_action = toolbar.addAction("Reset")
        self._reset_action.triggered.connect(self._on_reset_all_stats)

        # Central tab widget
        self._tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self._tabs)

        # -- Achievements tab --------------------------------------
        ach_page = QtWidgets.QWidget()
        ach_layout = QtWidgets.QVBoxLayout(ach_page)
        ach_layout.setContentsMargins(4, 4, 4, 4)

        ach_toolbar = QtWidgets.QToolBar()
        lock_all = ach_toolbar.addAction("Lock All")
        lock_all.triggered.connect(self._on_lock_all)
        invert_all = ach_toolbar.addAction("Invert All")
        invert_all.triggered.connect(self._on_invert_all)
        unlock_all = ach_toolbar.addAction("Unlock All")
        unlock_all.triggered.connect(self._on_unlock_all)

        ach_toolbar.addSeparator()
        ach_toolbar.addWidget(QtWidgets.QLabel(" Show only "))
        self._locked_only_button = QtWidgets.QToolButton()
        self._locked_only_button.setText("locked")
        self._locked_only_button.setCheckable(True)
        self._locked_only_button.toggled.connect(self._on_locked_only_toggled)
        ach_toolbar.addWidget(self._locked_only_button)
        self._unlocked_only_button = QtWidgets.QToolButton()
        self._unlocked_only_button.setText("unlocked")
        self._unlocked_only_button.setCheckable(True)
        self._unlocked_only_button.toggled.connect(self._on_unlocked_only_toggled)
        ach_toolbar.addWidget(self._unlocked_only_button)

        ach_toolbar.addSeparator()
        ach_toolbar.addWidget(QtWidgets.QLabel(" Filter "))
        self._filter_edit = QtWidgets.QLineEdit()
        self._filter_edit.setPlaceholderText("filter by name or description")
        self._filter_edit.setMaximumWidth(200)
        self._filter_edit.textChanged.connect(lambda _t: self._get_achievements())
        ach_toolbar.addWidget(self._filter_edit)

        ach_layout.addWidget(ach_toolbar)

        self._achievement_tree = QtWidgets.QTreeWidget()
        self._achievement_tree.setColumnCount(3)
        self._achievement_tree.setHeaderLabels(["Name", "Description", "Unlock Time"])
        self._achievement_tree.setRootIsDecorated(False)
        self._achievement_tree.setAlternatingRowColors(True)
        self._achievement_tree.setIconSize(QtCore.QSize(ICON_SIZE, ICON_SIZE))
        self._achievement_tree.setColumnWidth(0, 240)
        self._achievement_tree.setColumnWidth(1, 320)
        self._achievement_tree.itemChanged.connect(self._on_item_changed)
        ach_layout.addWidget(self._achievement_tree)

        self._tabs.addTab(ach_page, "Achievements")

        # -- Statistics tab ---------------------------------------
        stats_page = QtWidgets.QWidget()
        stats_layout = QtWidgets.QVBoxLayout(stats_page)
        stats_layout.setContentsMargins(4, 4, 4, 4)

        self._stats_table = QtWidgets.QTableWidget()
        self._stats_table.setColumnCount(3)
        self._stats_table.setHorizontalHeaderLabels(["Name", "Value", "Extra"])
        self._stats_table.horizontalHeader().setStretchLastSection(True)
        self._stats_table.setColumnWidth(0, 240)
        self._stats_table.setColumnWidth(1, 100)
        self._stats_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._stats_table.itemChanged.connect(self._on_stat_item_changed)
        stats_layout.addWidget(self._stats_table)

        self._enable_editing_check = QtWidgets.QCheckBox(
            "I understand by modifying the values of stats, "
            "I may screw things up and can't blame anyone but myself."
        )
        self._enable_editing_check.stateChanged.connect(self._on_stat_editing_toggled)
        stats_layout.addWidget(self._enable_editing_check)

        self._tabs.addTab(stats_page, "Statistics")

        # -- Status bar -------------------------------------------
        self._status_country = QtWidgets.QLabel()
        self._status_game = QtWidgets.QLabel()
        self._status_download = QtWidgets.QLabel()
        self._status_download.hide()
        self.statusBar().addWidget(self._status_country)
        self.statusBar().addWidget(self._status_game, 1)
        self.statusBar().addPermanentWidget(self._status_download)

        # Populate country label.
        country = self._client.steam_utils.get_ip_country() if self._client.steam_utils else None
        if country:
            self._status_country.setText(country)

    # ------------------------------------------------------------------
    # Callback pump.
    # ------------------------------------------------------------------
    def _on_timer(self) -> None:
        self._client.run_callbacks(False)

    # ------------------------------------------------------------------
    def _refresh_stats(self) -> None:
        self._achievement_tree.clear()
        self._stats_table.setRowCount(0)

        steam_id = self._client.steam_user.get_steam_id() if self._client.steam_user else 0
        call = self._client.steam_user_stats.request_user_stats(steam_id) if self._client.steam_user_stats else 0
        if call == 0:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed.")
            return

        self._status_game.setText("Retrieving stat information...")
        self._disable_input()

    def _disable_input(self) -> None:
        self._reload_action.setEnabled(False)
        self._store_action.setEnabled(False)

    def _enable_input(self) -> None:
        self._reload_action.setEnabled(True)
        self._store_action.setEnabled(True)

    # ------------------------------------------------------------------
    # UserStatsReceived — actually load / render everything.
    # ------------------------------------------------------------------
    def _on_user_stats_received(self, param: api_types.UserStatsReceived) -> None:
        if param.result != 1:
            self._status_game.setText(
                f"Error while retrieving stats: {_translate_error(param.result)}"
            )
            self._enable_input()
            return

        if not self._load_user_game_stats_schema():
            self._status_game.setText("Failed to load schema.")
            self._enable_input()
            return

        try:
            self._get_achievements()
        except Exception as exc:  # pragma: no cover
            self._status_game.setText("Error when handling achievements retrieval.")
            self._enable_input()
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Error when handling achievements retrieval:\n{exc}"
            )
            return

        try:
            self._get_statistics()
        except Exception as exc:  # pragma: no cover
            self._status_game.setText("Error when handling stats retrieval.")
            self._enable_input()
            QtWidgets.QMessageBox.critical(
                self, "Error", f"Error when handling stats retrieval:\n{exc}"
            )
            return

        self._status_game.setText(
            f"Retrieved {self._achievement_tree.topLevelItemCount()} achievements "
            f"and {self._stats_table.rowCount()} statistics."
        )
        self._enable_input()

    # ------------------------------------------------------------------
    def _load_user_game_stats_schema(self) -> bool:
        install = steam.get_install_path()
        if not install:
            return False
        path = os.path.join(
            install, "appcache", "stats", f"UserGameStatsSchema_{self._game_id}.bin"
        )
        if not os.path.isfile(path):
            return False

        kv = load_binary(path)
        if kv is None:
            return False

        current_language = (
            self._client.steam_apps008.get_current_game_language()
            if self._client.steam_apps008
            else None
        )
        current_language = current_language or "english"

        self._achievement_definitions.clear()
        self._stat_definitions.clear()

        stats_node = kv[str(self._game_id)]["stats"]
        if not stats_node.valid or not stats_node.children:
            return False

        for stat in stats_node.children:
            if not stat.valid:
                continue

            # Try new-style ``type`` string, then fall back to legacy ``type_int``.
            type_node = stat["type"]
            stat_type = api_types.UserStatType.Invalid
            if type_node.valid and type_node.type.name == "String":
                candidate = str(type_node.value).strip().lower()
                aliases = {
                    "int": api_types.UserStatType.Integer,
                    "integer": api_types.UserStatType.Integer,
                    "float": api_types.UserStatType.Float,
                    "averagerate": api_types.UserStatType.AverageRate,
                    "achievements": api_types.UserStatType.Achievements,
                    "groupachievements": api_types.UserStatType.GroupAchievements,
                }
                stat_type = aliases.get(candidate, api_types.UserStatType.Invalid)

            if stat_type == api_types.UserStatType.Invalid:
                type_int_node = stat["type_int"]
                raw = type_int_node.as_int(0) if type_int_node.valid else type_node.as_int(0)
                try:
                    stat_type = api_types.UserStatType(raw)
                except ValueError:
                    stat_type = api_types.UserStatType.Invalid

            if stat_type == api_types.UserStatType.Invalid:
                continue

            if stat_type == api_types.UserStatType.Integer:
                stat_id = stat["name"].as_string("")
                display = _get_localized_string(
                    stat["display"]["name"], current_language, stat_id
                )
                self._stat_definitions.append(
                    stats_module.IntegerStatDefinition(
                        id=stat_id,
                        display_name=display,
                        min_value=stat["min"].as_int(-(2**31)),
                        max_value=stat["max"].as_int(2**31 - 1),
                        max_change=stat["maxchange"].as_int(0),
                        increment_only=stat["incrementonly"].as_bool(False),
                        set_by_trusted_game_server=stat["bSetByTrustedGS"].as_bool(False),
                        default_value=stat["default"].as_int(0),
                        permission=stat["permission"].as_int(0),
                    )
                )
            elif stat_type in (
                api_types.UserStatType.Float,
                api_types.UserStatType.AverageRate,
            ):
                stat_id = stat["name"].as_string("")
                display = _get_localized_string(
                    stat["display"]["name"], current_language, stat_id
                )
                self._stat_definitions.append(
                    stats_module.FloatStatDefinition(
                        id=stat_id,
                        display_name=display,
                        min_value=stat["min"].as_float(float("-inf")),
                        max_value=stat["max"].as_float(float("inf")),
                        max_change=stat["maxchange"].as_float(0.0),
                        increment_only=stat["incrementonly"].as_bool(False),
                        default_value=stat["default"].as_float(0.0),
                        permission=stat["permission"].as_int(0),
                    )
                )
            elif stat_type in (
                api_types.UserStatType.Achievements,
                api_types.UserStatType.GroupAchievements,
            ):
                if not stat.children:
                    continue
                for bits in stat.children:
                    if not bits.name or bits.name.lower() != "bits":
                        continue
                    if not bits.valid or not bits.children:
                        continue
                    for bit in bits.children:
                        aid = bit["name"].as_string("")
                        aname = _get_localized_string(
                            bit["display"]["name"], current_language, aid
                        )
                        adesc = _get_localized_string(
                            bit["display"]["desc"], current_language, ""
                        )
                        self._achievement_definitions.append(
                            stats_module.AchievementDefinition(
                                id=aid,
                                name=aname,
                                description=adesc,
                                icon_normal=bit["display"]["icon"].as_string(""),
                                icon_locked=bit["display"]["icon_gray"].as_string(""),
                                is_hidden=bit["display"]["hidden"].as_bool(False),
                                permission=bit["permission"].as_int(0),
                            )
                        )

        return True

    # ------------------------------------------------------------------
    # Populate achievements list.
    # ------------------------------------------------------------------
    def _get_achievements(self) -> None:
        text_search = self._filter_edit.text().strip() or None
        want_locked = self._locked_only_button.isChecked()
        want_unlocked = self._unlocked_only_button.isChecked()

        self._is_updating_list = True
        self._achievement_tree.clear()

        for definition in self._achievement_definitions:
            if not definition.id:
                continue

            ok, is_achieved, unlock_time = self._client.steam_user_stats.get_achievement_and_unlock_time(
                definition.id
            )
            if not ok:
                continue

            if want_locked or want_unlocked:
                wanted = want_unlocked if is_achieved else want_locked
                if not wanted:
                    continue

            if text_search:
                lower = text_search.lower()
                if (
                    lower not in (definition.name or "").lower()
                    and lower not in (definition.description or "").lower()
                ):
                    continue

            unlock_dt: Optional[datetime] = None
            if is_achieved and unlock_time > 0:
                try:
                    unlock_dt = datetime.fromtimestamp(unlock_time)
                except (OverflowError, OSError, ValueError):
                    unlock_dt = None

            info = stats_module.AchievementInfo(
                id=definition.id,
                is_achieved=is_achieved,
                unlock_time=unlock_dt,
                icon_normal=definition.icon_normal or None,
                icon_locked=definition.icon_locked or definition.icon_normal or None,
                permission=definition.permission,
                name=definition.name,
                description=definition.description,
            )

            name_text = info.name if info.name and not info.name.startswith("#") else info.id
            desc_text = info.description if info.name and not info.name.startswith("#") else ""
            unlock_text = info.unlock_time.strftime("%Y-%m-%d %H:%M:%S") if info.unlock_time else ""

            item = _AchievementItem(info, [name_text, desc_text, unlock_text])

            # Achievements the user is not allowed to change get a warning colour.
            if (definition.permission & 3) != 0:
                for column in range(3):
                    item.setBackground(column, QtGui.QBrush(QtGui.QColor(64, 0, 0)))
                    item.setForeground(column, QtGui.QBrush(QtCore.Qt.white))

            self._achievement_tree.addTopLevelItem(item)
            self._queue_icon(info)

        self._is_updating_list = False
        self._download_next_icon()

    def _get_statistics(self) -> None:
        self._statistics.clear()
        self._stats_table.blockSignals(True)
        self._stats_table.setRowCount(0)

        for definition in self._stat_definitions:
            if not definition.id:
                continue

            if isinstance(definition, stats_module.IntegerStatDefinition):
                ok, value = self._client.steam_user_stats.get_stat_int(definition.id)
                if not ok:
                    continue
                info = stats_module.IntStatInfo(
                    stat_id=definition.id,
                    display_name=definition.display_name,
                    permission=definition.permission,
                    increment_only=definition.increment_only,
                    original_value=value,
                )
            elif isinstance(definition, stats_module.FloatStatDefinition):
                ok, value = self._client.steam_user_stats.get_stat_float(definition.id)
                if not ok:
                    continue
                info = stats_module.FloatStatInfo(
                    stat_id=definition.id,
                    display_name=definition.display_name,
                    permission=definition.permission,
                    increment_only=definition.increment_only,
                    original_value=value,
                )
            else:  # pragma: no cover — shouldn't happen
                continue

            self._statistics.append(info)
            row = self._stats_table.rowCount()
            self._stats_table.insertRow(row)

            name_item = QtWidgets.QTableWidgetItem(info.display_name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)

            value_item = QtWidgets.QTableWidgetItem(str(info.value))
            editable = self._enable_editing_check.isChecked()
            self._apply_value_item_flags(value_item, editable)
            value_item.setData(QtCore.Qt.UserRole, info)

            extra_item = QtWidgets.QTableWidgetItem(info.extra)
            extra_item.setFlags(extra_item.flags() & ~QtCore.Qt.ItemIsEditable)

            self._stats_table.setItem(row, 0, name_item)
            self._stats_table.setItem(row, 1, value_item)
            self._stats_table.setItem(row, 2, extra_item)

        self._stats_table.blockSignals(False)

    @staticmethod
    def _apply_value_item_flags(item: QtWidgets.QTableWidgetItem, editable: bool) -> None:
        flags = item.flags()
        if editable:
            flags |= QtCore.Qt.ItemIsEditable
        else:
            flags &= ~QtCore.Qt.ItemIsEditable
        item.setFlags(flags)

    def _on_stat_editing_toggled(self, state: int) -> None:
        editable = state == QtCore.Qt.Checked
        for row in range(self._stats_table.rowCount()):
            item = self._stats_table.item(row, 1)
            if item is not None:
                self._apply_value_item_flags(item, editable)

    def _on_stat_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if item.column() != 1:
            return
        info = item.data(QtCore.Qt.UserRole)
        if not isinstance(info, stats_module.StatInfo):
            return
        try:
            info.value = item.text()
        except stats_module.StatIsProtectedException:
            self._stats_table.blockSignals(True)
            item.setText(str(info.value))
            self._stats_table.blockSignals(False)
            QtWidgets.QMessageBox.warning(
                self,
                "Stat is protected",
                "This stat is protected. You can't modify it.",
            )
        except ValueError:
            self._stats_table.blockSignals(True)
            item.setText(str(info.value))
            self._stats_table.blockSignals(False)

    # ------------------------------------------------------------------
    # Icon downloading
    # ------------------------------------------------------------------
    def _icon_key_for(self, info: stats_module.AchievementInfo) -> str:
        return info.icon_normal if info.is_achieved else info.icon_locked or info.icon_normal or ""

    def _queue_icon(self, info: stats_module.AchievementInfo) -> None:
        key = self._icon_key_for(info)
        if not key:
            return
        icon = self._icons.get(key)
        if icon is not None:
            self._apply_icon(info, icon)
            return
        self._icon_queue.append(info)

    def _apply_icon(self, info: stats_module.AchievementInfo, icon: QtGui.QIcon) -> None:
        tree = self._achievement_tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if isinstance(item, _AchievementItem) and item.info is info:
                item.setIcon(0, icon)
                break

    def _download_next_icon(self) -> None:
        if self._icon_busy:
            return
        while self._icon_queue:
            info = self._icon_queue.pop(0)
            key = self._icon_key_for(info)
            if not key:
                continue
            cached = self._icons.get(key)
            if cached is not None:
                self._apply_icon(info, cached)
                continue
            url = (
                f"https://cdn.steamstatic.com/steamcommunity/public/images/apps/"
                f"{self._game_id}/{key}"
            )
            self._status_download.setText(
                f"Downloading {1 + len(self._icon_queue)} icons..."
            )
            self._status_download.show()
            self._icon_busy = True
            self._icon_request.emit(info, url)
            return
        self._status_download.hide()

    @QtCore.Slot(object, bytes)
    def _on_icon_downloaded(self, info: stats_module.AchievementInfo, data: bytes) -> None:
        self._icon_busy = False
        if data:
            pixmap = QtGui.QPixmap()
            if pixmap.loadFromData(data):
                icon = QtGui.QIcon(pixmap)
                key = self._icon_key_for(info)
                if key:
                    self._icons[key] = icon
                self._apply_icon(info, icon)
        self._download_next_icon()

    # ------------------------------------------------------------------
    # Filter toolbar callbacks.
    # ------------------------------------------------------------------
    def _on_locked_only_toggled(self, checked: bool) -> None:
        if checked:
            self._unlocked_only_button.blockSignals(True)
            self._unlocked_only_button.setChecked(False)
            self._unlocked_only_button.blockSignals(False)
        self._get_achievements()

    def _on_unlocked_only_toggled(self, checked: bool) -> None:
        if checked:
            self._locked_only_button.blockSignals(True)
            self._locked_only_button.setChecked(False)
            self._locked_only_button.blockSignals(False)
        self._get_achievements()

    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if self._is_updating_list or column != 0 or not isinstance(item, _AchievementItem):
            return
        info = item.info
        if (info.permission & 3) != 0:
            # Protected achievement — revert the check state.
            self._achievement_tree.blockSignals(True)
            item.setCheckState(
                0,
                QtCore.Qt.Checked if info.is_achieved else QtCore.Qt.Unchecked,
            )
            self._achievement_tree.blockSignals(False)
            QtWidgets.QMessageBox.warning(
                self,
                "Error",
                "Sorry, but this is a protected achievement and cannot be managed "
                "with Steam Achievement Manager.",
            )

    # ------------------------------------------------------------------
    def _on_lock_all(self) -> None:
        self._set_all_achievements(QtCore.Qt.Unchecked)

    def _on_unlock_all(self) -> None:
        self._set_all_achievements(QtCore.Qt.Checked)

    def _on_invert_all(self) -> None:
        tree = self._achievement_tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if isinstance(item, _AchievementItem):
                new = (
                    QtCore.Qt.Unchecked
                    if item.checkState(0) == QtCore.Qt.Checked
                    else QtCore.Qt.Checked
                )
                item.setCheckState(0, new)

    def _set_all_achievements(self, state: QtCore.Qt.CheckState) -> None:
        tree = self._achievement_tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if isinstance(item, _AchievementItem):
                item.setCheckState(0, state)

    # ------------------------------------------------------------------
    # Commit changes.
    # ------------------------------------------------------------------
    def _store_achievements(self) -> int:
        pending: List[stats_module.AchievementInfo] = []
        tree = self._achievement_tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if not isinstance(item, _AchievementItem):
                continue
            info = item.info
            desired = item.checkState(0) == QtCore.Qt.Checked
            if info.is_achieved == desired:
                continue
            info.is_achieved = desired
            pending.append(info)

        if not pending:
            return 0

        for info in pending:
            if not self._client.steam_user_stats.set_achievement(info.id, info.is_achieved):
                QtWidgets.QMessageBox.critical(
                    self,
                    "Error",
                    f"An error occurred while setting the state for {info.id}, aborting store.",
                )
                return -1
        return len(pending)

    def _store_statistics(self) -> int:
        pending = [s for s in self._statistics if s.is_modified]
        if not pending:
            return 0

        for info in pending:
            if isinstance(info, stats_module.IntStatInfo):
                ok = self._client.steam_user_stats.set_stat_int(info.id, info.int_value)
            elif isinstance(info, stats_module.FloatStatInfo):
                ok = self._client.steam_user_stats.set_stat_float(info.id, info.float_value)
            else:
                continue
            if not ok:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Error",
                    f"An error occurred while setting the value for {info.id}, aborting store.",
                )
                return -1
        return len(pending)

    def _store(self) -> bool:
        if not self._client.steam_user_stats.store_stats():
            QtWidgets.QMessageBox.critical(
                self, "Error", "An error occurred while storing, aborting."
            )
            return False
        return True

    def _on_store(self) -> None:
        achievements = self._store_achievements()
        if achievements < 0:
            self._refresh_stats()
            return
        stats = self._store_statistics()
        if stats < 0:
            self._refresh_stats()
            return
        if not self._store():
            self._refresh_stats()
            return
        QtWidgets.QMessageBox.information(
            self,
            "Information",
            f"Stored {achievements} achievements and {stats} statistics.",
        )
        self._refresh_stats()

    # ------------------------------------------------------------------
    def _on_reset_all_stats(self) -> None:
        if (
            QtWidgets.QMessageBox.question(
                self,
                "Warning",
                "Are you absolutely sure you want to reset stats?",
            )
            != QtWidgets.QMessageBox.Yes
        ):
            return

        achievements_too = (
            QtWidgets.QMessageBox.question(
                self,
                "Question",
                "Do you want to reset achievements too?",
            )
            == QtWidgets.QMessageBox.Yes
        )

        if (
            QtWidgets.QMessageBox.question(
                self,
                "Warning",
                "Really really sure?",
            )
            != QtWidgets.QMessageBox.Yes
        ):
            return

        if not self._client.steam_user_stats.reset_all_stats(achievements_too):
            QtWidgets.QMessageBox.critical(self, "Error", "Failed.")
            return
        self._refresh_stats()

    # ------------------------------------------------------------------
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._callback_timer.stop()
        self._icon_thread.quit()
        self._icon_thread.wait(2000)
        super().closeEvent(event)
