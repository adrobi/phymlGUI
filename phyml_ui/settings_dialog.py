from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QComboBox, QLineEdit, QPushButton, QFileDialog,
                             QGroupBox, QDialog, QDialogButtonBox)
from PySide6.QtGui import QIcon

from phyml_core.i18n import _t
from phyml_core.utils import resource_path
from phyml_ui.themes import ACCENTS


class SettingsDialog(QDialog):
    """Rarely changed settings: executable paths and appearance."""

    FIELDS = ('path_phyml', 'path_mpirun', 'path_muscle')

    def __init__(self, app_window, parent=None):
        super().__init__(parent)
        self.app_window = app_window
        self.setWindowTitle(_t("settings_title"))
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(640, 340)
        root = QVBoxLayout(self)
        engine_box = QGroupBox(_t("settings_engine_box"))
        eform = QFormLayout(engine_box)
        self.engine_combo = QComboBox()
        self.engine_combo.addItem(_t("engine_phyml"), "phyml")
        self.engine_combo.addItem(_t("engine_iqtree"), "iqtree")
        idx = self.engine_combo.findData(app_window.engine_setting)
        self.engine_combo.setCurrentIndex(max(idx, 0))
        eform.addRow(_t("settings_engine"), self.engine_combo)
        self.iqtree_edit = QLineEdit(app_window.iqtree_path_input.text())
        iq_btn = QPushButton(_t("btn_browse"))
        iq_btn.clicked.connect(lambda: self._browse(self.iqtree_edit))
        irow = QHBoxLayout(); irow.addWidget(self.iqtree_edit); irow.addWidget(iq_btn)
        iwrap = QWidget(); iwrap.setLayout(irow)
        eform.addRow(_t("path_iqtree"), iwrap)
        root.addWidget(engine_box)

        paths_box = QGroupBox(_t("settings_paths"))
        form = QFormLayout(paths_box)
        self.edits = []
        inputs = [app_window.phyml_path_input, app_window.mpirun_path_input,
                  app_window.muscle_path_input]
        for key, source in zip(self.FIELDS, inputs):
            edit = QLineEdit(source.text())
            btn = QPushButton(_t("btn_browse"))
            btn.clicked.connect(lambda _=False, e=edit: self._browse(e))
            row = QHBoxLayout(); row.addWidget(edit); row.addWidget(btn)
            wrap = QWidget(); wrap.setLayout(row)
            form.addRow(_t(key), wrap)
            self.edits.append(edit)
        root.addWidget(paths_box)

        look_box = QGroupBox(_t("settings_appearance"))
        look = QFormLayout(look_box)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(_t("theme_system"), "system")
        self.theme_combo.addItem(_t("theme_light"), "light")
        self.theme_combo.addItem(_t("theme_dark"), "dark")
        idx = self.theme_combo.findData(app_window._theme_setting)
        self.theme_combo.setCurrentIndex(max(idx, 0))
        self.accent_combo = QComboBox()
        self.accent_combo.addItem(_t("accent_system"), "system")
        for key, hexval in ACCENTS.items():
            self.accent_combo.addItem(_t("accent_" + key), key)
        idx = self.accent_combo.findData(app_window._accent_setting)
        self.accent_combo.setCurrentIndex(max(idx, 0))
        look.addRow(_t("settings_theme"), self.theme_combo)
        look.addRow(_t("settings_accent"), self.accent_combo)
        root.addWidget(look_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, _t("file_exe"))
        if path:
            edit.setText(path)

    def accept(self):
        inputs = [self.app_window.phyml_path_input,
                  self.app_window.mpirun_path_input,
                  self.app_window.muscle_path_input]
        for edit, source in zip(self.edits, inputs):
            source.setText(edit.text())  # programmatic: triggers autosave & MPI detect
        self.app_window.iqtree_path_input.setText(self.iqtree_edit.text())
        engine = self.engine_combo.currentData()
        if engine != self.app_window.engine_setting:
            self.app_window.engine_setting = engine
            self.app_window.update_models()
        self.app_window.apply_theme(self.theme_combo.currentData(),
                                    self.accent_combo.currentData())
        if not self.app_window._is_loading:
            self.app_window.auto_save()
        super().accept()
