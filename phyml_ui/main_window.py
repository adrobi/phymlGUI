import os
import shutil
from dataclasses import asdict
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit,
                             QPushButton, QMessageBox, QCheckBox, QSplitter, QScrollArea,
                             QInputDialog, QApplication)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon

from phyml_core import __version__, presets, report, settings, utils
from phyml_core.engines import ENGINES
from phyml_core.engines.base import format_issue
from phyml_core.history import HistoryStore, best_tree, new_record
from phyml_core.i18n import _t
from phyml_core.paths import AppPaths
from phyml_core.utils import detect_cores, is_mpi_binary, resource_path
from phyml_ui.fasta_input import FASTA_SUFFIXES, FastaInput, batch_files
from phyml_ui.nav_panel import NavPanel
from phyml_ui.params_panel import ParamsPanel, set_combo_by_data
from phyml_ui.results_panel import ResultsPanel
from phyml_ui.settings_dialog import SettingsDialog
from phyml_ui.status_bar import AppStatusBar
from phyml_ui.themes import resolve, build_qss, role_colors, PALETTES
from phyml_ui.tree_viewer import TreeViewerWidget
from phyml_ui.worker import RunWorker

# settings that say nothing about how a run was made: left out of a history record
_NOT_RUN_PARAMS = ('presets', 'recent', 'window')


class PhyMLApp(QWidget):
    """The main window: builds the panels, keeps the settings file and the history in step
    with them and starts / cancels / shows runs."""

    def __init__(self, paths=None, engines=None):
        super().__init__()
        self.paths = paths if paths is not None else AppPaths.detect()
        self.engines = ENGINES if engines is None else engines   # tests pass fakes
        self.history_store = HistoryStore(self.paths.history_file)
        self.settings_store = settings.SettingsStore(self.paths, self._log)
        self._is_loading = True
        self._history_records = []      # the records shown in the history list, same order
        self.worker = None
        self.fasta_file = ""
        self._mpi_auto_path = ""
        self._theme_setting, self._accent_setting = 'system', 'green'
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

    def _build_middle_pane(self):
        """FASTA input + parameter groups (each on its own plate) + navigation + controls."""
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
        self.fasta = FastaInput()
        self.fasta.path_chosen.connect(self._set_input)
        self.fasta_path_input = self.fasta.path_edit
        v.addWidget(self.fasta)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.params = ParamsPanel(self.phys_cores)
        self.params.changed.connect(self.trigger_autosave)
        scroll.setWidget(self.params)
        v.addWidget(scroll, 1)

        # navigation (recent/presets/history) lives at the bottom of the column
        self.nav = NavPanel()
        self.nav.setMaximumHeight(230)
        self.nav.recent_activated.connect(self._open_recent)
        self.nav.preset_activated.connect(self._preset_activated)
        self.nav.preset_save_requested.connect(self._save_preset)
        self.nav.preset_delete_requested.connect(self._delete_preset)
        self.nav.history_activated.connect(self._open_history_entry)
        v.addWidget(self.nav)

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
        """Big tree viewer on top, Log/Stats/Summary/Queue tabs underneath."""
        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(8, 0, 0, 0)  # breathing room from the left splitter
        self.tree_view = TreeViewerWidget()
        self.result_tabs = ResultsPanel()
        self.result_tabs.retry_clicked.connect(self._retry_failed)
        self.log_console = self.result_tabs.log_console
        self.right_split = QSplitter(Qt.Vertical)
        self.right_split.addWidget(self.tree_view)
        self.right_split.addWidget(self.result_tabs)
        self.right_split.setSizes([470, 260])
        self.right_split.setChildrenCollapsible(False)
        v.addWidget(self.right_split, 1)
        return right

    # ---------- input, drag & drop, recent ----------

    def _set_input(self, path):
        self.fasta_path_input.setText(path)
        self.fasta_file = path

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            p = urls[0].toLocalFile()
            if os.path.isdir(p) or p.lower().endswith(FASTA_SUFFIXES):
                event.acceptProposedAction()

    def dropEvent(self, event):
        self._set_input(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()

    def _remember_recent(self, path):
        self._recent = ([path] + [p for p in self._recent if p != path])[:10]
        self.nav.set_recent(self._recent)

    def _open_recent(self, path):
        if os.path.exists(path):
            self._set_input(path)

    # ---------- theme, settings, models ----------

    def open_settings(self):
        SettingsDialog(self, self).exec()

    def apply_theme(self, theme_setting=None, accent_setting=None):
        """Resolve settings (with 'system' support), style the app and the log."""
        if theme_setting is not None:
            self._theme_setting = theme_setting
        if accent_setting is not None:
            self._accent_setting = accent_setting
        theme, accent = resolve(self._theme_setting, self._accent_setting)
        QApplication.instance().setStyleSheet(build_qss(theme, accent))
        self.log_console.set_role_colors(role_colors(theme, accent))
        pal = PALETTES[theme]
        self.tree_view.set_colors(pal['text'], accent, pal['base'])

    def update_models(self):
        # an unknown engine in a hand-edited config gets PhyML's list, as a run uses PhyML for it
        self.params.set_engine(self.engines.get(self.engine_setting) or ENGINES['phyml'])

    set_combo_by_data = staticmethod(set_combo_by_data)

    def on_phyml_path_changed(self, path):
        if not is_mpi_binary(path):
            self._mpi_auto_path = ""
        elif not self.params.chk_use_mpi.isChecked() and self._mpi_auto_path != path:
            self._mpi_auto_path = path
            self.params.chk_use_mpi.setChecked(True)
            if not self._is_loading:
                self._log('system', _t("mpi_detected"))

    # ---------- settings file ----------

    def bind_autosave(self, parent_widget):
        for child in parent_widget.children():
            if child is self.params: continue   # it saves through params.changed
            elif isinstance(child, QLineEdit): child.textChanged.connect(self.trigger_autosave)
            elif isinstance(child, QComboBox): child.currentIndexChanged.connect(self.trigger_autosave)
            elif isinstance(child, QCheckBox): child.toggled.connect(self.trigger_autosave)
            else: self.bind_autosave(child)

    def trigger_autosave(self, *args):
        if not self._is_loading: self.auto_save()

    def auto_save(self):
        self.settings_store.save(self.get_current_config())

    def get_current_config(self):
        return {
            "engine": self.engine_setting,
            "iqtree_path": self.iqtree_path_input.text(),
            "phyml_path": self.phyml_path_input.text(),
            "mpirun_path": self.mpirun_path_input.text(),
            "muscle_path": self.muscle_path_input.text(),
            **self.params.params(),
            "show_tree": self.chk_show_tree.isChecked(),
            "theme": self._theme_setting,
            "accent": self._accent_setting,
            "recent": self._recent,
            "presets": self._user_presets,
            "window": {"w": self.width(), "h": self.height(),
                       "splitter": self.splitter.sizes(), "vsplit": self.right_split.sizes()},
        }

    def load_config(self):
        self.update_models()
        raw, clean = self.settings_store.load()
        try:
            self._apply_config(settings.resolve_cores(settings.from_disk(raw, self.paths)))
            if clean and os.path.isfile(self.paths.config_file):
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
        self.update_models()
        self.params.set_params(dict(presets.extract(config), use_mpi=config["use_mpi"],
                                    mpi_np=config["mpi_np"]))
        self.chk_show_tree.setChecked(config["show_tree"])
        self._recent = [p for p in config["recent"] if isinstance(p, str) and os.path.exists(p)]
        self.nav.set_recent(self._recent)
        self._user_presets = dict(config["presets"])
        self.apply_theme(config["theme"], config["accent"])
        win = config["window"]
        if win.get("w") and win.get("h"):
            self.resize(min(win["w"], 4096), min(win["h"], 4096))
        for key, split in (("splitter", self.splitter), ("vsplit", self.right_split)):
            if isinstance(win.get(key), list) and len(win[key]) == 2:
                split.setSizes(win[key])

    # ---------- runs ----------

    def _log(self, level, text):
        """A log line at the given level; messages from the core modules may end with a newline."""
        self.log_console.append(level, text.rstrip('\n'))

    def start_pipeline(self, files_override=None):
        if self.worker is not None and self.worker.isRunning():
            return   # one run at a time: replacing a running worker would destroy its thread
        if isinstance(files_override, bool):  # defensive: Qt clicked(checked)
            files_override = None
        if files_override is None:
            target = self.fasta_path_input.text() or self.fasta_file
            if not target or not os.path.exists(target):
                QMessageBox.warning(self, _t("err_box_title"), _t("err_box_msg")); return
            files = batch_files(target) if os.path.isdir(target) else [target]
            if not files:
                QMessageBox.warning(self, _t("err_box_title"), _t("batch_empty")); return
            out_dir = target if os.path.isdir(target) else os.path.dirname(os.path.abspath(target))
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
        self._remember_recent(target)
        if not self._is_loading: self.auto_save()
        self.btn_run.setEnabled(False); self.btn_cancel.setEnabled(True)
        self.result_tabs.begin_run(files)
        self.status.track(self._active_pid)
        self._run_started = datetime.now()
        self._run_config, self._run_inputs, self._run_out_dir = config, inputs, out_dir
        self.worker = RunWorker.for_run(config, files, self.paths, engines=self.engines)
        self.worker.log.connect(self._log)
        self.worker.status.connect(self.result_tabs.set_file_status)
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

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            # synchronous: after close the process may exit and cut off a daemon thread,
            # leaving phyml-mpi / smpd children alive
            self.worker.cancel(block=True)
            self.worker.wait()
        self.auto_save()  # persist window geometry and splitter ratios
        event.accept()

    def pipeline_finished(self, result):
        """Show a finished run (a RunResult): tables, summary files, history, retry, tree."""
        if self.worker is not None:
            self.worker.wait()   # done is emitted at the end of run(): this returns at once
        self.last_result = result
        self.btn_run.setEnabled(True); self.btn_cancel.setEnabled(False)
        self.status.stop_tracking()
        if result.files:
            rows = report.summary_rows(result.files)
            self.result_tabs.show_result(result, rows)
            self._write_summary(rows)
        self._append_history(result)
        self._failed_files = [f.file for f in result.files if f.status == 'fail']
        self.result_tabs.retry_btn.setVisible(bool(self._failed_files))
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

    def _retry_failed(self):
        if self._failed_files:
            self.start_pipeline(files_override=self._failed_files)

    def _open_output_dir(self):
        if self._last_out_dir and os.path.isdir(self._last_out_dir):
            if utils.IS_WINDOWS:
                os.startfile(self._last_out_dir)
            else:   # xdg-open, also from inside an AppImage
                QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_out_dir))

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
            self._log('error', _t('err_history_save').format(e))
        self._refresh_history()

    def _refresh_history(self):
        try:
            self._history_records = self.history_store.load(
                on_error=lambda message: self._log('error', message))[:50]
        except OSError as e:
            self._history_records = []
            self._log('error', _t('err_load').format(e))
        self.nav.set_history(self._history_records)

    def _open_history_entry(self, row):
        if row >= len(self._history_records):
            return
        tree = best_tree(self._history_records[row])
        if tree and os.path.exists(tree):
            self.tree_view.load_tree(tree)
        else:
            self._log('error', _t('hist_no_tree'))

    # ---------- presets ----------

    def _refresh_presets(self):
        self.nav.set_presets(presets.BUILTIN, self._user_presets)

    def _preset_activated(self, preset):
        params = presets.apply(preset, self.get_current_config())
        self._is_loading = True   # one save for the whole preset, after it is shown
        try:
            self.engine_setting = params['engine']
            self.update_models()
            self.params.set_params(presets.extract(params))
        finally:
            self._is_loading = False
        self.auto_save()
        self._log('success', _t('preset_applied').format(self.nav.activated_preset_name))

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, _t('preset_save_current'), _t('preset_prompt'))
        if not ok or not name.strip():
            return
        name = name.strip()
        self._user_presets[name] = presets.extract(self.get_current_config())
        self.auto_save()
        self._refresh_presets()
        self._log('success', _t('preset_saved').format(name))

    def _delete_preset(self, name):
        self._user_presets.pop(name, None)
        self.auto_save()
        self._refresh_presets()
