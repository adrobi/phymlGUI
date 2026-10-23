import os
import re
import subprocess

from PySide6.QtCore import QThread, Signal
from Bio import AlignIO, SeqIO
from Bio.Seq import Seq

from .i18n import _t


def parse_stats(stats_path):
    """Parse key values from a PhyML 3.3 stats file into a dict."""
    try:
        with open(stats_path, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return {}
    def grab(pattern):
        m = re.search(pattern, content)
        return m.group(1) if m else ""
    return {
        'model': grab(r'Model of \w+ substitution:\s*(\S+)'),
        'taxa': grab(r'Number of taxa:\s*(\d+)'),
        'lnL': grab(r'Log-likelihood:\s*(-?[\d.]+)'),
        'gamma': grab(r'Gamma shape parameter:\s*(-?[\d.]+)'),
        'tstv': grab(r'transition/transversion ratio:\s*(-?[\d.]+)'),
        'time': grab(r'Time used:\s*(\S+)'),
    }


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
        self.results = []  # one row per input file, for the CSV summary

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
            ok, tree, stats = self._process_one(fasta)
            row = {'file': os.path.basename(fasta), 'status': 'OK' if ok else 'FAIL', 'tree': tree if ok else ''}
            row.update({k: stats.get(k, '') for k in ('model', 'taxa', 'lnL', 'gamma', 'tstv', 'time')})
            self.results.append(row)
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
        """Full pipeline for a single FASTA file: returns (success, tree_path, stats)."""
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
                    return False, "", {}

                aligned_fasta = current_fasta.rsplit('.', 1)[0] + '_aligned.fasta'
                if os.path.exists(aligned_fasta):
                    try:
                        os.remove(aligned_fasta)
                        self.log_signal.emit(_t("del_old"))
                    except Exception as e:
                        self.log_signal.emit(_t("err_del").format(e))
                        return False, "", {}

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
                    return False, "", {}

                if self.active_process.returncode == 0 and os.path.exists(aligned_fasta):
                    self.log_signal.emit(_t("align_success").format(aligned_fasta))
                    current_fasta = aligned_fasta
                else:
                    self.log_signal.emit(_t("err_muscle_fail"))
                    return False, "", {}
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
                self.log_signal.emit(_t("err_conv").format(e)); return False, "", {}

            if self._is_cancelled: return False, "", {}

            # 3. Run PhyML (MPI support added here)
            phyml_exe = self.config.get("phyml_path", "")
            if not phyml_exe or not os.path.exists(phyml_exe):
                self.log_signal.emit(_t("err_phyml")); return False, "", {}

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
                return False, "", {}
            elif self.active_process.returncode != 0:
                self.log_signal.emit(_t("err_crit_phyml").format(self.active_process.returncode))
                return False, "", {}
            else:
                self.log_signal.emit(_t("success_pipe"))
                tree_path = f"{phylip_path}_phyml_tree.txt"
                stats = parse_stats(tree_path.replace('_phyml_tree.txt', '_phyml_stats.txt'))
                self.log_signal.emit(_t("stats_summary").format(
                    *(stats.get(k) or "n/a" for k in ('model', 'taxa', 'lnL', 'gamma', 'tstv', 'time'))))
                return True, tree_path, stats

        except Exception as e:
            self.log_signal.emit(_t("err_crit").format(str(e)))
            return False, "", {}

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
