"""Tests for the stretching CPU bar and batch mode."""
import os, sys, time, shutil

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import phymlgui
from PySide6.QtWidgets import QSizePolicy, QMessageBox

app = phymlgui.QApplication([])
if not all(os.path.exists(p) for p in (
        os.path.join(ROOT, 'phymlgui v1.1', 'phyml-mpi.exe'),
        os.path.join(ROOT, 'tools', 'muscle.exe'))):
    print('SKIP: local analysis binaries not found')
    sys.exit(0)

w = phymlgui.PhyMLApp()

# 1. CPU bar expands to fill free status bar space
assert w.cpu_sys_bar.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
print('PASS status bar: cpu bar has Expanding policy')

# 2. empty-folder guard
empty_dir = os.path.abspath(os.path.join('testrun', 't8_empty_dir'))
os.makedirs(empty_dir, exist_ok=True)
warned = []
phymlgui.QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a) or QMessageBox.Ok)
w.fasta_path_input.setText(empty_dir)
w.start_pipeline()
assert warned, 'empty folder must trigger a warning'
assert w.worker is None or not w.worker.isRunning()
print('PASS batch guard: empty folder blocked with warning')

# 3. batch of two files through the real worker (MPI + bootstrap)
run_dir = os.path.join('testrun', 't7_batch')
shutil.rmtree(run_dir, ignore_errors=True)
os.makedirs(run_dir, exist_ok=True)
shutil.copy('testrun/test_unaligned.fasta', os.path.join(run_dir, 'batchA.fasta'))
shutil.copy('testrun/test_prealigned.fasta', os.path.join(run_dir, 'batchB.fasta'))

config = {
    'phyml_path': os.path.join(ROOT, 'phymlgui v1.1', 'phyml-mpi.exe'),
    'muscle_path': os.path.join(ROOT, 'tools', 'muscle.exe'),
    'mpirun_path': r'C:\Program Files\Microsoft MPI\Bin\mpiexec.exe',
    'mpi_np': '2', 'use_mpi': True, 'datatype': 'nt', 'model': 'HKY85',
    'support_method': 'bootstrap', 'bootstrap_replicates': '20',
    'freq': 'default', 'tstv': 'e', 'pinv': '0.0', 'classes': '4',
    'gamma': 'e', 'search': 'NNI', 'optimize': 'tlr', 'parsimony': False,
}
files = [os.path.join(run_dir, 'batchA.fasta'), os.path.join(run_dir, 'batchB.fasta')]
done, logs = [], []
worker = phymlgui.PipelineWorker(config, files)
worker.log_signal.connect(logs.append)
worker.finished_signal.connect(lambda ok, tree: done.append((ok, tree)))
worker.start()
while not done:
    app.processEvents()
    time.sleep(0.3)

assert done[0][0], 'batch failed:\n' + '\n'.join(logs[-10:])
assert any('===' in l for l in logs), 'per-file headers missing'
assert any('2/2' in l for l in logs), 'batch summary missing'
assert os.path.exists(os.path.join(run_dir, 'batchA_aligned.fasta')), 'batchA not aligned'
assert os.path.exists(os.path.join(run_dir, 'batchA_aligned.phy_phyml_tree.txt'))
assert os.path.exists(os.path.join(run_dir, 'batchB.phy_phyml_tree.txt'))
from Bio import Phylo
assert len(Phylo.read(os.path.join(run_dir, 'batchB.phy_phyml_tree.txt'), 'newick').get_terminals()) == 8
print('PASS batch: 2/2 files processed, trees for both, headers and summary logged')

# 4. full GUI path: batch via start_pipeline writes phymlgui_summary.csv
cfg_bak = None
if os.path.exists(phymlgui.CONFIG_FILE):
    import shutil as _sh
    cfg_bak = phymlgui.CONFIG_FILE + '.bak'
    _sh.copy(phymlgui.CONFIG_FILE, cfg_bak)
try:
    w.le_bootstrap_replicates.setText('20')   # user config may hold 10000+
    w.le_mpi_np.setText('2')
    run_dir_abs = os.path.abspath(run_dir)
    w.fasta_path_input.setText(run_dir_abs)
    w.start_pipeline()
    guard = 0
    while (not w.btn_run.isEnabled()) and guard < 400:
        app.processEvents(); time.sleep(0.3); guard += 1
    assert w.btn_run.isEnabled(), 'pipeline did not finish through GUI path'
    csv_path = os.path.join(run_dir, 'phymlgui_summary.csv')
    assert os.path.exists(csv_path), 'summary CSV missing'
    content = open(csv_path, encoding='utf-8-sig').read()
    assert 'batchA.fasta' in content and 'batchB.fasta' in content and 'OK' in content and 'HKY85' in content
    first_col = [l.split(';')[0] for l in content.splitlines()[1:] if l]
    assert first_col == ['batchA.fasta', 'batchB.fasta'], f'queue leaked artifacts: {first_col}'
    print('PASS csv summary: phymlgui_summary.csv written with both files and stats')

    # 5. stage-3: queue statuses, history record, open-folder enabled
    assert w.queue_list.count() == 2
    statuses = [w.queue_list.item(i).text().split('  ')[-1] for i in range(2)]
    assert statuses == ['✓', '✓'], statuses
    import json as _json
    from phyml_ui.main_window import HISTORY_FILE
    records = _json.load(open(HISTORY_FILE, encoding='utf-8'))
    assert records and records[0]['n'] == 2 and records[0]['ok'] == 2
    assert w.history_list.count() >= 1
    assert w.open_dir_btn.isEnabled()
    assert not w.retry_btn.isVisible() or not w._failed_files
    print('PASS stage3: queue statuses, history record, open-folder enabled')
finally:
    if cfg_bak:
        import shutil as _sh
        _sh.move(cfg_bak, phymlgui.CONFIG_FILE)
print('ALL BATCH TESTS PASSED')
