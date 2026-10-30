import os
import subprocess
import sys
import threading
import time

import psutil
import pytest

from fakes import FakeEngine, fake_muscle
from fake_tool import SLEEPER
from phyml_core import runner as runner_module
from phyml_core.engines.base import Issue, format_issue
from phyml_core.i18n import _t
from phyml_core.paths import AppPaths
from phyml_core.runner import LEVELS, FileResult, PipelineRunner, RunResult, kill_process_tree

ALIGNED = [('A', 'ACGTACGTAC'), ('B', 'ACGTACGAAC'), ('C', 'ACGAACGTAC')]
UNALIGNED = [('A', 'ACGTACGTAC'), ('B', 'ACGTAC'), ('C', 'ACGAACGTACGT')]

WAIT = 15   # seconds: the upper bound of every wait, so a bug cannot hang the suite


def write_fasta(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(f'>{rid}\n{seq}\n' for rid, seq in records), encoding='utf-8')
    return str(path)


@pytest.fixture
def paths(tmp_path):
    return AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path / 'data'))


class Recorder:
    """on_log / on_status that keep what they got; `running` is set by the first 'running'."""

    def __init__(self):
        self.logs = []
        self.statuses = []
        self.running = threading.Event()

    def on_log(self, level, text):
        self.logs.append((level, text))

    def on_status(self, name, status):
        self.statuses.append((name, status))
        if status == 'running':
            self.running.set()

    def texts(self, level=None):
        return [text for lvl, text in self.logs if level is None or lvl == level]

    def statuses_of(self, name):
        return [status for n, status in self.statuses if n == name]


def make_runner(files, paths, rec=None, **params):
    rec = rec or Recorder()
    params.setdefault('engine', 'fake')
    return PipelineRunner(params, files, paths, on_log=rec.on_log, on_status=rec.on_status,
                          engines={'fake': FakeEngine()})


def start(runner):
    """run() in a daemon thread; box['result'] gets the RunResult."""
    box = {}
    thread = threading.Thread(target=lambda: box.update(result=runner.run()), daemon=True)
    thread.start()
    return thread, box


def wait_for_sleeper(runner):
    """The process tree of the current step once its sleeping grandchild is up."""
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        pid = runner.active_pid
        if pid is not None:
            try:
                root = psutil.Process(pid)
                descendants = root.children(recursive=True)
                if any(SLEEPER in ' '.join(_cmdline(p)) for p in descendants):
                    return [root, *descendants]
            except psutil.Error:
                pass
        time.sleep(0.05)
    raise AssertionError('the fake tool never started its sleeping child')


def _cmdline(proc):
    try:
        return proc.cmdline()
    except psutil.Error:
        return []


def alive(proc):
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def kill_all(procs):
    for proc in procs:
        try:
            proc.kill()
        except psutil.Error:
            pass


# --- results ----------------------------------------------------------------------------

def test_run_result_counts_and_success():
    ok, fail = FileResult('a.fasta', 'ok'), FileResult('b.fasta', 'fail')
    assert RunResult([ok, ok], cancelled=False).success
    assert RunResult([ok, fail], cancelled=False).ok_count == 1
    assert not RunResult([ok, fail], cancelled=False).success
    assert not RunResult([ok], cancelled=True).success
    assert not RunResult([], cancelled=False).success


def test_ok_run_returns_tree_and_stats(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    rec = Recorder()
    result = make_runner([fasta], paths, rec).run()
    assert isinstance(result, RunResult)
    assert not result.cancelled and result.success and result.ok_count == 1
    file = result.files[0]
    assert file.file == fasta
    assert file.status == 'ok' and file.error == ''
    assert file.tree == str(tmp_path / 'a.phy') + '_fake_tree.txt'
    assert os.path.isfile(file.tree)
    assert file.stats == {'model': 'FAKE', 'taxa': '3', 'lnL': '-123.45', 'gamma': '0.5',
                          'tstv': '2.0', 'time': '1s'}
    assert rec.statuses == [('a.fasta', 'pending'), ('a.fasta', 'running'), ('a.fasta', 'ok')]
    assert any('fake engine: done' in text for text in rec.texts('out'))
    assert _t('seq_aligned') in rec.texts('success')


def test_empty_fasta_fails_cleanly(tmp_path, paths):
    """A broken input fails the file instead of raising out of run()."""
    empty = tmp_path / 'empty.fasta'
    empty.write_text('')
    rec = Recorder()
    result = make_runner([str(empty)], paths, rec).run()
    assert not result.success
    assert result.files[0].status == 'fail'
    assert _t('err_empty') in result.files[0].error
    assert rec.statuses_of('empty.fasta') == ['pending', 'running', 'fail']
    assert any(_t('err_empty') in text for text in rec.texts('error'))


def test_header_only_fasta_fails_with_err_empty(tmp_path, paths):
    fasta = tmp_path / 'headers.fasta'
    fasta.write_text('>A\n>B\n')
    result = make_runner([str(fasta)], paths).run()
    assert result.files[0].status == 'fail'
    assert _t('err_empty') in result.files[0].error


def test_engine_exit_code_reported(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    rec = Recorder()
    result = make_runner([fasta], paths, rec, fake_mode='exit3').run()
    assert result.files[0].status == 'fail'
    assert result.files[0].error == _t('err_engine_exit').format('Fake', 3)
    assert _t('err_engine_exit').format('Fake', 3) in rec.texts('error')


def test_missing_tree_reported(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    result = make_runner([fasta], paths, fake_mode='notree').run()
    tree = str(tmp_path / 'a.phy') + '_fake_tree.txt'
    assert result.files[0].status == 'fail'
    assert result.files[0].error == _t('err_no_tree').format('Fake', tree)


def test_engine_exception_never_escapes(tmp_path, paths):
    bad = write_fasta(tmp_path / 'bad.fasta', ALIGNED)
    good = write_fasta(tmp_path / 'good.fasta', ALIGNED)
    rec = Recorder()
    result = make_runner([bad, good], paths, rec, fake_mode={'bad': 'raise'}).run()
    assert [f.status for f in result.files] == ['fail', 'ok']
    assert 'boom' in result.files[0].error
    assert rec.statuses_of('good.fasta') == ['pending', 'running', 'ok']
    assert any('boom' in text for text in rec.texts('error'))


def test_validate_error_stops_file_and_warning_is_logged(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    warning = Issue('warning', 'iqtree_ufboot_min', ('1000', '10'))
    error = Issue('error', 'val_no_exe', ('Fake', 'C:/nowhere/fake.exe'))
    rec = Recorder()
    result = make_runner([fasta], paths, rec, fake_issues=[warning, error]).run()
    file = result.files[0]
    assert file.status == 'fail'
    assert file.error == format_issue(error)
    assert format_issue(warning) in rec.texts('system')
    assert format_issue(error) in rec.texts('error')
    assert not os.path.exists(str(tmp_path / 'a.phy') + '_fake_tree.txt')
    assert rec.texts('out') == []   # the engine never started


def test_warnings_and_notes_do_not_stop_the_file(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    warning = Issue('warning', 'val_no_mpiexec', ('mpiexec',))
    note = Issue('warning', 'iqtree_ufboot_min', ('1000', '10'))
    rec = Recorder()
    result = make_runner([fasta], paths, rec, fake_issues=[warning], fake_notes=[note]).run()
    assert result.files[0].status == 'ok'
    assert format_issue(warning) in rec.texts('system')
    assert format_issue(note) in rec.texts('system')


def test_id_collision_fails_with_listing(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', [('A.1', 'ACGT'), ('A_1', 'ACGA'), ('B', 'ACGG')])
    result = make_runner([fasta], paths).run()
    file = result.files[0]
    assert file.status == 'fail'
    assert 'A.1' in file.error and 'A_1' in file.error
    assert file.error.startswith(_t('err_id_collision').split('{}')[0])
    assert not (tmp_path / 'a.phy').exists()


def test_unaligned_input_runs_muscle(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', UNALIGNED)
    rec = Recorder()
    result = make_runner([fasta], paths, rec, muscle_path=fake_muscle(tmp_path, 'copy')).run()
    aligned = tmp_path / 'a_aligned.fasta'
    assert aligned.is_file()
    assert result.files[0].status == 'ok', result.files[0].error
    assert result.files[0].tree == str(tmp_path / 'a_aligned.phy') + '_fake_tree.txt'
    assert _t('diff_len') in rec.texts('system')
    assert _t('align_success').format(str(aligned)) in rec.texts('success')


def test_muscle_falls_back_to_v3_syntax(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', UNALIGNED)
    result = make_runner([fasta], paths, muscle_path=fake_muscle(tmp_path, 'v3only')).run()
    assert result.files[0].status == 'ok', result.files[0].error
    assert (tmp_path / 'a_aligned.fasta').is_file()


def test_old_alignment_is_replaced(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', UNALIGNED)
    (tmp_path / 'a_aligned.fasta').write_text('stale')
    rec = Recorder()
    result = make_runner([fasta], paths, rec, muscle_path=fake_muscle(tmp_path, 'copy')).run()
    assert result.files[0].status == 'ok', result.files[0].error
    assert _t('del_old') in rec.texts('system')
    assert (tmp_path / 'a_aligned.fasta').read_text().startswith('>A')


def test_missing_muscle_fails_with_err_muscle(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', UNALIGNED)
    rec = Recorder()
    result = make_runner([fasta], paths, rec, muscle_path=str(tmp_path / 'no-muscle.exe')).run()
    assert result.files[0].status == 'fail'
    assert result.files[0].error == _t('err_muscle')
    assert _t('err_muscle') in rec.texts('error')


def test_unknown_engine_fails_the_files(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    result = make_runner([fasta], paths, engine='raxml').run()
    assert result.files[0].status == 'fail'
    assert 'raxml' in result.files[0].error


def test_batch_logs_found_header_and_summary(tmp_path, paths):
    a = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    b = write_fasta(tmp_path / 'b.fasta', ALIGNED)
    rec = Recorder()
    result = make_runner([a, b], paths, rec, fake_mode={'b': 'exit3'}).run()
    assert [f.status for f in result.files] == ['ok', 'fail']
    assert [f.file for f in result.files] == [a, b]
    texts = rec.texts()
    assert _t('batch_found').format(2) in texts
    assert _t('batch_file_header').format(1, 2, 'a.fasta').rstrip('\n') in texts
    assert _t('batch_file_header').format(2, 2, 'b.fasta').rstrip('\n') in texts
    assert _t('batch_summary').format(1, 2).rstrip('\n') in texts
    assert rec.statuses[:2] == [('a.fasta', 'pending'), ('b.fasta', 'pending')]


def test_log_levels_are_from_levels(tmp_path, paths):
    files = [write_fasta(tmp_path / 'ok.fasta', ALIGNED),
             write_fasta(tmp_path / 'msa.fasta', UNALIGNED),
             write_fasta(tmp_path / 'bad.fasta', [('A.1', 'ACGT'), ('A_1', 'ACGA')]),
             write_fasta(tmp_path / 'exit.fasta', ALIGNED)]
    rec = Recorder()
    make_runner(files, paths, rec, muscle_path=fake_muscle(tmp_path, 'copy'),
                fake_mode={'exit': 'exit3'},
                fake_notes=[Issue('warning', 'iqtree_ufboot_min', ('1000', '10'))]).run()
    levels = {level for level, _ in rec.logs}
    assert levels <= set(LEVELS)
    assert levels == set(LEVELS)   # the scenario produces every level
    assert all(not text.endswith('\n') for text in rec.texts())


def test_undecodable_engine_output_is_replaced(tmp_path, paths):
    """fake_tool 'ok' prints bytes that no single codec decodes cleanly."""
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    rec = Recorder()
    result = make_runner([fasta], paths, rec).run()
    assert result.files[0].status == 'ok', result.files[0].error
    assert any(text.startswith('progress ') for text in rec.texts('out'))


def test_run_in_cyrillic_dir_with_spaces(tmp_path, paths):
    folder = tmp_path / 'Мои данные' / 'проект 1'
    aligned = write_fasta(folder / 'выборка 1.fasta', ALIGNED)
    unaligned = write_fasta(folder / 'выборка 2.fasta', UNALIGNED)
    rec = Recorder()
    result = make_runner([aligned, unaligned], paths, rec,
                         muscle_path=fake_muscle(tmp_path, 'copy')).run()
    assert [f.status for f in result.files] == ['ok', 'ok'], [f.error for f in result.files]
    assert result.files[0].tree == str(folder / 'выборка 1.phy') + '_fake_tree.txt'
    assert os.path.isfile(result.files[0].tree)
    assert (folder / 'выборка 2_aligned.fasta').is_file()
    assert os.path.isfile(result.files[1].tree)
    assert rec.statuses_of('выборка 1.fasta') == ['pending', 'running', 'ok']


# --- cancel -------------------------------------------------------------------------------

def test_cancel_kills_process_tree(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    rec = Recorder()
    runner = make_runner([fasta], paths, rec, fake_mode='hang')
    thread, box = start(runner)
    procs = []
    try:
        assert rec.running.wait(WAIT)
        procs = wait_for_sleeper(runner)
        assert procs[0].pid == runner.active_pid
        started = time.monotonic()
        canceller = threading.Thread(target=runner.cancel, daemon=True)
        canceller.start()
        canceller.join(WAIT)
        thread.join(WAIT)
        assert not thread.is_alive(), 'run() did not return after cancel()'
        assert time.monotonic() - started < 10
        result = box['result']
        assert result.cancelled and not result.success
        assert result.files[0].status == 'cancelled'
        assert rec.statuses_of('a.fasta') == ['pending', 'running', 'cancelled']
        assert [p.pid for p in procs if alive(p)] == []
        assert runner.active_pid is None
        assert _t('cancel_analysis').rstrip('\n') in rec.texts('system')
    finally:
        runner.cancel()
        kill_all(procs)


def test_cancel_during_alignment_marks_rest_cancelled(tmp_path, paths):
    first = write_fasta(tmp_path / 'a.fasta', UNALIGNED)
    second = write_fasta(tmp_path / 'b.fasta', UNALIGNED)
    rec = Recorder()
    runner = make_runner([first, second], paths, rec, muscle_path=fake_muscle(tmp_path, 'hang'))
    thread, box = start(runner)
    procs = []
    try:
        procs = wait_for_sleeper(runner)
        canceller = threading.Thread(target=runner.cancel, daemon=True)
        canceller.start()
        canceller.join(WAIT)
        thread.join(WAIT)
        assert not thread.is_alive(), 'run() did not return after cancel()'
        result = box['result']
        assert result.cancelled
        assert [f.status for f in result.files] == ['cancelled', 'cancelled']
        assert [f.file for f in result.files] == [first, second]
        assert rec.statuses_of('a.fasta') == ['pending', 'running', 'cancelled']
        assert rec.statuses_of('b.fasta') == ['pending', 'cancelled']
        assert [p.pid for p in procs if alive(p)] == []
        assert _t('cancel_align') in rec.texts('system')
        assert not (tmp_path / 'a_aligned.phy').exists()
    finally:
        runner.cancel()
        kill_all(procs)


def test_cancel_before_run_cancels_every_file(tmp_path, paths):
    files = [write_fasta(tmp_path / 'a.fasta', ALIGNED), write_fasta(tmp_path / 'b.fasta', ALIGNED)]
    rec = Recorder()
    runner = make_runner(files, paths, rec)
    runner.cancel()
    result = runner.run()
    assert result.cancelled
    assert [f.status for f in result.files] == ['cancelled', 'cancelled']
    assert rec.statuses_of('a.fasta') == ['pending', 'cancelled']
    assert not (tmp_path / 'a.phy').exists()


def test_cancel_from_a_callback_and_after_finish_is_safe(tmp_path, paths):
    files = [write_fasta(tmp_path / 'a.fasta', ALIGNED), write_fasta(tmp_path / 'b.fasta', ALIGNED)]
    rec = Recorder()
    holder = {}

    def on_status(name, status):
        rec.on_status(name, status)
        if status == 'running':
            holder['runner'].cancel()   # on the runner's own thread, between steps

    runner = PipelineRunner({'engine': 'fake'}, files, paths, on_log=rec.on_log,
                            on_status=on_status, engines={'fake': FakeEngine()})
    holder['runner'] = runner
    thread, box = start(runner)
    thread.join(WAIT)
    assert not thread.is_alive()
    assert [f.status for f in box['result'].files] == ['cancelled', 'cancelled']
    runner.cancel()   # after run() returned
    runner.cancel()
    assert runner.active_pid is None


def test_error_while_cancelled_keeps_its_message(tmp_path, paths):
    """A real failure that coincides with a cancel is 'cancelled' but not silent."""
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    rec = Recorder()
    holder = {}
    converted = _t('conv_success').split('{}')[0]

    def on_log(level, text):
        rec.on_log(level, text)
        if text.startswith(converted):   # past the last checkpoint before the engine step
            holder['runner'].cancel()

    runner = PipelineRunner({'engine': 'fake', 'fake_mode': 'raise'}, [fasta], paths,
                            on_log=on_log, on_status=rec.on_status,
                            engines={'fake': FakeEngine()})
    holder['runner'] = runner
    result = runner.run()
    file = result.files[0]
    assert result.cancelled
    assert file.status == 'cancelled'
    assert 'boom' in file.error
    assert any('boom' in text for text in rec.texts('error'))


def test_cancel_does_not_hold_the_lock_while_killing(tmp_path, paths, monkeypatch):
    """cancel() kills outside the runner's lock: a slow kill must not block other threads."""
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    rec = Recorder()
    runner = make_runner([fasta], paths, rec, fake_mode='hang')
    real_kill = runner_module.kill_process_tree
    seen = {}

    def slow_kill(pid):
        acquired = runner._lock.acquire(timeout=2)   # same thread: fails if cancel holds it
        if acquired:
            runner._lock.release()
        seen['lock_free'] = acquired
        time.sleep(0.5)
        real_kill(pid)

    monkeypatch.setattr(runner_module, 'kill_process_tree', slow_kill)
    thread, box = start(runner)
    procs = []
    try:
        procs = wait_for_sleeper(runner)
        canceller = threading.Thread(target=runner.cancel, daemon=True)
        canceller.start()
        canceller.join(WAIT)
        thread.join(WAIT)
        assert not thread.is_alive(), 'run() did not return after cancel()'
        assert seen == {'lock_free': True}
        assert box['result'].files[0].status == 'cancelled'
    finally:
        runner.cancel()
        kill_all(procs)


def test_callbacks_that_raise_do_not_escape(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)

    def broken(*args):
        raise RuntimeError('callback')

    runner = PipelineRunner({'engine': 'fake'}, [fasta], paths, on_log=broken, on_status=broken,
                            engines={'fake': FakeEngine()})
    assert runner.run().files[0].status == 'ok'


def test_runner_without_callbacks(tmp_path, paths):
    fasta = write_fasta(tmp_path / 'a.fasta', ALIGNED)
    runner = PipelineRunner({'engine': 'fake'}, [fasta], paths, engines={'fake': FakeEngine()})
    assert runner.run().success


# --- kill_process_tree --------------------------------------------------------------------

def _spawn_tree():
    """A python that starts a sleeping child, once the child is up: [parent, child]."""
    script = ('import subprocess, sys, time; '
              f'subprocess.Popen([sys.executable, "-c", {SLEEPER!r}]); time.sleep(60)')
    proc = subprocess.Popen([sys.executable, '-c', script])
    parent = psutil.Process(proc.pid)
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        children = parent.children(recursive=True)
        if children:
            return proc, [parent, *children]
        time.sleep(0.05)
    proc.kill()
    raise AssertionError('the child never started')


def test_kill_process_tree_kills_children():
    proc, procs = _spawn_tree()
    try:
        kill_process_tree(proc.pid)
        proc.wait(WAIT)
        assert [p.pid for p in procs if alive(p)] == []
    finally:
        kill_all(procs)


def test_kill_process_tree_ignores_a_finished_process():
    proc = subprocess.Popen([sys.executable, '-c', 'pass'])
    proc.wait(WAIT)
    kill_process_tree(proc.pid)   # must not raise


def test_kill_process_tree_without_psutil_terminates_the_process(monkeypatch):
    monkeypatch.setattr(runner_module, 'psutil', None)
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        kill_process_tree(proc.pid)
        proc.wait(WAIT)
        kill_process_tree(proc.pid)   # gone: ignored
    finally:
        if proc.poll() is None:
            proc.kill()


def test_runner_module_imports_no_qt():
    code = ('import sys; import phyml_core.runner; '
            'sys.exit(1 if any(m.startswith("PySide6") for m in sys.modules) else 0)')
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert subprocess.run([sys.executable, '-c', code], cwd=root, timeout=60).returncode == 0
