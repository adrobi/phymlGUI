import sys
import os
import json
import subprocess
import re
import shutil
import locale

try:
    import psutil  # optional: CPU monitoring and physical core detection
except ImportError:
    psutil = None

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QFormLayout, QComboBox, QLineEdit, QPushButton,
                             QTextEdit, QFileDialog, QMessageBox, QTabWidget,
                             QCheckBox, QGroupBox, QSizePolicy, QLabel, QDialog,
                             QStatusBar, QProgressBar)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QIcon
from Bio import AlignIO, SeqIO, Phylo
from Bio.Seq import Seq

def resource_path(relative_path):
    """ Get the absolute path to a resource (required for correct operation within .exe) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Multilingual support (i18n) ---
def detect_language():
    try:
        lang, _ = locale.getdefaultlocale()
        if lang and lang.startswith('ru'):
            return 'ru'
    except Exception:
        pass
    return 'en'

def load_translations():
    """ Load localization strings from external JSON file """
    locales_path = resource_path('locales.json')
    if not os.path.exists(locales_path):
        print(f"Warning: {locales_path} not found. Fallback to empty dictionary.")
        return {"en": {}, "ru": {}}
    
    try:
        with open(locales_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {locales_path}: {e}")
        return {"en": {}, "ru": {}}

LANG = detect_language()
STRINGS = load_translations()

def _t(key):
    """ Returns the translated string by key """
    return STRINGS.get(LANG, {}).get(key, key)


CONFIG_FILE = 'phyml_config.json'

def detect_cores():
    """Physical and logical CPU counts (psutil preferred, os fallback)."""
    phys = logi = None
    if psutil is not None:
        phys = psutil.cpu_count(logical=False)
        logi = psutil.cpu_count(logical=True)
    phys = phys or os.cpu_count() or 2
    logi = logi or os.cpu_count() or phys
    return phys, logi

def is_mpi_binary(path):
    """Heuristic: PhyML MPI builds are named phyml-mpi / phyml_mpi etc."""
    return 'mpi' in os.path.basename(path or '').lower()

# --- Dialog class for tree visualization ---
class TreeViewerDialog(QDialog):
    def __init__(self, tree_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("tree_result").format(os.path.basename(tree_path)))
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(1200, 800) 
        
        layout = QVBoxLayout(self)
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        self.ax = self.figure.add_subplot(111)
        
        try:
            tree = Phylo.read(tree_path, "newick")
            def format_label(node):
                if node.is_terminal():
                    return node.name
                else:
                    if node.name:
                        try:
                            return str(round(float(node.name)))
                        except ValueError:
                            return node.name
                    return ""

            import matplotlib
            matplotlib.rcParams.update({'font.size': 9})
            Phylo.draw(tree, axes=self.ax, do_show=False, label_func=format_label)
            self.ax.set_title(_t("ml_tree"), pad=15, fontsize=12)
            self.figure.tight_layout() 
            self.canvas.draw()
            matplotlib.rcParams.update({'font.size': 10})
        except Exception as e:
            self.ax.text(0.5, 0.5, _t("tree_error").format(e), 
                         ha="center", va="center", color="red", fontsize=12)
            self.canvas.draw()

# --- Background Worker Thread ---
class PipelineWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, config, fasta_files):
        super().__init__()
        self.config = config
        if isinstance(fasta_files, str):
            fasta_files = [fasta_files]
        self.fasta_files = list(fasta_files)
        self.active_process = None
        self._is_cancelled = False

    def run(self):
        n_ok, last_tree = 0, ""
        batch = len(self.fasta_files) > 1
        if batch:
            self.log_signal.emit(_t("batch_found").format(len(self.fasta_files)))
        for i, fasta in enumerate(self.fasta_files, 1):
            if self._is_cancelled:
                break
            if batch:
                self.log_signal.emit(_t("batch_file_header").format(i, len(self.fasta_files), os.path.basename(fasta)))
            ok, tree = self._process_one(fasta)
            if ok:
                n_ok += 1
                last_tree = tree
            if self._is_cancelled:
                break
        if batch and not self._is_cancelled:
            self.log_signal.emit(_t("batch_summary").format(n_ok, len(self.fasta_files)))
        success = n_ok == len(self.fasta_files) and n_ok > 0 and not self._is_cancelled
        self.finished_signal.emit(success, last_tree)

    def _process_one(self, current_fasta):
        """Full pipeline for a single FASTA file: returns (success, tree_path)."""
        creation_flags = 0
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NO_WINDOW

        try:
            self.log_signal.emit(_t("init_analysis").format(current_fasta))

            # 1. Alignment check
            if not self.is_aligned(current_fasta):
                self.log_signal.emit(_t("diff_len"))
                muscle_exe = self.config.get("muscle_path", "")

                if not muscle_exe or not os.path.exists(muscle_exe):
                    self.log_signal.emit(_t("err_muscle"))
                    return False, ""

                aligned_fasta = current_fasta.rsplit('.', 1)[0] + '_aligned.fasta'
                if os.path.exists(aligned_fasta):
                    try:
                        os.remove(aligned_fasta)
                        self.log_signal.emit(_t("del_old"))
                    except Exception as e:
                        self.log_signal.emit(_t("err_del").format(e))
                        return False, ""

                cmd_muscle = [muscle_exe, "-align", current_fasta, "-output", aligned_fasta]
                self.active_process = subprocess.Popen(cmd_muscle, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creation_flags)
                for line in iter(self.active_process.stdout.readline, ''):
                    if self._is_cancelled: break
                self.active_process.stdout.close()
                self.active_process.wait()

                if self.active_process.returncode != 0 and not self._is_cancelled:
                    cmd_muscle_v3 = [muscle_exe, "-in", current_fasta, "-out", aligned_fasta]
                    self.active_process = subprocess.Popen(cmd_muscle_v3, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creation_flags)
                    for line in iter(self.active_process.stdout.readline, ''):
                        if self._is_cancelled: break
                    self.active_process.stdout.close()
                    self.active_process.wait()

                if self._is_cancelled:
                    self.log_signal.emit(_t("cancel_align"))
                    return False, ""

                if self.active_process.returncode == 0 and os.path.exists(aligned_fasta):
                    self.log_signal.emit(_t("align_success").format(aligned_fasta))
                    current_fasta = aligned_fasta
                else:
                    self.log_signal.emit(_t("err_muscle_fail"))
                    return False, ""
            else:
                self.log_signal.emit(_t("seq_aligned"))

            # 2. Conversion (FASTA -> PHYLIP)
            self.log_signal.emit(_t("cleaning"))
            phylip_path = current_fasta.rsplit('.', 1)[0] + '.phy'
            try:
                alignment = AlignIO.read(current_fasta, "fasta")
                for record in alignment:
                    record.seq = Seq(str(record.seq).replace('.', '-'))
                    clean_id = re.sub(r'[.|:;(),\s]', '_', record.id)
                    record.id = clean_id
                    record.name = clean_id
                    record.description = ""
                AlignIO.write(alignment, phylip_path, "phylip-relaxed")
                self.log_signal.emit(_t("conv_success").format(phylip_path))
            except Exception as e:
                self.log_signal.emit(_t("err_conv").format(e)); return False, ""

            if self._is_cancelled: return False, ""

            # 3. Run PhyML (MPI support added here)
            phyml_exe = self.config.get("phyml_path", "")
            if not phyml_exe or not os.path.exists(phyml_exe):
                self.log_signal.emit(_t("err_phyml")); return False, ""

            cmd_phyml = []
            if self.config.get("use_mpi", False):
                mpirun_exe = self.config.get("mpirun_path", "mpiexec")
                np = self.config.get("mpi_np", "2")
                cmd_phyml.extend([mpirun_exe, "-np", np])

            cmd_phyml.append(phyml_exe)
            cmd_phyml.extend(['-i', phylip_path])
            cmd_phyml.extend(['-d', self.config.get("datatype", "nt")])
            cmd_phyml.extend(['-m', self.config.get("model", "HKY85")])

            support_method = self.config.get("support_method", "bootstrap")
            if support_method == "bootstrap":
                cmd_phyml.extend(['-b', self.config.get("bootstrap_replicates", "100")])
            else:
                cmd_phyml.extend(['-b', support_method])

            if self.config.get("freq") != "default": cmd_phyml.extend(['-f', self.config.get("freq")])
            if self.config.get("tstv"): cmd_phyml.extend(['-t', self.config.get("tstv")])
            if self.config.get("pinv"): cmd_phyml.extend(['-v', self.config.get("pinv")])
            if self.config.get("classes"): cmd_phyml.extend(['-c', self.config.get("classes")])
            if self.config.get("gamma"): cmd_phyml.extend(['-a', self.config.get("gamma")])
            cmd_phyml.extend(['-s', self.config.get("search", "NNI")])
            cmd_phyml.extend(['-o', self.config.get("optimize", "tlr")])
            if self.config.get("parsimony"): cmd_phyml.append('-p')

            self.log_signal.emit(_t("run_phyml").format(' '.join(cmd_phyml)))
            self.active_process = subprocess.Popen(cmd_phyml, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creation_flags)

            for line in iter(self.active_process.stdout.readline, ''):
                if line: self.log_signal.emit(line.strip())
                if self._is_cancelled: break

            self.active_process.stdout.close()
            self.active_process.wait()

            if self._is_cancelled:
                self.log_signal.emit(_t("cancel_analysis"))
                return False, ""
            elif self.active_process.returncode != 0:
                self.log_signal.emit(_t("err_crit_phyml").format(self.active_process.returncode))
                return False, ""
            else:
                self.log_signal.emit(_t("success_pipe"))
                tree_path = f"{phylip_path}_phyml_tree.txt"
                self._log_stats_summary(tree_path)
                return True, tree_path

        except Exception as e:
            self.log_signal.emit(_t("err_crit").format(str(e)))
            return False, ""

    def _log_stats_summary(self, tree_path):
        """Emit a one-line summary parsed from the sibling *_phyml_stats.txt."""
        stats_path = tree_path.replace('_phyml_tree.txt', '_phyml_stats.txt')
        if not os.path.exists(stats_path):
            return
        try:
            with open(stats_path, encoding='utf-8', errors='replace') as f:
                content = f.read()
        except OSError:
            return
        def grab(pattern):
            m = re.search(pattern, content)
            return m.group(1) if m else "n/a"
        self.log_signal.emit(_t("stats_summary").format(
            grab(r'Model of \w+ substitution:\s*(\S+)'),
            grab(r'Number of taxa:\s*(\d+)'),
            grab(r'Log-likelihood:\s*(-?[\d.]+)'),
            grab(r'Gamma shape parameter:\s*(-?[\d.]+)'),
            grab(r'transition/transversion ratio:\s*(-?[\d.]+)'),
            grab(r'Time used:\s*(\S+)')))

    def cancel(self):
        self._is_cancelled = True
        if self.active_process and self.active_process.poll() is None:
            try: self.active_process.terminate()
            except Exception: self.active_process.kill()

    def is_aligned(self, file_path):
        records = list(SeqIO.parse(file_path, "fasta"))
        if not records: raise ValueError(_t("err_empty"))
        first_len = len(records[0].seq)
        return all(len(rec.seq) == first_len for rec in records)


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
        self.phys_cores, self.logi_cores = detect_cores()
        self.initUI()
        self.load_config()
        self._is_loading = False

    def initUI(self):
        self.setWindowTitle('phymlGUI')
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(850, 850)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

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

        # Tab: Basic Parameters (MPI settings added here)
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

        # Tab: Evolutionary
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

        # Tab: Tree Search
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
        self.btn_run.setStyleSheet("background-color: #2196F3; color: white; padding: 10px; font-weight: bold;")
        self.btn_run.clicked.connect(self.start_pipeline)
        
        self.btn_cancel = QPushButton(_t("btn_cancel"))
        self.btn_cancel.setStyleSheet("background-color: #F44336; color: white; padding: 10px; font-weight: bold;")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_pipeline)

        self.chk_show_tree = QCheckBox(_t("chk_show"))
        self.chk_show_tree.setChecked(True)

        control_layout.addWidget(self.btn_run); control_layout.addWidget(self.btn_cancel); control_layout.addWidget(self.chk_show_tree)
        main_layout.addLayout(control_layout)

        # 4. Logs
        group_logs = QGroupBox(_t("group_log"))
        log_layout = QVBoxLayout()
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        log_layout.addWidget(self.log_console)
        group_logs.setLayout(log_layout)
        main_layout.addWidget(group_logs)

        # 5. Status bar: core info + live CPU utilization
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.cores_label = QLabel(_t("cores_info").format(self.phys_cores, self.logi_cores))
        self.cpu_sys_label = QLabel(_t("cpu_sys").format(0))
        self.cpu_sys_bar = QProgressBar()
        self.cpu_sys_bar.setRange(0, 100)
        self.cpu_sys_bar.setTextVisible(True)
        self.cpu_sys_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.cpu_run_label = QLabel(_t("cpu_analysis_idle"))
        self.status_bar.addWidget(self.cores_label)
        self.status_bar.addWidget(self.cpu_sys_label)
        self.status_bar.addWidget(self.cpu_sys_bar, 1)  # stretch: fills all free space
        self.status_bar.addPermanentWidget(self.cpu_run_label)
        main_layout.addWidget(self.status_bar)

        self.cpu_timer = QTimer(self)
        self.cpu_timer.setInterval(1000)
        self.cpu_timer.timeout.connect(self.update_cpu_status)
        if psutil is not None:
            self.cpu_timer.start()

        self.setLayout(main_layout)
        self.bind_autosave(self)

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
            "show_tree": self.chk_show_tree.isChecked()
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
                self.le_mpi_np.setText(config.get("mpi_np", "4"))
                self.le_tstv.setText(config.get("tstv", "e"))
                self.le_pinv.setText(config.get("pinv", "0.0"))
                self.le_classes.setText(config.get("classes", "4"))
                self.le_gamma.setText(config.get("gamma", "e"))
                self.chk_parsimony.setChecked(config.get("parsimony", False))
                self.chk_show_tree.setChecked(config.get("show_tree", True))
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
            files = sorted(f for f in os.listdir(target) if f.lower().endswith(('.fasta', '.fas', '.fa')))
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
        self.btn_run.setEnabled(False); self.btn_cancel.setEnabled(True); self.log_console.clear()
        self._cpu_samples = []
        self._mon_procs = {}
        config = self.get_current_config()
        self.worker = PipelineWorker(config, files)
        self.worker.log_signal.connect(lambda msg: self.log_console.append(msg))
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
        if success and self.chk_show_tree.isChecked() and not self._batch_mode and os.path.exists(tree_path):
            self.log_console.append(_t("sys_open_tree"))
            viewer = TreeViewerDialog(tree_path, self); viewer.exec()

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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PhyMLApp()
    window.show()
    sys.exit(app.exec())