import copy
import os
import shutil
from dataclasses import asdict
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QFormLayout, QComboBox, QLineEdit, QPushButton,
                             QFileDialog, QMessageBox, QTabWidget,
                             QCheckBox, QGroupBox, QLabel, QSplitter, QToolBox,
                             QToolButton, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem,
                             QHeaderView, QScrollArea, QMenu, QInputDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QShortcut, QKeySequence

from phyml_core import __version__, alignment, presets, report, settings
from phyml_core.engines import ENGINES
from phyml_core.engines.base import format_issue
from phyml_core.history import HistoryStore, best_tree, display_input, new_record
from phyml_core.i18n import _t
from phyml_core.paths import AppPaths
from phyml_core.utils import detect_cores, is_mpi_binary, resource_path
from phyml_ui.tree_viewer import TreeViewerWidget
from phyml_ui.themes import resolve, build_qss, role_colors, PALETTES
from phyml_ui.log_console import LogConsole
from phyml_ui.settings_dialog import SettingsDialog
from phyml_ui.status_bar import AppStatusBar
from phyml_ui.worker import RunWorker

# queue marker per file status of the runner
_STATUS_MARKERS = {'pending': '…', 'running': '▶', 'ok': '✓', 'fail': '✗',
                   'cancelled': '⊘'}
# settings that say nothing about how a run was made: left out of a history record
_NOT_RUN_PARAMS = ('presets', 'recent', 'window')


# --- Main Application Window ---
class PhyMLApp(QWidget):
    def __init__(self, paths=None, engines=None):
        super().__init__()
        self.paths = paths if paths is not None else AppPaths.detect()
        self.engines = ENGINES if engines is None else engines   # tests pass fakes
        self.history_store = HistoryStore(self.paths.history_file)
        self._is_loading = True
        self._autosave_blocked = False  # set when the settings file could not be read
        self._save_failed = False       # the last auto_save failed (the error is logged once)
        self._extra_settings = {}       # keys of the settings file this version does not know
        self._history_records = []      # the records shown in history_list, same order
        self.worker = None
        self.fasta_file = ""
        self._mpi_auto_path = ""
        self._batch_mode = False
        self._theme_setting = 'system'
        self._accent_setting = 'green'
        self.engine_setting = 'phyml'
        self._recent = []
        self._user_presets = {}
        self._failed_files = []
        self._run_started = None
        self._run_config = None         # the config the current/last run was started with
        self._run_inputs = []           # what that run was asked to process (history 'inputs')
        self._run_out_dir = None        # where its summary goes
        self._last_out_dir = None
        self.last_result = None         # RunResult of the last finished run
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
        self.status = AppStatusBar(self.phys_cores, self.logi_cores)
        self.status.open_dir_clicked.connect(self._open_output_dir)
        self.status.settings_clicked.connect(self.open_settings)
        root_layout.addWidget(self.status)

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
            # synchronous: after close the process may exit and cut off a daemon thread,
            # leaving phyml-mpi / smpd children alive
            self.worker.cancel(block=True)
            self.worker.wait()
        self.auto_save()  # persist window geometry and splitter ratios
        event.accept()

    def toggle_bootstrap_input(self):
        is_bootstrap = self.cb_support_method.currentData() == "bootstrap"
        self.le_bootstrap_replicates.setEnabled(is_bootstrap)
        if not self._is_loading: self.auto_save()

    def update_models(self):
        self.cb_model.clear()
        # an unknown engine in a hand-edited config gets PhyML's list, as a run uses PhyML for it
        engine = self.engines.get(self.engine_setting) or ENGINES['phyml']
        for m in engine.models(self.cb_datatype.currentData()):
            self.cb_model.addItem(m, m)
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
            info = alignment.summarize(path)  # an empty or broken file raises: no label
            self.fasta_info_label.setText(_t('fasta_info').format(
                info['n'], info['min_len'], info['max_len'], info['gap_pct']))
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

    def _log(self, level, text):
        """A log line at the given level; messages from the core modules may end with a newline."""
        self.log_console.append(level, text.rstrip('\n'))

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
                self._log('error', _t('err_settings_save').format(e))
            self._save_failed = True

    def _migrate_legacy_files(self):
        """Copy config/history from the working folder of older versions, once."""
        try:
            cwd = os.getcwd()
            copied = settings.migrate_legacy(self.paths, cwd)
        except OSError as e:
            self._log('error', _t('err_load').format(e))
            if not os.path.exists(self.paths.config_file):
                # Saving the defaults now would create the config that closes the migration
                # gate, and the legacy settings would never be copied.
                self._autosave_blocked = True
            return
        for name in copied:
            self._log('system', _t('settings_migrated').format(
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
            self._log('error', message)
        self._extra_settings = {k: v for k, v in raw.items() if k not in settings.DEFAULTS}
        try:
            self._apply_config(settings.from_disk(raw, self.paths))
            if not problems and os.path.isfile(self.paths.config_file):
                self._log('system', _t("sys_load"))
        except Exception as e:
            self._log('error', _t("err_load").format(e))
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
        if self.worker is not None and self.worker.isRunning():
            return   # one run at a time: replacing a running worker would destroy its thread
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
                out_dir = target
            else:
                files = [target]
                out_dir = os.path.dirname(os.path.abspath(target))
            inputs = [target]
        else:
            files = list(files_override)
            if not files:
                return
            target = os.path.dirname(files[0])
            out_dir = os.path.dirname(os.path.abspath(files[0]))
            inputs = list(files)
        config = self.get_current_config()
        if config.get('engine') not in self.engines:
            config['engine'] = 'phyml'   # a hand-edited unknown engine: PhyML, as its model list
        errors = [issue for issue in self.engines[config['engine']].validate(config, self.paths)
                  if issue.level == 'error']
        if errors:
            QMessageBox.warning(self, _t('err_box_title'),
                                '\n'.join(format_issue(issue) for issue in errors))
            return
        self._batch_mode = len(files) > 1
        self._remember_recent(target)
        if not self._is_loading: self.auto_save()
        self.btn_run.setEnabled(False); self.btn_cancel.setEnabled(True); self.log_console.clear()
        self.retry_btn.setVisible(False)
        self.result_tabs.setCurrentWidget(self.log_console)
        self._populate_queue(files)
        if self._batch_mode:
            self.result_tabs.setCurrentWidget(self.queue_list.parentWidget())
        self.status.track(self._active_pid)
        self._run_started = datetime.now()
        self._run_config = config
        self._run_inputs = inputs
        self._run_out_dir = out_dir
        self.worker = RunWorker.for_run(config, files, self.paths, engines=self.engines)
        self.worker.log.connect(self._log)
        self.worker.status.connect(self._on_file_status)
        self.worker.done.connect(self.pipeline_finished)
        self.worker.start()

    def _active_pid(self):
        """The root pid of the running analysis, for the CPU monitor."""
        if self.worker is not None and self.worker.isRunning():
            return self.worker.active_pid
        return None

    def cancel_pipeline(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()   # returns at once; the kill runs on its own thread
            self.btn_cancel.setEnabled(False)
            self._log('error', _t("sys_interrupt"))

    def pipeline_finished(self, result):
        """Show a finished run (a RunResult): tables, summary files, history, retry, tree."""
        if self.worker is not None:
            self.worker.wait()   # done is emitted at the end of run(): this returns at once
        self.last_result = result
        self.btn_run.setEnabled(True); self.btn_cancel.setEnabled(False)
        self.status.stop_tracking()
        if result.files:
            rows = report.summary_rows(result.files)
            self._populate_stats(result)
            self._populate_summary(rows)
            self._write_summary(rows)
        self._append_history(result)
        self._failed_files = [f.file for f in result.files if f.status == 'fail']
        self.retry_btn.setVisible(bool(self._failed_files))
        self._last_out_dir = self._run_out_dir
        self.status.set_open_dir_enabled(self._last_out_dir is not None)
        if result.success and self.chk_show_tree.isChecked():
            tree = result.files[-1].tree
            if tree and os.path.exists(tree):
                self.tree_view.load_tree(tree)

    def _write_summary(self, rows):
        """phymlgui_summary.csv (and .xlsx) next to the inputs; a failure is only logged."""
        try:
            written = report.write_summary(rows, self._run_out_dir)
        except Exception as e:   # OSError, and whatever openpyxl raises after the CSV
            self._log('error', _t("err_summary_save").format(e))
            return
        for path in written:
            key = 'xlsx_saved' if path.lower().endswith('.xlsx') else 'summary_saved'
            self._log('success', _t(key).format(path))

    # ---------- queue ----------

    def _populate_queue(self, files):
        self.queue_list.clear()
        for f in files:
            self.queue_list.addItem(os.path.basename(f) + '  …')

    def _on_file_status(self, name, status):
        marker = _STATUS_MARKERS.get(status, '?')
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

    def _append_history(self, result):
        """Add a finished run (a RunResult) to the history: one entry per file, with the
        config the run was started with, not what the form shows now."""
        config = self._run_config if isinstance(self._run_config, dict) else self.get_current_config()
        params = {k: v for k, v in config.items() if k not in _NOT_RUN_PARAMS}
        duration = (datetime.now() - self._run_started).total_seconds() if self._run_started else 0.0
        rec = new_record(inputs=self._run_inputs,
                         engine=params.get('engine') or self.engine_setting,
                         params=params, files=[asdict(f) for f in result.files],
                         duration_s=duration)
        try:
            self.history_store.append(rec)
        except OSError as e:
            self._log('error', _t('err_settings_save').format(e))
        self._refresh_history()

    def _refresh_history(self):
        self.history_list.clear()
        try:
            self._history_records = self.history_store.load(
                on_error=lambda message: self._log('error', message))[:50]
        except OSError as e:
            self._history_records = []
            self._log('error', _t('err_load').format(e))
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
            self._log('error', _t('hist_no_tree'))

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
        self._log('success', _t('preset_applied').format(item.text()))

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
        self._log('success', _t('preset_saved').format(name))

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

    def _populate_stats(self, result):
        """The statistics of the last file that finished 'ok'."""
        done = [f for f in result.files if f.status == 'ok']
        if not done:
            return
        last = done[-1]
        self.stats_file_label.setText(_t("stats_field_file") + ': ' + os.path.basename(last.file))
        fields = [('stats_field_model', 'model'), ('stats_field_taxa', 'taxa'),
                  ('stats_field_lnl', 'lnL'), ('stats_field_gamma', 'gamma'),
                  ('stats_field_tstv', 'tstv'), ('stats_field_time', 'time')]
        self.stats_table.setRowCount(len(fields))
        for i, (key, col) in enumerate(fields):
            self.stats_table.setItem(i, 0, QTableWidgetItem(_t(key)))
            self.stats_table.setItem(i, 1, QTableWidgetItem((last.stats or {}).get(col) or 'n/a'))

    def _populate_summary(self, rows):
        cols = ['file', 'status', 'model', 'taxa', 'lnL', 'gamma', 'tstv', 'time']
        heads = [_t("sum_col_" + c) for c in cols]
        self.summary_table.setColumnCount(len(cols))
        self.summary_table.setHorizontalHeaderLabels(heads)
        self.summary_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, c in enumerate(cols):
                self.summary_table.setItem(i, j, QTableWidgetItem(r.get(c) or ''))

    def on_phyml_path_changed(self, path):
        if is_mpi_binary(path):
            if not self.chk_use_mpi.isChecked() and self._mpi_auto_path != path:
                self._mpi_auto_path = path
                self.chk_use_mpi.setChecked(True)
                if not self._is_loading:
                    self._log('system', _t("mpi_detected"))
        else:
            self._mpi_auto_path = ""
