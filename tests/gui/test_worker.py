"""RunWorker: PipelineRunner on a QThread, its callbacks turned into Qt signals."""
import time

import pytest

from phyml_core.paths import AppPaths
from phyml_core.runner import LEVELS, PipelineRunner, RunResult
from phyml_ui.worker import RunWorker
from unit.fakes import FakeEngine

ALIGNED = '>A\nACGTACGTAC\n>B\nACGTACGAAC\n>C\nACGAACGTAC\n'


@pytest.fixture
def paths(tmp_path):
    return AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path / 'data'))


def make_worker(tmp_path, paths, **params):
    fasta = tmp_path / 'a.fasta'
    fasta.write_text(ALIGNED, encoding='utf-8')
    params.setdefault('engine', 'fake')
    return RunWorker.for_run(params, [str(fasta)], paths, engines={'fake': FakeEngine()})


def test_worker_emits_log_status_done(qtbot, tmp_path, paths):
    w = make_worker(tmp_path, paths, fake_mode='ok')
    logs, statuses = [], []
    w.log.connect(lambda level, text: logs.append((level, text)))
    w.status.connect(lambda name, status: statuses.append((name, status)))
    with qtbot.waitSignal(w.done, timeout=10000) as blocker:
        w.start()
    w.wait()
    result = blocker.args[0]
    assert isinstance(result, RunResult)
    assert result.success
    assert logs and all(level in LEVELS for level, _ in logs)
    assert any('fake engine: done' in text for level, text in logs if level == 'out')
    assert statuses == [('a.fasta', 'pending'), ('a.fasta', 'running'), ('a.fasta', 'ok')]
    assert w.active_pid is None


def test_worker_wraps_a_given_runner(qtbot, tmp_path, paths):
    fasta = tmp_path / 'a.fasta'
    fasta.write_text(ALIGNED, encoding='utf-8')
    runner = PipelineRunner({'engine': 'fake'}, [str(fasta)], paths,
                            engines={'fake': FakeEngine()})
    w = RunWorker(runner)
    with qtbot.waitSignal(w.done, timeout=10000) as blocker:
        w.start()
    w.wait()
    assert blocker.args[0].success


def test_cancel_returns_at_once_and_ends_the_run(qtbot, tmp_path, paths):
    w = make_worker(tmp_path, paths, fake_mode='hang')
    with qtbot.waitSignal(w.done, timeout=15000) as blocker:
        w.start()
        qtbot.waitUntil(lambda: w.active_pid is not None, timeout=10000)
        started = time.monotonic()
        w.cancel()
        assert time.monotonic() - started < 0.5, 'cancel() blocked the calling thread'
    w.wait()
    result = blocker.args[0]
    assert result.cancelled and result.files[0].status == 'cancelled'
