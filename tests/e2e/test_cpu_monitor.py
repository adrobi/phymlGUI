"""Live CPU monitoring of a real MPI run."""
import shutil
import time

import pytest

from datasets import phyml_config, synthetic  # noqa: F401  (fixture)
from phyml_core.pipeline import PipelineWorker
from phyml_ui.main_window import PhyMLApp

pytestmark = [pytest.mark.needs_phyml, pytest.mark.needs_mpi, pytest.mark.needs_muscle]


@pytest.fixture
def window(isolated_config, qtbot):
    # isolated_config goes first so it is torn down last: qtbot closes the
    # window at teardown and closeEvent still writes the (patched) config file
    w = PhyMLApp()
    qtbot.addWidget(w)
    return w


def test_cpu_samples_during_mpi_run(window, qapp, tmp_path, monkeypatch, binaries, synthetic):
    run_dir = tmp_path / 't6_monitor'
    run_dir.mkdir()
    fasta = run_dir / 'test_unaligned.fasta'
    shutil.copy(synthetic['unaligned'], fasta)
    monkeypatch.chdir(run_dir)

    window._cpu_samples = []
    worker = PipelineWorker(phyml_config(binaries), str(fasta))
    window.worker = worker
    done, wlogs = [], []
    worker.log_signal.connect(wlogs.append)
    worker.finished_signal.connect(lambda ok, tree: done.append((ok, tree)))
    worker.start()
    ticks = 0
    while not done and ticks < 300:
        qapp.processEvents()
        time.sleep(0.3)
        window.update_cpu_status()
        ticks += 1
    if done:
        worker.wait()  # the signal is emitted just before the thread exits
    assert done, 'worker did not finish'
    assert done[0][0], 'pipeline failed:\n' + '\n'.join(wlogs[-10:])
    assert window._cpu_samples, 'no CPU samples collected'
    peak = max(window._cpu_samples)
    assert peak > 50, f'analysis CPU unexpectedly low: peak {peak}'
