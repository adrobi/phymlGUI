import csv
import json
import os
import shutil
from html import escape

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QFormLayout, QComboBox, QLineEdit, QPushButton,
                             QFileDialog, QMessageBox, QTabWidget,
                             QCheckBox, QGroupBox, QSizePolicy, QLabel,
                             QStatusBar, QProgressBar, QSplitter, QToolBox,
                             QListWidget, QListWidgetItem, QTextEdit,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QFont, QShortcut, QKeySequence

from phyml_core import __version__
from phyml_core.i18n import _t
from phyml_core.utils import psutil, detect_cores, is_mpi_binary, resource_path
from phyml_core.pipeline import PipelineWorker
from phyml_ui.tree_viewer import TreeViewerWidget
from phyml_ui.themes import THEMES

CONFIG_FILE = 'phyml_config.json'

_ROLE_COLORS = {
    'error':   '#E53935',
    'success': '#43A047',
    'system':  '#3D8BFD',
    'out':     None,  # default text color from the active theme
}


class LogConsole(QWidget):
    """Structured log: colored roles, severity filter, substring search.

    Keeps the QTextEdit-style API used by the pipeline (append/clear) and
    by tests (toPlainText); entries are always stored in full, filtering
    only affects what is displayed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []  # (role, text)
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

    def _append_html(self, text, role):
        color = _ROLE_COLORS[role]
        prefix = '' if color is None else f'#{color}'
        weight = '600' if role == 'system' else '400'
        self.view.append(f'<span style="color:{prefix or "inherit"};font-weight:{weight}">'
                         f'{escape(text)}</span>')
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _render(self):
        self.view.clear()
        for role, text in self._entries:
            if self._passes(role, text):
                self._append_html(text, role)


# --- Main Application Window ---
class PhyMLApp(QWidget):
    def __init__(self):
        super().__init__()
        self._is_loading = True
        self.worker = None
        self.fasta_file = ""
        self._mpi_auto_path = ""
        self._cpu_samples = []
        self._mon_procs = {}
        self._batch_mode = False
        self._theme = 'light'
        self._recent = []
        self.phys_cores, self.logi_cores = detect_cores()
        self.initUI()
        self.load_config()
        self._is_loading = False

    # ---------- UI construction ----------

    def initUI(self):
        self.setWindowTitle(f'phymlGUI {__version__}')
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(1280, 820)
        self.setMinimumSize(980, 600)  # must stay usable at 1366x768
        self.setAcceptDrops(True)

        root_layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(self.splitter, 1)

        self.splitter.addWidget(self._build_left_panel())
        self.splitter.addWidget(self._build_right_pane())
        self.splitter.setSizes([230, 1050])
        self.splitter.setChildrenCollapsible(True)

        QShortcut(QKeySequence(Qt.Key_F9), self, self.toggle_side_panel)
        self.bind_autosave(self)  # after the whole tree is parented

    def _build_left_panel(self):
        self.panel = QToolBox()
        self.panel.setMinimumWidth(180)

        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(self._open_recent)
        self.panel.addItem(self.recent_list, _t("panel_recent"))

        self.presets_list = QListWidget()
        hint = QListWidgetItem(_t("panel_hint_presets"))
        hint.setFlags(hint.flags() & ~Qt.ItemIsEnabled)
        self.presets_list.addItem(hint)
        self.panel.addItem(self.presets_list, _t("panel_presets"))

        self.history_list = QListWidget()
        hint = QListWidgetItem(_t("panel_hint_history"))
        hint.setFlags(hint.flags() & ~Qt.ItemIsEnabled)
        self.history_list.addItem(hint)
        self.panel.addItem(self.history_list, _t("panel_history"))
        return self.panel

    def _build_right_pane(self):
        right = QWidget()
        main_layout = QVBoxLayout(right)
        main_layout.setSpacing(8)

        # 1. Group: Paths
        group_paths = QGroupBox(_t("group_paths"))
        path_layout = QFormLayout()

        self.phyml_path_input = QLineEdit()
        self.phyml_path_input.textChanged.connect(self.on_phyml_path_changed)
        btn_phyml = QPushButton(_t("btn_browse"))
        btn_phyml.clicked.connect(lambda: self.browse_file(self.phyml_path_input))
        hbox1 = QHBoxLayout(); hbox1.addWidget(self.phyml_path_input); hbox1.addWidget(btn_phyml)
        path_layout.addRow(_t("path_phyml"), hbox1)

        self.mpirun_path_input = QLineEdit()
        btn_mpirun = QPushButton(_t("btn_browse"))
        btn_mpirun.clicked.connect(lambda: self.browse_file(self.mpirun_path_input))
        hbox_mpi_path = QHBoxLayout(); hbox_mpi_path.addWidget(self.mpirun_path_input); hbox_mpi_path.addWidget(btn_mpirun)
        path_layout.addRow(_t("path_mpirun"), hbox_mpi_path)

        self.muscle_path_input = QLineEdit()
        btn_muscle = QPushButton(_t("btn_browse"))
        btn_muscle.clicked.connect(lambda: self.browse_file(self.muscle_path_input))
        hbox2 = QHBoxLayout(); hbox2.addWidget(self.muscle_path_input); hbox2.addWidget(btn_muscle)
        path_layout.addRow(_t("path_muscle"), hbox2)

        self.fasta_path_input = QLineEdit()
        btn_fasta = QPushButton(_t("btn_select_fasta"))
        btn_fasta.clicked.connect(self.browse_fasta)
        btn_fasta_dir = QPushButton(_t("btn_select_dir"))
        btn_fasta_dir.clicked.connect(self.browse_fasta_dir)
        hbox3 = QHBoxLayout(); hbox3.addWidget(self.fasta_path_input); hbox3.addWidget(btn_fasta); hbox3.addWidget(btn_fasta_dir)
        path_layout.addRow(_t("input_fasta"), hbox3)

        group_paths.setLayout(path_layout)
        main_layout.addWidget(group_paths)

        # 2. Parameter Tabs
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        tab_basic = QWidget()
        form_basic = QFormLayout(tab_basic)

        self.chk_use_mpi = QCheckBox(_t("lbl_use_mpi"))
        self.le_mpi_np = QLineEdit(str(self.phys_cores))
        self.le_mpi_np.setFixedWidth(50)
        mpi_hbox = QHBoxLayout(); mpi_hbox.addWidget(self.chk_use_mpi); mpi_hbox.addWidget(QLabel(_t("lbl_mpi_np"))); mpi_hbox.addWidget(self.le_mpi_np); mpi_hbox.addStretch()
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
        self.tabs.addTab(tab_basic, _t("tab_model"))

        tab_model = QWidget()
        form_model = QFormLayout(tab_model)
        self.cb_freq = QComboBox()
        self.cb_freq.addItem(_t("freq_def"), "default"); self.cb_freq.addItem(_t("freq_emp"), "e"); self.cb_freq.addItem(_t("freq_ml"), "m")
        form_model.addRow(_t("lbl_freq"), self.cb_freq)
        self.le_tstv = QLineEdit("e"); form_model.addRow(_t("lbl_tstv"), self.le_tstv)
        self.le_pinv = QLineEdit("0.0"); form_model.addRow(_t("lbl_pinv"), self.le_pinv)
        self.le_classes = QLineEdit("4"); form_model.addRow(_t("lbl_classes"), self.le_classes)
        self.le_gamma = QLineEdit("e"); form_model.addRow(_t("lbl_gamma"), self.le_gamma)
        self.tabs.addTab(tab_model, _t("tab_evo"))

        tab_tree = QWidget()
        form_tree = QFormLayout(tab_tree)
        self.cb_search = QComboBox()
        self.cb_search.addItem(_t("search_nni"), "NNI"); self.cb_search.addItem(_t("search_spr"), "SPR"); self.cb_search.addItem(_t("search_best"), "BEST")
        form_tree.addRow(_t("lbl_search"), self.cb_search)
        self.cb_optimize = QComboBox()
        self.cb_optimize.addItem(_t("opt_tlr"), "tlr"); self.cb_optimize.addItem(_t("opt_tl"), "tl"); self.cb_optimize.addItem(_t("opt_lr"), "lr")
        self.cb_optimize.addItem(_t("opt_l"), "l"); self.cb_optimize.addItem(_t("opt_r"), "r"); self.cb_optimize.addItem(_t("opt_n"), "n")
        form_tree.addRow(_t("lbl_opt"), self.cb_optimize)
        self.chk_parsimony = QCheckBox(_t("chk_pars")); form_tree.addRow("", self.chk_parsimony)
        self.tabs.addTab(tab_tree, _t("tab_search"))

        main_layout.addWidget(self.tabs)

        # 3. Controls
        control_layout = QHBoxLayout()
        self.btn_run = QPushButton(_t("btn_run"))
        self.btn_run.setStyleSheet(f"background-color: #2196F3; color: white; padding: 10px; font-weight: bold;")
        self.btn_run.clicked.connect(self.start_pipeline)

        self.btn_cancel = QPushButton(_t("btn_cancel"))
        self.btn_cancel.setStyleSheet(f"background-color: #F44336; color: white; padding: 10px; font-weight: bold;")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_pipeline)

        self.chk_show_tree = QCheckBox(_t("chk_show"))
        self.chk_show_tree.setChecked(True)

        control_layout.addWidget(self.btn_run); control_layout.addWidget(self.btn_cancel); control_layout.addWidget(self.chk_show_tree)
        main_layout.addLayout(control_layout)

        # 4. Results tabs: Log | Tree | Stats | Summary
        self.result_tabs = QTabWidget()
        self.log_console = LogConsole()
        self.result_tabs.addTab(self.log_console, _t("tab_log"))

        self.tree_view = TreeViewerWidget()
        self.result_tabs.addTab(self.tree_view, _t("tab_tree"))

        stats_tab = QWidget()
        stats_lay = QVBoxLayout(stats_tab)
        self.stats_file_label = QLabel("—")
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.horizontalHeader().setVisible(False)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        stats_lay.addWidget(self.stats_file_label)
        stats_lay.addWidget(self.stats_table)
        self.result_tabs.addTab(stats_tab, _t("tab_stats"))

        self.summary_table = QTableWidget(0, 8)
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.result_tabs.addTab(self.summary_table, _t("tab_summary"))
        main_layout.addWidget(self.result_tabs, 1)

        # 5. Status bar: core info + live CPU utilization + theme toggle
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.cores_label = QLabel(_t("cores_info").format(self.phys_cores, self.logi_cores))
        self.cpu_sys_label = QLabel(_t("cpu_sys").format(0))
        self.cpu_sys_bar = QProgressBar()
        self.cpu_sys_bar.setRange(0, 100)
        self.cpu_sys_bar.setTextVisible(True)
        self.cpu_sys_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.cpu_run_label = QLabel(_t("cpu_analysis_idle"))
        self.theme_btn = QPushButton("☾")
        self.theme_btn.setFixedSize(30, 24)
        self.theme_btn.setToolTip(_t("theme_toggle"))
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.status_bar.addWidget(self.cores_label)
        self.status_bar.addWidget(self.cpu_sys_label)
        self.status_bar.addWidget(self.cpu_sys_bar, 1)  # stretch: fills all free space
        self.status_bar.addPermanentWidget(self.cpu_run_label)
        self.status_bar.addPermanentWidget(self.theme_btn)
        main_layout.addWidget(self.status_bar)

        self.cpu_timer = QTimer(self)
        self.cpu_timer.setInterval(1000)
        self.cpu_timer.timeout.connect(self.update_cpu_status)
        if psutil is not None:
            self.cpu_timer.start()

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

    # ---------- panel / theme helpers ----------

    def toggle_side_panel(self):
        self.panel.setVisible(not self.panel.isVisible())

    def toggle_theme(self):
        self._theme = 'dark' if self._theme == 'light' else 'light'
        self.apply_theme(self._theme)
        if not self._is_loading:
            self.auto_save()

    def apply_theme(self, name):
        from PySide6.QtWidgets import QApplication
        self._theme = name if name in THEMES else 'light'
        self.theme_btn.setText('☀' if self._theme == 'dark' else '☾')
        QApplication.instance().setStyleSheet(THEMES[self._theme])

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
        event.accept()

    def toggle_bootstrap_input(self):
        is_bootstrap = self.cb_support_method.currentData() == "bootstrap"
        self.le_bootstrap_replicates.setEnabled(is_bootstrap)
        if not self._is_loading: self.auto_save()

    def update_models(self):
        self.cb_model.clear()
        dt = self.cb_datatype.currentData()
        models = ["HKY85", "JC69", "K80", "F81", "F84", "TN93", "GTR", "custom"] if dt == "nt" else \
                 ["LG", "WAG", "JTT", "MtREV", "Dayhoff", "DCMut", "RtREV", "CPREV", "VT", "Blosum62", "MtMam", "MtArt", "HIVw", "HIVb", "custom"]
        for m in models: self.cb_model.addItem(m, m)
        if not self._is_loading: self.auto_save()

    def browse_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self, _t("file_exe"))
        if path: line_edit.setText(path)

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
            "theme": self._theme,
            "recent": self._recent
        }

    def auto_save(self):
        config = self.get_current_config()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except: pass

    def load_config(self):
        self.update_models()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.phyml_path_input.setText(config.get("phyml_path", ""))
                mpirun = config.get("mpirun_path", "mpiexec")
                if mpirun in ("mpirun", "mpiexec"):
                    mpirun = shutil.which("mpiexec") or shutil.which("mpirun") or mpirun
                self.mpirun_path_input.setText(mpirun)
                self.muscle_path_input.setText(config.get("muscle_path", ""))
                self.set_combo_by_data(self.cb_datatype, config.get("datatype", "nt"))
                self.update_models()
                self.set_combo_by_data(self.cb_model, config.get("model", "HKY85"))
                self.set_combo_by_data(self.cb_freq, config.get("freq", "default"))
                self.set_combo_by_data(self.cb_support_method, config.get("support_method", "bootstrap"))
                self.set_combo_by_data(self.cb_search, config.get("search", "NNI"))
                self.set_combo_by_data(self.cb_optimize, config.get("optimize", "tlr"))
                self.le_bootstrap_replicates.setText(config.get("bootstrap_replicates", "100"))
                self.chk_use_mpi.setChecked(config.get("use_mpi", False))
                self.le_mpi_np.setText(config.get("mpi_np", str(self.phys_cores)))
                self.le_tstv.setText(config.get("tstv", "e"))
                self.le_pinv.setText(config.get("pinv", "0.0"))
                self.le_classes.setText(config.get("classes", "4"))
                self.le_gamma.setText(config.get("gamma", "e"))
                self.chk_parsimony.setChecked(config.get("parsimony", False))
                self.chk_show_tree.setChecked(config.get("show_tree", True))
                self._recent = [p for p in config.get("recent", []) if os.path.exists(p)]
                self._refresh_recent()
                self.apply_theme(config.get("theme", "light"))
                self.toggle_bootstrap_input()
                self.log_console.append(_t("sys_load"))
            except Exception as e: self.log_console.append(_t("err_load").format(e))

    def set_combo_by_data(self, combo, data_val):
        idx = combo.findData(data_val)
        if idx >= 0: combo.setCurrentIndex(idx)

    def start_pipeline(self):
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
        if (is_mpi_binary(self.phyml_path_input.text())
                and not self.chk_use_mpi.isChecked()
                and self.cb_support_method.currentData() == "bootstrap"):
            QMessageBox.warning(self, _t("mpi_boot_title"), _t("mpi_boot_msg")); return
        self._batch_mode = len(files) > 1
        self._remember_recent(target)
        if not self._is_loading: self.auto_save()
        self.btn_run.setEnabled(False); self.btn_cancel.setEnabled(True); self.log_console.clear()
        self.result_tabs.setCurrentWidget(self.log_console)
        self._cpu_samples = []
        self._mon_procs = {}
        config = self.get_current_config()
        self.worker = PipelineWorker(config, files)
        self.worker.log_signal.connect(self.log_console.append)
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
        if success and tree_path and os.path.exists(tree_path):
            self.tree_view.load_tree(tree_path)
            if self.chk_show_tree.isChecked() and not self._batch_mode:
                self.result_tabs.setCurrentWidget(self.tree_view)

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
