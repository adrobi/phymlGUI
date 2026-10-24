"""Batch mode: a folder of FASTA files, CSV summary, queue and history."""
import json
import shutil

import pytest
from Bio import Phylo

import phyml_ui.main_window as main_window
from datasets import phyml_config, synthetic  # noqa: F401  (fixture)
from phyml_core.pipeline import PipelineWorker

pytestmark = [pytest.mark.needs_phyml, pytest.mark.needs_mpi, pytest.mark.needs_muscle]


@pytest.fixture
def batch_dir(tmp_path, synthetic):
    """A folder with an unaligned (batchA) and a pre-aligned (batchB) FASTA."""
    run_dir = tmp_path / 't7_batch'
    run_dir.mkdir()
    shutil.copy(synthetic['unaligned'], run_dir / 'batchA.fasta')
    shutil.copy(synthetic['aligned'], run_dir / 'batchB.fasta')
    return run_dir


@pytest.fixture
def gui_batch(window, warned, qtbot, binaries, batch_dir, synthetic):
    """The window after a finished batch run over batch_dir, started with Run."""
    # a MUSCLE output left by an earlier run: the queue must not pick it up
    shutil.copy(synthetic['aligned'], batch_dir / 'batchA_aligned.fasta')
    window.phyml_path_input.setText(binaries['phyml'])
    window.mpirun_path_input.setText(binaries['mpiexec'])
    window.muscle_path_input.setText(binaries['muscle'])
    window.chk_use_mpi.setChecked(True)
    window.set_combo_by_data(window.cb_support_method, 'bootstrap')
    window.le_bootstrap_replicates.setText('20')
    window.le_mpi_np.setText('2')
    window.fasta_path_input.setText(str(batch_dir))
    window.btn_run.click()  # real signal path: clicked(bool) must not break start_pipeline
    assert not warned, f'run was blocked by a warning: {warned}'
    qtbot.waitUntil(lambda: window.btn_run.isEnabled(), timeout=180_000)
    window.worker.wait()
    return window, batch_dir


def test_two_file_batch(qapp, qtbot, binaries, batch_dir):
    """Batch of two files through the real worker (MPI + bootstrap)."""
    files = [str(batch_dir / 'batchA.fasta'), str(batch_dir / 'batchB.fasta')]
    done, logs = [], []
    worker = PipelineWorker(phyml_config(binaries), files)
    worker.log_signal.connect(logs.append)
    worker.finished_signal.connect(lambda ok, tree: done.append((ok, tree)))
    worker.start()
    try:
        qtbot.waitUntil(lambda: bool(done), timeout=180_000)
    finally:
        worker.cancel()
        worker.wait()

    assert done[0][0], 'batch failed:\n' + '\n'.join(logs[-10:])
    assert any('===' in line for line in logs), 'per-file headers missing'
    assert any('2/2' in line for line in logs), 'batch summary missing'
    assert (batch_dir / 'batchA_aligned.fasta').exists(), 'batchA not aligned'
    assert (batch_dir / 'batchA_aligned.phy_phyml_tree.txt').exists()
    tree_b = batch_dir / 'batchB.phy_phyml_tree.txt'
    assert tree_b.exists()
    assert len(Phylo.read(str(tree_b), 'newick').get_terminals()) == 8


def test_gui_batch_writes_summary_csv(gui_batch):
    """Full GUI path: a batch started from the window writes phymlgui_summary.csv."""
    window, run_dir = gui_batch
    assert window.btn_run.isEnabled(), 'pipeline did not finish through GUI path'
    csv_path = run_dir / 'phymlgui_summary.csv'
    assert csv_path.exists(), 'summary CSV missing'
    content = csv_path.read_text(encoding='utf-8-sig')
    assert ('batchA.fasta' in content and 'batchB.fasta' in content
            and 'OK' in content and 'HKY85' in content)
    first_col = [line.split(';')[0] for line in content.splitlines()[1:] if line]
    assert first_col == ['batchA.fasta', 'batchB.fasta'], f'queue leaked artifacts: {first_col}'


def test_queue_history_open_folder(gui_batch):
    """Queue statuses, history record and the open-folder button after a batch."""
    window, _ = gui_batch
    assert window.queue_list.count() == 2
    statuses = [window.queue_list.item(i).text().split('  ')[-1] for i in range(2)]
    assert statuses == ['✓', '✓'], statuses
    with open(main_window.HISTORY_FILE, encoding='utf-8') as f:
        records = json.load(f)
    assert records and records[0]['n'] == 2 and records[0]['ok'] == 2
    assert window.history_list.count() >= 1
    assert window.open_dir_btn.isEnabled()
    assert not window.retry_btn.isVisible() or not window._failed_files
