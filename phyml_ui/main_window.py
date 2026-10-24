import copy
import csv
import os
import shutil
from datetime import datetime
from html import escape

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QFormLayout, QComboBox, QLineEdit, QPushButton,
                             QFileDialog, QMessageBox, QTabWidget,
                             QCheckBox, QGroupBox, QSizePolicy, QLabel,
                             QStatusBar, QProgressBar, QSplitter, QToolBox,
                             QToolButton, QListWidget, QListWidgetItem,
                             QTextEdit, QTableWidget, QTableWidgetItem,
                             QHeaderView, QScrollArea, QDialog,
                             QDialogButtonBox, QMenu, QInputDialog)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QFont, QShortcut, QKeySequence

from phyml_core import __version__, presets, settings
from phyml_core.history import HistoryStore, best_tree, display_input, new_record
from phyml_core.i18n import _t
from phyml_core.paths import AppPaths
from phyml_core.utils import psutil, detect_cores, is_mpi_binary, resource_path
from phyml_core.pipeline import PipelineWorker
from phyml_ui.tree_viewer import TreeViewerWidget
from phyml_ui.themes import resolve, build_qss, role_colors, ACCENTS, PALETTES

# per-file values of a worker row that go into the history
_STAT_KEYS = ('model', 'taxa', 'lnL', 'gamma', 'tstv', 'time')
# settings that say nothing about how a run was made: left out of a history record
_NOT_RUN_PARAMS = ('presets', 'recent', 'window')


class LogConsole(QWidget):
    """Structured log: colored roles, severity filter, substring search.

    Keeps the QTextEdit-style API used by the pipeline (append/clear) and
    by tests (toPlainText); entries are always stored in full, filtering
    only affects what is displayed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []  # (role, text)
        self._role_colors = {'error': '#E53935', 'success': '#43A047',
                             'system': '#1E9E6A', 'out': '#212121'}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        self.filter_box = QComboBox()
        self.filter_box.addItem(_t("log_filter_all"), "all")
        self.filter_box.addItem(_t("log_filter_error"), "error")
        self.filter_box.addItem(_t("log_filter_success"), "success")
        self.filter_box.addItem(_t("log_filter_system"), "system")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(_t("log_search"))
        self.filter_box.currentIndexChanged.connect(self._render)
        self.search_edit.textChanged.connect(self._render)
        bar.addWidget(self.filter_box)
        bar.addWidget(self.search_edit)
        layout.addLayout(bar)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont('Consolas', 9))
        layout.addWidget(self.view)

    @staticmethod
    def _classify(text):
        s = text.strip()
        if ('[ERROR]' in s or '[ОШИБКА]' in s or '[CRITICAL' in s
                or '[КРИТИЧ' in s or s.startswith('[!')):
            return 'error'
        if s.startswith('[+]') or 'SUCCESSFULLY' in s or 'УСПЕШНО' in s:
            return 'success'
        if s.startswith('['):
            return 'system'
        return 'out'

    def append(self, text):
        self._entries.append((self._classify(text), text))
        if self._passes(*self._entries[-1]):
            self._append_html(text, self._entries[-1][0])

    def clear(self):
        self._entries.clear()
        self.view.clear()

    def toPlainText(self):
        return '\n'.join(t for _, t in self._entries)

    def _passes(self, role, text):
        flt = self.filter_box.currentData()
        if flt != 'all' and role != flt:
            return False
        needle = self.search_edit.text().strip().lower()
        return not needle or needle in text.lower()

    def set_role_colors(self, colors):
        self._role_colors = dict(colors)
        self._render()

    def _append_html(self, text, role):
        prefix = self._role_colors[role]
        weight = '600' if role == 'system' else '400'
        self.view.append(f'<span style="color:{prefix};font-weight:{weight}">'
                         f'{escape(text)}</span>')
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _render(self):
        self.view.clear()
        for role, text in self._entries:
            if self._passes(role, text):
                self._append_html(text, role)


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


# --- Main Application Window ---
class PhyMLApp(QWidget):
    def __init__(self, paths=None):
        super().__init__()
        self.paths = paths if paths is not None else AppPaths.detect()
        self.history_store = HistoryStore(self.paths.history_file)
        self._is_loading = True
        self._autosave_blocked = False  # set when the settings file could not be read
        self._save_failed = False       # the last auto_save failed (the error is logged once)
        self._extra_settings = {}       # keys of the settings file this version does not know
        self._history_records = []      # the records shown in history_list, same order
        self.worker = None
        self.fasta_file = ""
        self._mpi_auto_path = ""
        self._cpu_samples = []
        self._mon_procs = {}
        self._batch_mode = False
        self._theme_setting = 'system'
        self._accent_setting = 'green'
        self.engine_setting = 'phyml'
        self._recent = []
        self._user_presets = {}
        self._failed_files = []
        self._run_started = None
        self._last_out_dir = None
        self.phys_cores, self.logi_cores = detect_cores()
        self.initUI()
        self.load_config()
        self._is_loading = False

    # ---------- UI construction ----------

    def initUI(self):
        self.setWindowTitle(f'phymlGUI {__version__}')
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(1440, 860)
        self.setMinimumSize(1080, 600)  # must stay usable at 1366x768
        self.setAcceptDrops(True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        self.splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(self.splitter, 1)
        root_layout.addWidget(self._build_status_bar())

        self.splitter.addWidget(self._build_middle_pane())
        self.splitter.addWidget(self._build_right_pane())
        self.splitter.setSizes([340, 1040])
        self.splitter.setChildrenCollapsible(True)

        self.bind_autosave(self)  # after the whole tree is parented

    def _build_nav_panel(self):
        self.panel = QToolBox()

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._open_recent)
        self.panel.addItem(self.recent_list, _t("panel_recent"))

        self.presets_list = QListWidget()
        self.presets_list.itemDoubleClicked.connect(self._preset_activated)
        self.presets_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.presets_list.customContextMenuRequested.connect(self._preset_menu)
        self.panel.addItem(self.presets_list, _t("panel_presets"))

        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self._open_history_entry)
        self.panel.addItem(self.history_list, _t("panel_history"))
        return self.panel

    def _build_middle_pane(self):
        """FASTA input + parameter groups (each on its own plate) + controls."""
        # hidden holders for engine paths; edited via the Settings dialog
        self.phyml_path_input = QLineEdit()
        self.phyml_path_input.textChanged.connect(self.on_phyml_path_changed)
        self.mpirun_path_input = QLineEdit()
        self.muscle_path_input = QLineEdit()
        self.iqtree_path_input = QLineEdit()

        middle = QWidget()
        v = QVBoxLayout(middle)
        v.setContentsMargins(0, 0, 8, 0)  # breathing room from the right splitter
        v.setSpacing(8)

        v.addWidget(QLabel(_t("input_fasta")))
        self.fasta_path_input = QLineEdit()
        btn_fasta = QPushButton(_t("btn_select_fasta"))
        btn_fasta.clicked.connect(self.browse_fasta)
        btn_fasta_dir = QPushButton(_t("btn_select_dir"))
        btn_fasta_dir.clicked.connect(self.browse_fasta_dir)
        row = QHBoxLayout(); row.addWidget(self.fasta_path_input, 1)
        row.addWidget(btn_fasta); row.addWidget(btn_fasta_dir)
        v.addLayout(row)
        self.fasta_info_label = QLabel(' ')
        self.fasta_info_label.setStyleSheet('color: #9AA0A6;')
        self.fasta_path_input.textChanged.connect(self._update_fasta_info)
        v.addWidget(self.fasta_info_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        plates = QWidget()
        pv = QVBoxLayout(plates)
        pv.setContentsMargins(0, 0, 4, 0)
        pv.setSpacing(10)

        gb_model = QGroupBox(_t("tab_model"))
        form_basic = QFormLayout(gb_model)
        self.chk_use_mpi = QCheckBox(_t("lbl_use_mpi"))
        self.le_mpi_np = QLineEdit(str(self.phys_cores))
        self.le_mpi_np.setFixedWidth(50)
        mpi_hbox = QHBoxLayout(); mpi_hbox.addWidget(self.chk_use_mpi)
        mpi_hbox.addWidget(QLabel(_t("lbl_mpi_np"))); mpi_hbox.addWidget(self.le_mpi_np)
        mpi_hbox.addStretch()
        form_basic.addRow(_t("mode_mpi"), mpi_hbox)

        self.cb_datatype = QComboBox()
        self.cb_datatype.addItem(_t("dt_nt"), "nt")
        self.cb_datatype.addItem(_t("dt_aa"), "aa")
        self.cb_datatype.currentIndexChanged.connect(self.update_models)
        form_basic.addRow(_t("lbl_dt"), self.cb_datatype)

        self.cb_model = QComboBox()
        form_basic.addRow(_t("lbl_model"), self.cb_model)

        self.cb_support_method = QComboBox()
        self.cb_support_method.addItem(_t("supp_boot"), "bootstrap")
        self.cb_support_method.addItem(_t("supp_alrt1"), "-1"); self.cb_support_method.addItem(_t("supp_alrt2"), "-2")
        self.cb_support_method.addItem(_t("supp_alrt4"), "-4"); self.cb_support_method.addItem(_t("supp_none"), "0")
        self.cb_support_method.currentIndexChanged.connect(self.toggle_bootstrap_input)
        form_basic.addRow(_t("lbl_supp"), self.cb_support_method)

        self.le_bootstrap_replicates = QLineEdit("100")
        form_basic.addRow(_t("lbl_boot"), self.le_bootstrap_replicates)
        pv.addWidget(gb_model)

        gb_evo = QGroupBox(_t("tab_evo"))
        form_model = QFormLayout(gb_evo)
        self.cb_freq = QComboBox()
        self.cb_freq.addItem(_t("freq_def"), "default"); self.cb_freq.addItem(_t("freq_emp"), "e"); self.cb_freq.addItem(_t("freq_ml"), "m")
        form_model.addRow(_t("lbl_freq"), self.cb_freq)
        self.le_tstv = QLineEdit("e"); form_model.addRow(_t("lbl_tstv"), self.le_tstv)
        self.le_pinv = QLineEdit("0.0"); form_model.addRow(_t("lbl_pinv"), self.le_pinv)
        self.le_classes = QLineEdit("4"); form_model.addRow(_t("lbl_classes"), self.le_classes)
        self.le_gamma = QLineEdit("e"); form_model.addRow(_t("lbl_gamma"), self.le_gamma)
        pv.addWidget(gb_evo)

        gb_search = QGroupBox(_t("tab_search"))
        form_tree = QFormLayout(gb_search)
        self.cb_search = QComboBox()
        self.cb_search.addItem(_t("search_nni"), "NNI"); self.cb_search.addItem(_t("search_spr"), "SPR"); self.cb_search.addItem(_t("search_best"), "BEST")
        form_tree.addRow(_t("lbl_search"), self.cb_search)
        self.cb_optimize = QComboBox()
        self.cb_optimize.addItem(_t("opt_tlr"), "tlr"); self.cb_optimize.addItem(_t("opt_tl"), "tl"); self.cb_optimize.addItem(_t("opt_lr"), "lr")
        self.cb_optimize.addItem(_t("opt_l"), "l"); self.cb_optimize.addItem(_t("opt_r"), "r"); self.cb_optimize.addItem(_t("opt_n"), "n")
        form_tree.addRow(_t("lbl_opt"), self.cb_optimize)
        self.chk_parsimony = QCheckBox(_t("chk_pars"))
        form_tree.addRow(self.chk_parsimony)
        pv.addWidget(gb_search)
        pv.addStretch(1)

        scroll.setWidget(plates)
        v.addWidget(scroll, 1)

        # navigation (recent/presets/history) lives at the bottom of the column
        self._build_nav_panel()
        self.panel.setMaximumHeight(230)
        v.addWidget(self.panel)

        control_row = QHBoxLayout()
        self.btn_run = QPushButton(_t("btn_run"))
        self.btn_run.setObjectName('btn_run')
        self.btn_run.clicked.connect(lambda: self.start_pipeline())  # clicked(bool) must not leak into files_override
        self.btn_cancel = QPushButton(_t("btn_cancel"))
        self.btn_cancel.setObjectName('btn_cancel')
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_pipeline)
        self.chk_show_tree = QCheckBox(_t("chk_show"))
        self.chk_show_tree.setChecked(True)
        control_row.addWidget(self.btn_run)
        control_row.addWidget(self.btn_cancel)
        control_row.addStretch(1)
        control_row.addWidget(self.chk_show_tree)
        v.addLayout(control_row)
        return middle

    def _build_right_pane(self):
        """Big tree viewer on top, Log/Stats/Summary tabs underneath."""
        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(8, 0, 0, 0)  # breathing room from the left splitter
        self.tree_view = TreeViewerWidget()

        self.result_tabs = QTabWidget()
        self.log_console = LogConsole()
        self.result_tabs.addTab(self.log_console, _t("tab_log"))

        stats_tab = QWidget()
        stats_lay = QVBoxLayout(stats_tab)
        self.stats_file_label = QLabel("—")
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.horizontalHeader().setVisible(False)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        stats_lay.addWidget(self.stats_file_label)
        stats_lay.addWidget(self.stats_table)
        self.result_tabs.addTab(stats_tab, _t("tab_stats"))

        self.summary_table = QTableWidget(0, 8)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 8):
            self.summary_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.result_tabs.addTab(self.summary_table, _t("tab_summary"))

        queue_tab = QWidget()
        queue_lay = QVBoxLayout(queue_tab)
        self.queue_list = QListWidget()
        self.queue_list.setAlternatingRowColors(True)
        self.retry_btn = QToolButton()
        self.retry_btn.setText(_t("btn_retry_failed"))
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self._retry_failed)
        queue_lay.addWidget(self.queue_list, 1)
        queue_lay.addWidget(self.retry_btn)
        self.result_tabs.addTab(queue_tab, _t("tab_queue"))

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.tree_view)
        split.addWidget(self.result_tabs)
        split.setSizes([470, 260])
        split.setChildrenCollapsible(False)
        self.right_split = split
        v.addWidget(split, 1)
        return right

    def _build_status_bar(self):
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.cores_label = QLabel(_t("cores_info").format(self.phys_cores, self.logi_cores))
        self.cpu_sys_label = QLabel(_t("cpu_sys").format(0))
        self.cpu_sys_bar = QProgressBar()
        self.cpu_sys_bar.setRange(0, 100)
        self.cpu_sys_bar.setTextVisible(True)
        self.cpu_sys_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.cpu_run_label = QLabel(_t("cpu_analysis_idle"))
        self.open_dir_btn = QToolButton()
        self.open_dir_btn.setText(_t("btn_open_dir"))
        self.open_dir_btn.setEnabled(False)
        self.open_dir_btn.clicked.connect(self._open_output_dir)
        self.settings_btn = QPushButton(_t("btn_settings"))
        self.settings_btn.clicked.connect(self.open_settings)
        self.status_bar.addWidget(self.cores_label)
        self.status_bar.addWidget(self.cpu_sys_label)
        self.status_bar.addWidget(self.cpu_sys_bar, 1)  # stretch: fills all free space
        self.status_bar.addPermanentWidget(self.cpu_run_label)
        self.status_bar.addPermanentWidget(self.open_dir_btn)
        self.status_bar.addPermanentWidget(self.settings_btn)  # far bottom-right corner

        self.cpu_timer = QTimer(self)
        self.cpu_timer.setInterval(1000)
        self.cpu_timer.timeout.connect(self.update_cpu_status)
        if psutil is not None:
            self.cpu_timer.start()
        return self.status_bar

    # ---------- drag & drop ----------

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            p = urls[0].toLocalFile()
            if os.path.isdir(p) or p.lower().endswith(('.fasta', '.fas', '.fa')):
                event.acceptProposedAction()

    def dropEvent(self, event):
        p = event.mimeData().urls()[0].toLocalFile()
        self.fasta_path_input.setText(p)
        self.fasta_file = p
        event.acceptProposedAction()

    # ---------- panel / theme / settings helpers ----------

    def open_settings(self):
        SettingsDialog(self, self).exec()

    def apply_theme(self, theme_setting=None, accent_setting=None):
        """Resolve settings (with 'system' support), style the app and the log."""
        from PySide6.QtWidgets import QApplication
        if theme_setting is not None:
            self._theme_setting = theme_setting
        if accent_setting is not None:
            self._accent_setting = accent_setting
        theme, accent = resolve(self._theme_setting, self._accent_setting)
        QApplication.instance().setStyleSheet(build_qss(theme, accent))
        self.log_console.set_role_colors(role_colors(theme, accent))
        pal = PALETTES[theme]
        self.tree_view.set_colors(pal['text'], accent, pal['base'])

    def _refresh_recent(self):
        self.recent_list.clear()
        for p in self._recent:
            self.recent_list.addItem(os.path.basename(p) + ('/' if os.path.isdir(p) else ''))

    def _remember_recent(self, path):
        if path in self._recent:
            self._recent.remove(path)
        self._recent.insert(0, path)
        self._recent = self._recent[:10]
        self._refresh_recent()

    def _open_recent(self, item):
        row = self.recent_list.row(item)
        if row < len(self._recent) and os.path.exists(self._recent[row]):
            p = self._recent[row]
            self.fasta_path_input.setText(p)
            self.fasta_file = p

    # ---------- pipeline plumbing ----------

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        self.auto_save()  # persist window geometry and splitter ratios
        event.accept()

    def toggle_bootstrap_input(self):
        is_bootstrap = self.cb_support_method.currentData() == "bootstrap"
        self.le_bootstrap_replicates.setEnabled(is_bootstrap)
        if not self._is_loading: self.auto_save()

    def update_models(self):
        self.cb_model.clear()
        if self.engine_setting == 'iqtree':
            models = ["MFP", "GTR+F+G4", "HKY+F+G4", "TIM2+F+G4", "TVM+F+G4"] \
                if self.cb_datatype.currentData() == "nt" else \
                ["MFP", "LG+G4", "WAG+G4", "JTT+G4", "mtREV+G4"]
        else:
            models = ["HKY85", "JC69", "K80", "F81", "F84", "TN93", "GTR", "custom"] if self.cb_datatype.currentData() == "nt" else \
                     ["LG", "WAG", "JTT", "MtREV", "Dayhoff", "DCMut", "RtREV", "CPREV", "VT", "Blosum62", "MtMam", "MtArt", "HIVw", "HIVb", "custom"]
        for m in models: self.cb_model.addItem(m, m)
        if not self._is_loading: self.auto_save()

    def _update_fasta_info(self, path):
        """Quick alignment summary under the FASTA field."""
        try:
            if not path or not os.path.exists(path):
                self.fasta_info_label.setText(' ')
                return
            if os.path.isdir(path):
                n = sum(1 for f in os.listdir(path)
                        if f.lower().endswith(('.fasta', '.fas', '.fa'))
                        and not f.lower().endswith('_aligned.fasta'))
                self.fasta_info_label.setText(_t('fasta_info').format(n, '—', '—', '—'))
                return
            from Bio import SeqIO
            lengths = [len(r.seq) for r in SeqIO.parse(path, 'fasta')]
            if not lengths:
                self.fasta_info_label.setText(' ')
                return
            gaps = 0
            total = sum(lengths)
            for r in SeqIO.parse(path, 'fasta'):
                gaps += str(r.seq).count('-')
            pct = round(gaps / total * 100, 1) if total else 0
            self.fasta_info_label.setText(
                _t('fasta_info').format(len(lengths), min(lengths), max(lengths), pct))
        except Exception:
            self.fasta_info_label.setText(' ')

    def browse_fasta(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("file_fasta"), "", "FASTA Files (*.fasta *.fas *.fa)")
        if path:
            self.fasta_path_input.setText(path)
            self.fasta_file = path

    def browse_fasta_dir(self):
        path = QFileDialog.getExistingDirectory(self, _t("file_dir"))
        if path:
            self.fasta_path_input.setText(path)
            self.fasta_file = path

    def bind_autosave(self, parent_widget):
        for child in parent_widget.children():
            if isinstance(child, QLineEdit): child.textChanged.connect(self.trigger_autosave)
            elif isinstance(child, QComboBox): child.currentIndexChanged.connect(self.trigger_autosave)
            elif isinstance(child, QCheckBox): child.toggled.connect(self.trigger_autosave)
            else: self.bind_autosave(child)

    def trigger_autosave(self, *args):
        if not self._is_loading: self.auto_save()

    def get_current_config(self):
        return {
            "engine": self.engine_setting,
            "iqtree_path": self.iqtree_path_input.text(),
            "phyml_path": self.phyml_path_input.text(),
            "mpirun_path": self.mpirun_path_input.text(),
            "muscle_path": self.muscle_path_input.text(),
            "datatype": self.cb_datatype.currentData(),
            "model": self.cb_model.currentData(),
            "support_method": self.cb_support_method.currentData(),
            "bootstrap_replicates": self.le_bootstrap_replicates.text(),
            "use_mpi": self.chk_use_mpi.isChecked(),
            "mpi_np": self.le_mpi_np.text(),
            "freq": self.cb_freq.currentData(),
            "tstv": self.le_tstv.text(),
            "pinv": self.le_pinv.text(),
            "classes": self.le_classes.text(),
            "gamma": self.le_gamma.text(),
            "search": self.cb_search.currentData(),
            "optimize": self.cb_optimize.currentData(),
            "parsimony": self.chk_parsimony.isChecked(),
            "show_tree": self.chk_show_tree.isChecked(),
            "theme": self._theme_setting,
            "accent": self._accent_setting,
            "recent": self._recent,
            "presets": self._user_presets,
            "window": {
                "w": self.width(), "h": self.height(),
                "splitter": self.splitter.sizes(),
                "vsplit": self.right_split.sizes(),
            }
        }

    def _log(self, text):
        """A system line for the log; messages from the core modules may end with a newline."""
        self.log_console.append(text.rstrip('\n'))

    def auto_save(self):
        if self._autosave_blocked:
            return
        data = dict(self._extra_settings)
        data.update(settings.to_disk(self.get_current_config(), self.paths))
        data['schema_version'] = settings.SCHEMA_VERSION
        try:
            settings.save(self.paths.config_file, data)
            self._save_failed = False
        except OSError as e:
            if not self._save_failed:   # every field change saves: report a failure once
                self._log(_t('err_settings_save').format(e))
            self._save_failed = True

    def _migrate_legacy_files(self):
        """Copy config/history from the working folder of older versions, once."""
        try:
            cwd = os.getcwd()
            copied = settings.migrate_legacy(self.paths, cwd)
        except OSError as e:
            self._log(_t('err_load').format(e))
            return
        for name in copied:
            self._log(_t('settings_migrated').format(
                os.path.join(cwd, name), os.path.join(self.paths.data_dir, name)))

    def load_config(self):
        self.update_models()
        self._migrate_legacy_files()
        problems = []
        try:
            raw = settings.load(self.paths.config_file, on_error=problems.append)
        except OSError as e:
            # The file is there but unreadable: work with defaults, but never save them
            # over the user's real settings.
            self._autosave_blocked = True
            problems.append(_t('err_load').format(e))
            raw = copy.deepcopy(settings.DEFAULTS)
        for message in problems:
            self._log(message)
        self._extra_settings = {k: v for k, v in raw.items() if k not in settings.DEFAULTS}
        try:
            self._apply_config(settings.from_disk(raw, self.paths))
            if not problems and os.path.isfile(self.paths.config_file):
                self._log(_t("sys_load"))
        except Exception as e:
            self._log(_t("err_load").format(e))
        # lists must be populated even without a config file
        self._refresh_presets()
        self._refresh_history()

    def _apply_config(self, config):
        """Show a settings dict (as returned by settings.from_disk) in the window."""
        self.engine_setting = config["engine"]
        self.iqtree_path_input.setText(config["iqtree_path"])
        self.phyml_path_input.setText(config["phyml_path"])
        mpirun = config["mpirun_path"]
        if mpirun in ("mpirun", "mpiexec"):
            mpirun = shutil.which("mpiexec") or shutil.which("mpirun") or mpirun
        self.mpirun_path_input.setText(mpirun)
        self.muscle_path_input.setText(config["muscle_path"])
        self._apply_model_params(config)
        self.chk_use_mpi.setChecked(config["use_mpi"])
        self.le_mpi_np.setText(config["mpi_np"] or str(self.phys_cores))  # '' = physical cores
        self.chk_show_tree.setChecked(config["show_tree"])
        self._recent = [p for p in config["recent"] if isinstance(p, str) and os.path.exists(p)]
        self._refresh_recent()
        self._user_presets = dict(config["presets"])
        self.apply_theme(config["theme"], config["accent"])
        win = config["window"]
        if win.get("w") and win.get("h"):
            self.resize(min(win["w"], 4096), min(win["h"], 4096))
        if isinstance(win.get("splitter"), list) and len(win["splitter"]) == 2:
            self.splitter.setSizes(win["splitter"])
        if isinstance(win.get("vsplit"), list) and len(win["vsplit"]) == 2:
            self.right_split.setSizes(win["vsplit"])
        self.toggle_bootstrap_input()

    def _apply_model_params(self, params):
        """Show the model and search parameters (the part presets also carry)."""
        self.set_combo_by_data(self.cb_datatype, params["datatype"])
        self.update_models()
        self.set_combo_by_data(self.cb_model, params["model"])
        self.set_combo_by_data(self.cb_freq, params["freq"])
        self.set_combo_by_data(self.cb_support_method, params["support_method"])
        self.set_combo_by_data(self.cb_search, params["search"])
        self.set_combo_by_data(self.cb_optimize, params["optimize"])
        self.le_bootstrap_replicates.setText(params["bootstrap_replicates"])
        self.le_tstv.setText(params["tstv"])
        self.le_pinv.setText(params["pinv"])
        self.le_classes.setText(params["classes"])
        self.le_gamma.setText(params["gamma"])
        self.chk_parsimony.setChecked(params["parsimony"])

    def set_combo_by_data(self, combo, data_val):
        idx = combo.findData(data_val)
        if idx >= 0: combo.setCurrentIndex(idx)

    def start_pipeline(self, files_override=None):
        if isinstance(files_override, bool):  # defensive: Qt clicked(checked)
            files_override = None
        if files_override is None:
            target = self.fasta_path_input.text() or self.fasta_file
            if not target or not os.path.exists(target):
                QMessageBox.warning(self, _t("err_box_title"), _t("err_box_msg")); return
            if os.path.isdir(target):
                # skip *_aligned.fasta: those are this app's own MUSCLE outputs
                files = sorted(f for f in os.listdir(target)
                               if f.lower().endswith(('.fasta', '.fas', '.fa'))
                               and not f.lower().endswith('_aligned.fasta'))
                if not files:
                    QMessageBox.warning(self, _t("err_box_title"), _t("batch_empty")); return
                files = [os.path.join(target, f) for f in files]
            else:
                files = [target]
        else:
            files = list(files_override)
        if self.engine_setting == 'iqtree':
            if not self.iqtree_path_input.text() or not os.path.exists(self.iqtree_path_input.text()):
                QMessageBox.warning(self, _t("err_box_title"), _t("err_iqtree")); return
        elif (is_mpi_binary(self.phyml_path_input.text())
                and not self.chk_use_mpi.isChecked()
                and self.cb_support_method.currentData() == "bootstrap"):
            QMessageBox.warning(self, _t("mpi_boot_title"), _t("mpi_boot_msg")); return
        self._batch_mode = len(files) > 1
        self._remember_recent(target if files_override is None else os.path.dirname(files[0]))
        if not self._is_loading: self.auto_save()
        self.btn_run.setEnabled(False); self.btn_cancel.setEnabled(True); self.log_console.clear()
        self.result_tabs.setCurrentWidget(self.log_console)
        self._populate_queue(files)
        if self._batch_mode:
            self.result_tabs.setCurrentWidget(self.queue_list.parentWidget())
        self._cpu_samples = []
        self._mon_procs = {}
        self._run_started = datetime.now()
        config = self.get_current_config()
        self.worker = PipelineWorker(config, files)
        self.worker.log_signal.connect(self.log_console.append)
        self.worker.file_status_signal.connect(self._on_file_status)
        self.worker.finished_signal.connect(self.pipeline_finished)
        self.worker.start()

    def cancel_pipeline(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.log_console.append(_t("sys_interrupt"))

    def pipeline_finished(self, success, tree_path):
        self.btn_run.setEnabled(True); self.btn_cancel.setEnabled(False)
        avg = sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else 0.0
        self.cpu_run_label.setText(_t("cpu_analysis_done").format(int(avg), round(avg / 100, 1)))
        if self.worker is not None and getattr(self.worker, 'results', None):
            self._populate_stats()
            self._populate_summary()
            self._save_summary_csv()
        n_ok = sum(1 for r in getattr(self.worker, 'results', []) if r['status'] == 'OK')
        n_all = len(getattr(self.worker, 'results', []))
        self._append_history(n_ok, n_all, tree_path)
        self._failed_files = [f for f, r in zip(getattr(self.worker, 'fasta_files', []),
                                                getattr(self.worker, 'results', []))
                              if r.get('status') == 'FAIL']
        self.retry_btn.setVisible(bool(self._failed_files))
        target = self.fasta_path_input.text() or self.fasta_file
        if target and os.path.isdir(target):
            self._last_out_dir = target
        elif getattr(self.worker, 'fasta_files', None):
            self._last_out_dir = os.path.dirname(os.path.abspath(self.worker.fasta_files[0]))
        self.open_dir_btn.setEnabled(self._last_out_dir is not None)
        if success and tree_path and os.path.exists(tree_path) and self.chk_show_tree.isChecked():
            self.tree_view.load_tree(tree_path)

    # ---------- queue ----------

    def _populate_queue(self, files):
        self.queue_list.clear()
        for f in files:
            self.queue_list.addItem(os.path.basename(f) + '  …')

    def _on_file_status(self, name, status):
        marker = {'pending': '…', 'running': '▶', 'ok': '✓', 'fail': '✗'}.get(status, '?')
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.text().split('  ')[0] == name:
                item.setText(f'{name}  {marker}')
                return

    def _retry_failed(self):
        if self._failed_files:
            self.start_pipeline(files_override=self._failed_files)

    def _open_output_dir(self):
        if self._last_out_dir and os.path.isdir(self._last_out_dir):
            os.startfile(self._last_out_dir)

    # ---------- history ----------

    def _append_history(self, n_ok, n_all, tree_path):
        """Add the finished run to the history, as the worker's rows describe it.

        The counts and the best tree follow from those rows, so n_ok, n_all and tree_path
        only keep the signature of the call.
        """
        worker = self.worker
        fasta_files = list(getattr(worker, 'fasta_files', None) or [])
        rows = list(getattr(worker, 'results', None) or [])
        config = getattr(worker, 'config', None)   # what the run used, not what the form shows now
        if not isinstance(config, dict):
            config = self.get_current_config()
        params = {k: v for k, v in config.items() if k not in _NOT_RUN_PARAMS}
        files = [{'file': path,
                  'status': 'ok' if row.get('status') == 'OK' else 'fail',
                  'tree': row.get('tree', ''),
                  'stats': {k: row.get(k, '') for k in _STAT_KEYS},
                  'error': row.get('error', '')}
                 for path, row in zip(fasta_files, rows)]
        target = self.fasta_path_input.text() or self.fasta_file or (fasta_files[0] if fasta_files else '')
        duration = (datetime.now() - self._run_started).total_seconds() if self._run_started else 0.0
        rec = new_record(inputs=[target] if target else [],
                         engine=params.get('engine') or self.engine_setting,
                         params=params, files=files, duration_s=duration)
        try:
            self.history_store.append(rec)
        except OSError as e:
            self._log(_t('err_settings_save').format(e))
        self._refresh_history()

    def _refresh_history(self):
        self.history_list.clear()
        try:
            self._history_records = self.history_store.load(on_error=self._log)[:50]
        except OSError as e:
            self._history_records = []
            self._log(_t('err_load').format(e))
        for rec in self._history_records:
            self.history_list.addItem(_t('hist_entry').format(
                rec.get('ts', ''), display_input(rec), rec.get('ok', 0), rec.get('n', 0)))

    def _open_history_entry(self, item):
        row = self.history_list.row(item)
        if row >= len(self._history_records):
            return
        tree = best_tree(self._history_records[row])
        if tree and os.path.exists(tree):
            self.tree_view.load_tree(tree)
        else:
            self.log_console.append(_t('hist_no_tree'))

    # ---------- presets ----------

    def _refresh_presets(self):
        self.presets_list.clear()
        save_item = QListWidgetItem(_t('preset_save_current'))
        save_item.setData(Qt.UserRole, '__save__')
        self.presets_list.addItem(save_item)
        for label_key in presets.BUILTIN:
            it = QListWidgetItem(_t(label_key))
            it.setData(Qt.UserRole, ('builtin', label_key))
            self.presets_list.addItem(it)
        for name in self._user_presets:
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, ('user', name))
            self.presets_list.addItem(it)

    def _preset_activated(self, item):
        data = item.data(Qt.UserRole)
        if data == '__save__':
            self._save_preset()
            return
        kind, key = data
        preset = presets.BUILTIN[key] if kind == 'builtin' else self._user_presets.get(key, {})
        self._apply_preset(preset)
        self.log_console.append(_t('preset_applied').format(item.text()))

    def _apply_preset(self, preset):
        params = presets.apply(preset, self.get_current_config())
        self._is_loading = True
        try:
            self.engine_setting = params['engine']
            self._apply_model_params(params)
        finally:
            self._is_loading = False
        self.toggle_bootstrap_input()
        self.auto_save()

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, _t('preset_save_current'), _t('preset_prompt'))
        if not ok or not name.strip():
            return
        name = name.strip()
        self._user_presets[name] = presets.extract(self.get_current_config())
        self.auto_save()
        self._refresh_presets()
        self.log_console.append(_t('preset_saved').format(name))

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
            self._user_presets.pop(data[1], None)
            self.auto_save()
            self._refresh_presets()

    def _populate_stats(self):
        rows = [r for r in self.worker.results if r['status'] == 'OK']
        if not rows:
            return
        r = rows[-1]
        self.stats_file_label.setText(_t("stats_field_file") + ': ' + r['file'])
        fields = [('stats_field_model', 'model'), ('stats_field_taxa', 'taxa'),
                  ('stats_field_lnl', 'lnL'), ('stats_field_gamma', 'gamma'),
                  ('stats_field_tstv', 'tstv'), ('stats_field_time', 'time')]
        self.stats_table.setRowCount(len(fields))
        for i, (key, col) in enumerate(fields):
            self.stats_table.setItem(i, 0, QTableWidgetItem(_t(key)))
            self.stats_table.setItem(i, 1, QTableWidgetItem(r.get(col) or 'n/a'))

    def _populate_summary(self):
        cols = ['file', 'status', 'model', 'taxa', 'lnL', 'gamma', 'tstv', 'time']
        heads = [_t("sum_col_" + c) for c in cols]
        self.summary_table.setColumnCount(len(cols))
        self.summary_table.setHorizontalHeaderLabels(heads)
        self.summary_table.setRowCount(len(self.worker.results))
        for i, r in enumerate(self.worker.results):
            for j, c in enumerate(cols):
                self.summary_table.setItem(i, j, QTableWidgetItem(r.get(c) or ''))

    def _save_summary_csv(self):
        """Write per-file results (status, model, lnL, ...) to phymlgui_summary.csv."""
        target = self.fasta_path_input.text() or self.fasta_file
        out_dir = target if os.path.isdir(target) else os.path.dirname(os.path.abspath(target))
        out_path = os.path.join(out_dir, 'phymlgui_summary.csv')
        fields = ['file', 'status', 'model', 'taxa', 'lnL', 'gamma', 'tstv', 'time', 'tree']
        try:
            with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
                wr = csv.DictWriter(f, fieldnames=fields, delimiter=';', extrasaction='ignore')
                wr.writeheader()
                wr.writerows(self.worker.results)
            self.log_console.append(_t("summary_saved").format(out_path))
        except OSError as e:
            self.log_console.append(_t("err_summary_save").format(e))
        # optional Excel workbook with the same data (needs openpyxl)
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = 'Summary'
            ws.append([_t("sum_col_" + c) for c in fields[:-1]])
            for r in self.worker.results:
                ws.append([r.get(c) or '' for c in fields[:-1]])
            for col, width in zip('ABCDEFGHI', (28, 8, 16, 8, 12, 10, 10, 12)):
                ws.column_dimensions[col].width = width
            xlsx_path = out_path[:-4] + '.xlsx'
            wb.save(xlsx_path)
            self.log_console.append(_t("xlsx_saved").format(xlsx_path))
        except ImportError:
            pass
        except Exception as e:
            self.log_console.append(_t("err_summary_save").format(e))

    def on_phyml_path_changed(self, path):
        if is_mpi_binary(path):
            if not self.chk_use_mpi.isChecked() and self._mpi_auto_path != path:
                self._mpi_auto_path = path
                self.chk_use_mpi.setChecked(True)
                if not self._is_loading:
                    self.log_console.append(_t("mpi_detected"))
        else:
            self._mpi_auto_path = ""

    def update_cpu_status(self):
        if psutil is None:
            return
        sys_pct = psutil.cpu_percent(interval=None)
        self.cpu_sys_bar.setValue(int(sys_pct))
        self.cpu_sys_label.setText(_t("cpu_sys").format(int(sys_pct)))
        proc = self.worker.active_process if self.worker is not None else None
        if (self.worker is not None and self.worker.isRunning()
                and proc is not None and proc.poll() is None):
            try:
                root = psutil.Process(proc.pid)
                pids = {proc.pid} | {c.pid for c in root.children(recursive=True)}
            except psutil.Error:
                return
            # cpu_percent() keeps per-call state inside each Process object,
            # so objects must be reused across ticks to get non-zero values
            for k in list(self._mon_procs):
                if k not in pids:
                    del self._mon_procs[k]
            total = 0.0
            for p in pids:
                obj = self._mon_procs.get(p)
                if obj is None:
                    try:
                        obj = self._mon_procs[p] = psutil.Process(p)
                    except psutil.Error:
                        continue
                try:
                    total += obj.cpu_percent(interval=None)
                except psutil.Error:
                    pass
            self._cpu_samples.append(total)
            self.cpu_run_label.setText(_t("cpu_analysis").format(int(total), round(total / 100, 1)))
