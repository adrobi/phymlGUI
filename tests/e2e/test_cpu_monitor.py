"""Live CPU monitoring of a real MPI run."""
import shutil
import time

import pytest

from datasets import phyml_config, synthetic  # noqa: F401  (fixture)
from phyml_core.runner import PipelineRunner
from phyml_ui.worker import RunWorker

pytestmark = [pytest.mark.needs_phyml, pytest.mark.needs_mpi, pytest.mark.needs_muscle]


def test_cpu_samples_during_mpi_run(window, qapp, tmp_path, monkeypatch, binaries, synthetic):
    run_dir = tmp_path / 't6_monitor'
    run_dir.mkdir()
    fasta = run_dir / 'test_unaligned.fasta'
    shutil.copy(synthetic['unaligned'], fasta)
    monkeypatch.chdir(run_dir)

    window._cpu_samples = []
    done, wlogs = [], []
    runner = PipelineRunner(phyml_config(binaries), str(fasta), window.paths,
                            on_log=lambda level, text: wlogs.append(text))
    worker = RunWorker(runner)   # the window's CPU monitor asks a RunWorker for active_pid
    window.worker = worker
    worker.done.connect(lambda result: done.append((result.success, result)))
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
