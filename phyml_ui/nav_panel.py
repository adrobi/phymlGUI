import os

from PySide6.QtWidgets import QToolBox, QListWidget, QListWidgetItem, QMenu
from PySide6.QtCore import Qt, Signal

from phyml_core.history import display_input
from phyml_core.i18n import _t

_SAVE = '__save__'   # data of the "save current settings" row of the presets list


class NavPanel(QToolBox):
    """Recent inputs, presets and run history; a double click asks the window to act."""

    recent_activated = Signal(str)          # the full path of the input
    preset_activated = Signal(dict)         # a copy of the preset's parameters
    preset_save_requested = Signal()
    preset_delete_requested = Signal(str)   # the name of a user preset
    history_activated = Signal(int)         # the row, = the index in set_history's list

    def __init__(self, parent=None):
        super().__init__(parent)
        self._presets = {}                  # (kind, key) -> preset dict
        self.activated_preset_name = ''     # the shown name of the last activated preset

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(
            lambda item: self.recent_activated.emit(item.data(Qt.UserRole)))
        self.addItem(self.recent_list, _t("panel_recent"))

        self.presets_list = QListWidget()
        self.presets_list.itemDoubleClicked.connect(self._preset_double_clicked)
        self.presets_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.presets_list.customContextMenuRequested.connect(self._preset_menu)
        self.addItem(self.presets_list, _t("panel_presets"))

        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(
            lambda item: self.history_activated.emit(self.history_list.row(item)))
        self.addItem(self.history_list, _t("panel_history"))

    def set_recent(self, paths: list) -> None:
        self.recent_list.clear()
        for p in paths:
            item = QListWidgetItem(os.path.basename(p) + ('/' if os.path.isdir(p) else ''))
            item.setData(Qt.UserRole, p)
            self.recent_list.addItem(item)

    def set_presets(self, builtin: dict, user: dict) -> None:
        """The save row, the built-in presets (keyed by their label key), the user ones."""
        self.presets_list.clear()
        self._presets = {}
        save_item = QListWidgetItem(_t('preset_save_current'))
        save_item.setData(Qt.UserRole, _SAVE)
        self.presets_list.addItem(save_item)
        for kind, presets in (('builtin', builtin), ('user', user)):
            for key, preset in presets.items():
                it = QListWidgetItem(_t(key) if kind == 'builtin' else key)
                it.setData(Qt.UserRole, (kind, key))
                self.presets_list.addItem(it)
                self._presets[(kind, key)] = preset

    def set_history(self, records: list) -> None:
        self.history_list.clear()
        for rec in records:
            self.history_list.addItem(_t('hist_entry').format(
                rec.get('ts', ''), display_input(rec), rec.get('ok', 0), rec.get('n', 0)))

    def _preset_double_clicked(self, item):
        data = item.data(Qt.UserRole)
        if data == _SAVE:
            self.preset_save_requested.emit()
            return
        self.activated_preset_name = item.text()
        self.preset_activated.emit(dict(self._presets.get(tuple(data), {})))

    def _preset_menu(self, pos):
        item = self.presets_list.itemAt(pos)
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if not (isinstance(data, tuple) and data[0] == 'user'):
            return
        menu = QMenu(self)
        act = menu.addAction(_t('preset_delete'))
        if menu.exec(self.presets_list.mapToGlobal(pos)) == act:
            self.preset_delete_requested.emit(data[1])
