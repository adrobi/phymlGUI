import sys
import os
import json
import subprocess
import re
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QFormLayout, QComboBox, QLineEdit, QPushButton, 
                             QTextEdit, QFileDialog, QMessageBox, QTabWidget, 
                             QCheckBox, QGroupBox, QSizePolicy, QLabel, QDialog)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QIcon
from Bio import AlignIO, SeqIO, Phylo
from Bio.Seq import Seq

def resource_path(relative_path):
    """ Get the absolute path to a resource (required for correct operation within .exe) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

CONFIG_FILE = 'phyml_config.json'

# --- Dialog class for tree visualization ---
class TreeViewerDialog(QDialog):
    def __init__(self, tree_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"PhyML Result: {os.path.basename(tree_path)}")
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        # 1. Increase the initial window size
        self.resize(1200, 800) 
        
        layout = QVBoxLayout(self)
        
        # Create Matplotlib figure and canvas
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        self.ax = self.figure.add_subplot(111)
        
        # Render the tree
        try:
            tree = Phylo.read(tree_path, "newick")
            
            # 2. Function for clean label formatting
            def format_label(node):
                if node.is_terminal():
                    return node.name # Keep species names (at the ends of branches) as they are
                else:
                    # Round internal node values (branch supports) to whole numbers
                    if node.name:
                        try:
                            # Try to convert long float to a neat integer
                            return str(round(float(node.name)))
                        except ValueError:
                            # If it's text, leave it as text
                            return node.name
                    return ""

            # 3. Decrease global font size for the plot
            import matplotlib
            matplotlib.rcParams.update({'font.size': 9})

            # Draw tree using the formatting function
            Phylo.draw(tree, axes=self.ax, do_show=False, label_func=format_label)
            
            self.ax.set_title("Maximum Likelihood Tree (ML Tree)", pad=15, fontsize=12)
            
            # Automatically adjust layout so long names don't get cut off
            self.figure.tight_layout() 
            
            self.canvas.draw()
            
            # Reset font size back to default so it doesn't affect other plots
            matplotlib.rcParams.update({'font.size': 10})
            
        except Exception as e:
            self.ax.text(0.5, 0.5, f"Tree rendering error:\n{e}", 
                         ha="center", va="center", color="red", fontsize=12)
            self.canvas.draw()


# --- Background Worker Thread ---
class PipelineWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config, fasta_file):
        super().__init__()
        self.config = config
        self.fasta_file = fasta_file
        self.active_process = None
        self._is_cancelled = False
        
        self._success = False
        self._out_tree_path = ""

    def run(self):
        creation_flags = 0
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NO_WINDOW

        try:
            current_fasta = self.fasta_file

            # 1. Alignment check (using MUSCLE)
            self.log_signal.emit(f"[*] Initializing analysis for file: {current_fasta}")
            if not self.is_aligned(current_fasta):
                self.log_signal.emit("[!] Sequence lengths differ. Starting MUSCLE...")
                muscle_exe = self.config.get("muscle_path", "")
                
                if not muscle_exe or not os.path.exists(muscle_exe):
                    self.log_signal.emit("[ERROR] Invalid path to MUSCLE. Alignment impossible.")
                    return

                aligned_fasta = current_fasta.rsplit('.', 1)[0] + '_aligned.fasta'
                
                if os.path.exists(aligned_fasta):
                    try:
                        os.remove(aligned_fasta)
                        self.log_signal.emit("[-] Found old aligned file. Deleting for overwrite...")
                    except Exception as e:
                        self.log_signal.emit(f"[ERROR] Failed to delete old file: {e}")
                        return
                
                cmd_muscle = [muscle_exe, "-align", current_fasta, "-output", aligned_fasta]
                
                self.active_process = subprocess.Popen(cmd_muscle, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creation_flags)
                
                for line in iter(self.active_process.stdout.readline, ''):
                    if self._is_cancelled:
                        break
                self.active_process.stdout.close()
                self.active_process.wait()
                
                # Fallback for older MUSCLE versions if first command fails
                if self.active_process.returncode != 0 and not self._is_cancelled:
                    cmd_muscle_v3 = [muscle_exe, "-in", current_fasta, "-out", aligned_fasta]
                    
                    self.active_process = subprocess.Popen(cmd_muscle_v3, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creation_flags)
                    
                    for line in iter(self.active_process.stdout.readline, ''):
                        if self._is_cancelled:
                            break
                    self.active_process.stdout.close()
                    self.active_process.wait()

                if self._is_cancelled:
                    self.log_signal.emit("[-] Alignment process cancelled by user.")
                    return

                if self.active_process.returncode == 0 and os.path.exists(aligned_fasta):
                    self.log_signal.emit(f"[+] Alignment completed successfully: {aligned_fasta}")
                    current_fasta = aligned_fasta
                else:
                    self.log_signal.emit("[ERROR] MUSCLE failed. Check input file.")
                    return
            else:
                self.log_signal.emit("[+] Sequences are already aligned.")

            # 2. Cleanup and Conversion (FASTA -> PHYLIP)
            self.log_signal.emit("[*] Cleaning characters and converting (FASTA -> PHYLIP)...")
            phylip_path = current_fasta.rsplit('.', 1)[0] + '.phy'
            
            try:
                alignment = AlignIO.read(current_fasta, "fasta")
                for record in alignment:
                    # Clean dots and special characters in sequence and IDs
                    clean_seq = str(record.seq).replace('.', '-')
                    record.seq = Seq(clean_seq)
                    clean_id = re.sub(r'[.|:;(),\s]', '_', record.id)
                    record.id = clean_id
                    record.name = clean_id
                    record.description = "" 
                
                AlignIO.write(alignment, phylip_path, "phylip-relaxed")
                self.log_signal.emit(f"[+] Conversion complete: {phylip_path}")
            except Exception as e:
                self.log_signal.emit(f"[ERROR] Conversion failed: {e}")
                return

            if self._is_cancelled:
                return

            # 3. Run PhyML
            phyml_exe = self.config.get("phyml_path", "")
            if not phyml_exe or not os.path.exists(phyml_exe):
                self.log_signal.emit("[ERROR] Invalid path to PhyML.")
                return

            cmd_phyml = [phyml_exe, '-i', phylip_path]
            cmd_phyml.extend(['-d', self.config.get("datatype", "nt")])
            cmd_phyml.extend(['-m', self.config.get("model", "HKY85")])
            
            support_method = self.config.get("support_method", "bootstrap")
            if support_method == "bootstrap":
                cmd_phyml.extend(['-b', self.config.get("bootstrap_replicates", "100")])
            else:
                cmd_phyml.extend(['-b', support_method])
            
            # Optional model parameters
            if self.config.get("freq") != "default":
                cmd_phyml.extend(['-f', self.config.get("freq")])
            if self.config.get("tstv"):
                cmd_phyml.extend(['-t', self.config.get("tstv")])
            if self.config.get("pinv"):
                cmd_phyml.extend(['-v', self.config.get("pinv")])
            if self.config.get("classes"):
                cmd_phyml.extend(['-c', self.config.get("classes")])
            if self.config.get("gamma"):
                cmd_phyml.extend(['-a', self.config.get("gamma")])
            
            cmd_phyml.extend(['-s', self.config.get("search", "NNI")])
            cmd_phyml.extend(['-o', self.config.get("optimize", "tlr")])
            if self.config.get("parsimony"):
                cmd_phyml.append('-p')

            self.log_signal.emit(f"[*] Running PhyML: {' '.join(cmd_phyml)}")

            self.active_process = subprocess.Popen(cmd_phyml, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creation_flags)
            
            for line in iter(self.active_process.stdout.readline, ''):
                if line:
                    self.log_signal.emit(line.strip())
                if self._is_cancelled:
                    break

            self.active_process.stdout.close()
            self.active_process.wait()

            if self._is_cancelled:
                self.log_signal.emit("\n[-] Analysis cancelled by user.")
            elif self.active_process.returncode != 0:
                self.log_signal.emit(f"\n[CRITICAL ERROR] PhyML exited with code {self.active_process.returncode}.")
            else:
                self.log_signal.emit("\n[+] PIPELINE COMPLETED SUCCESSFULLY.")
                self._success = True
                self._out_tree_path = f"{phylip_path}_phyml_tree.txt"

        except Exception as e:
            self.log_signal.emit(f"\n[CRITICAL ERROR]: {str(e)}")
        finally:
            self.finished_signal.emit(self._success, self._out_tree_path)

    def cancel(self):
        self._is_cancelled = True
        if self.active_process and self.active_process.poll() is None:
            try:
                self.active_process.terminate()
            except Exception:
                self.active_process.kill()

    def is_aligned(self, file_path):
        records = list(SeqIO.parse(file_path, "fasta"))
        if not records:
            raise ValueError("Input file is empty or has invalid FASTA format.")
        first_len = len(records[0].seq)
        return all(len(rec.seq) == first_len for rec in records)


# --- Main Application Window ---
class PhyMLApp(QWidget):
    def __init__(self):
        super().__init__()
        self._is_loading = True
        self.worker = None
        self.fasta_file = ""
        self.initUI()
        self.load_config()
        self._is_loading = False

    def initUI(self):
        self.setWindowTitle('phymlGUI')
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(800, 800)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        # 1. Group: "Paths and Files"
        group_paths = QGroupBox("1. Executables and Data")
        path_layout = QFormLayout()
        
        self.phyml_path_input = QLineEdit()
        btn_phyml = QPushButton("Browse...")
        btn_phyml.clicked.connect(lambda: self.browse_file(self.phyml_path_input))
        hbox1 = QHBoxLayout(); hbox1.setContentsMargins(0,0,0,0); hbox1.addWidget(self.phyml_path_input); hbox1.addWidget(btn_phyml)
        path_layout.addRow("Path to PhyML (.exe):", hbox1)

        self.muscle_path_input = QLineEdit()
        btn_muscle = QPushButton("Browse...")
        btn_muscle.clicked.connect(lambda: self.browse_file(self.muscle_path_input))
        hbox2 = QHBoxLayout(); hbox2.setContentsMargins(0,0,0,0); hbox2.addWidget(self.muscle_path_input); hbox2.addWidget(btn_muscle)
        path_layout.addRow("Path to MUSCLE (.exe):", hbox2)

        self.fasta_path_input = QLineEdit()
        btn_fasta = QPushButton("Select FASTA")
        btn_fasta.clicked.connect(self.browse_fasta)
        hbox3 = QHBoxLayout(); hbox3.setContentsMargins(0,0,0,0); hbox3.addWidget(self.fasta_path_input); hbox3.addWidget(btn_fasta)
        path_layout.addRow("Input FASTA File:", hbox3)

        group_paths.setLayout(path_layout)
        main_layout.addWidget(group_paths)

        # 2. Parameter Tabs
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        # Tab: Basic Parameters
        tab_basic = QWidget()
        form_basic = QFormLayout(tab_basic)
        
        self.cb_datatype = QComboBox()
        self.cb_datatype.addItem("Nucleotides (DNA)", "nt")
        self.cb_datatype.addItem("Amino Acids (AA)", "aa")
        self.cb_datatype.currentIndexChanged.connect(self.update_models)
        form_basic.addRow("Data Type (-d):", self.cb_datatype)

        self.cb_model = QComboBox()
        form_basic.addRow("Substitution Model (-m):", self.cb_model)

        self.cb_support_method = QComboBox()
        self.cb_support_method.addItem("Bootstrap (Non-parametric)", "bootstrap")
        self.cb_support_method.addItem("aLRT statistics (-1)", "-1")
        self.cb_support_method.addItem("aLRT Chi2-based (-2)", "-2")
        self.cb_support_method.addItem("SH-like branch supports (-4)", "-4")
        self.cb_support_method.addItem("No support (0)", "0")
        self.cb_support_method.currentIndexChanged.connect(self.toggle_bootstrap_input)
        form_basic.addRow("Branch Support (-b):", self.cb_support_method)

        self.le_bootstrap_replicates = QLineEdit("100")
        self.le_bootstrap_replicates.setPlaceholderText("Number of replicates")
        form_basic.addRow("Bootstrap Replicates:", self.le_bootstrap_replicates)
        self.tabs.addTab(tab_basic, "Model Parameters")

        # Tab: Evolutionary Settings
        tab_model = QWidget()
        form_model = QFormLayout(tab_model)
        self.cb_freq = QComboBox()
        self.cb_freq.addItem("Default", "default")
        self.cb_freq.addItem("Empirical (e)", "e")
        self.cb_freq.addItem("Maximum Likelihood (m)", "m")
        form_model.addRow("Frequency Estimation (-f):", self.cb_freq)
        self.le_tstv = QLineEdit("e")
        form_model.addRow("Ts/Tv ratio (-t):", self.le_tstv)
        self.le_pinv = QLineEdit("0.0")
        form_model.addRow("Proportion of Invariant Sites (-v):", self.le_pinv)
        self.le_classes = QLineEdit("4")
        form_model.addRow("Rate Categories (-c):", self.le_classes)
        self.le_gamma = QLineEdit("e")
        form_model.addRow("Gamma Parameter (-a):", self.le_gamma)
        self.tabs.addTab(tab_model, "Evolutionary Settings")

        # Tab: Tree Search
        tab_tree = QWidget()
        form_tree = QFormLayout(tab_tree)
        self.cb_search = QComboBox()
        self.cb_search.addItem("NNI (Local Search)", "NNI")
        self.cb_search.addItem("SPR (Global Search)", "SPR")
        self.cb_search.addItem("BEST (Best of NNI/SPR)", "BEST")
        form_tree.addRow("Search Algorithm (-s):", self.cb_search)
        self.cb_optimize = QComboBox()
        self.cb_optimize.addItem("Topology, Lengths, Params (tlr)", "tlr")
        self.cb_optimize.addItem("Topology and Lengths (tl)", "tl")
        self.cb_optimize.addItem("Lengths and Params (lr)", "lr")
        self.cb_optimize.addItem("Only Lengths (l)", "l")
        self.cb_optimize.addItem("Only Params (r)", "r")
        self.cb_optimize.addItem("No Optimization (n)", "n")
        form_tree.addRow("Optimization Degree (-o):", self.cb_optimize)
        self.chk_parsimony = QCheckBox("Parsimony Starting Tree (-p)")
        form_tree.addRow("", self.chk_parsimony)
        self.tabs.addTab(tab_tree, "Tree Search")

        main_layout.addWidget(self.tabs)

        # 3. Control Buttons and Preview Toggle
        control_layout = QHBoxLayout()
        
        self.btn_run = QPushButton("Start Analysis")
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setStyleSheet("background-color: #2196F3; color: white; padding: 10px; font-weight: bold;")
        self.btn_run.clicked.connect(self.start_pipeline)
        
        self.btn_cancel = QPushButton("Cancel Analysis")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet("background-color: #F44336; color: white; padding: 10px; font-weight: bold;")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_pipeline)

        # New Tree Preview checkbox
        self.chk_show_tree = QCheckBox("Show tree after completion")
        self.chk_show_tree.setChecked(True)
        self.chk_show_tree.setCursor(Qt.PointingHandCursor)

        control_layout.addWidget(self.btn_run)
        control_layout.addWidget(self.btn_cancel)
        control_layout.addWidget(self.chk_show_tree)
        
        main_layout.addLayout(control_layout)

        # 4. Log Console
        group_logs = QGroupBox("Execution Log")
        log_layout = QVBoxLayout()
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) 
        log_layout.addWidget(self.log_console)
        group_logs.setLayout(log_layout)
        main_layout.addWidget(group_logs)

        self.setLayout(main_layout)
        self.bind_autosave(self)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.log_console.append("\n[System] Stopping background processes before closing...")
            self.worker.cancel()
            self.worker.wait()
        event.accept()

    def toggle_bootstrap_input(self):
        is_bootstrap = self.cb_support_method.currentData() == "bootstrap"
        self.le_bootstrap_replicates.setEnabled(is_bootstrap)
        if not self._is_loading:
            self.auto_save()

    def update_models(self):
        self.cb_model.clear()
        dt = self.cb_datatype.currentData()
        if dt == "nt":
            models = ["HKY85", "JC69", "K80", "F81", "F84", "TN93", "GTR", "custom"]
        else:
            models = ["LG", "WAG", "JTT", "MtREV", "Dayhoff", "DCMut", "RtREV", 
                      "CPREV", "VT", "Blosum62", "MtMam", "MtArt", "HIVw", "HIVb", "custom"]
        for m in models:
            self.cb_model.addItem(m, m)
        if not self._is_loading:
            self.auto_save()

    def browse_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self, "Select Executable File")
        if path:
            line_edit.setText(path)

    def browse_fasta(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Input File", "", "FASTA Files (*.fasta *.fas *.fa)")
        if path:
            self.fasta_path_input.setText(path)
            self.fasta_file = path

    def bind_autosave(self, parent_widget):
        for child in parent_widget.children():
            if isinstance(child, QLineEdit):
                child.textChanged.connect(self.trigger_autosave)
            elif isinstance(child, QComboBox):
                child.currentIndexChanged.connect(self.trigger_autosave)
            elif isinstance(child, QCheckBox):
                child.toggled.connect(self.trigger_autosave)
            else:
                self.bind_autosave(child)

    def trigger_autosave(self, *args):
        if not self._is_loading:
            self.auto_save()

    def get_current_config(self):
        return {
            "phyml_path": self.phyml_path_input.text(),
            "muscle_path": self.muscle_path_input.text(),
            "datatype": self.cb_datatype.currentData(),
            "model": self.cb_model.currentData(),
            "support_method": self.cb_support_method.currentData(),
            "bootstrap_replicates": self.le_bootstrap_replicates.text(),
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
        except Exception as e:
            pass

    def load_config(self):
        self.update_models()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.phyml_path_input.setText(config.get("phyml_path", ""))
                self.muscle_path_input.setText(config.get("muscle_path", ""))
                
                self.set_combo_by_data(self.cb_datatype, config.get("datatype", "nt"))
                self.update_models()
                self.set_combo_by_data(self.cb_model, config.get("model", "HKY85"))
                self.set_combo_by_data(self.cb_freq, config.get("freq", "default"))
                self.set_combo_by_data(self.cb_support_method, config.get("support_method", "bootstrap"))
                self.set_combo_by_data(self.cb_search, config.get("search", "NNI"))
                self.set_combo_by_data(self.cb_optimize, config.get("optimize", "tlr"))

                self.le_bootstrap_replicates.setText(config.get("bootstrap_replicates", "100"))
                self.le_tstv.setText(config.get("tstv", "e"))
                self.le_pinv.setText(config.get("pinv", "0.0"))
                self.le_classes.setText(config.get("classes", "4"))
                self.le_gamma.setText(config.get("gamma", "e"))
                
                self.chk_parsimony.setChecked(config.get("parsimony", False))
                self.chk_show_tree.setChecked(config.get("show_tree", True))

                self.toggle_bootstrap_input()
                self.log_console.append("[System] Parameters loaded successfully.\n")
            except Exception as e:
                self.log_console.append(f"[ERROR] Failed to read config: {e}\n")

    def set_combo_by_data(self, combo, data_val):
        idx = combo.findData(data_val)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def start_pipeline(self):
        if not self.fasta_file or not os.path.exists(self.fasta_file):
            QMessageBox.warning(self, "Error", "Please specify a valid FASTA file.")
            return

        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log_console.clear()
        
        config = self.get_current_config()
        self.worker = PipelineWorker(config, self.fasta_file)
        self.worker.log_signal.connect(lambda msg: self.log_console.append(msg))
        self.worker.finished_signal.connect(self.pipeline_finished)
        self.worker.start()

    def cancel_pipeline(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.log_console.append("\n[!] Sending interrupt signal to process...")

    def pipeline_finished(self, success, tree_path):
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        
        # If analysis was successful and preview is enabled, open viewer
        if success and self.chk_show_tree.isChecked() and os.path.exists(tree_path):
            self.log_console.append("[*] Opening tree viewer...")
            viewer = TreeViewerDialog(tree_path, self)
            viewer.exec_() # Open window modally

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PhyMLApp()
    window.show()
    sys.exit(app.exec_())