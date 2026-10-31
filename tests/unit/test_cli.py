import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from phyml_core import cli
from phyml_core.runner import FileResult, RunResult

ROOT = Path(__file__).resolve().parents[2]
BLOCK_QT = "import sys; sys.modules['PySide6'] = None; "


def _env(tmp_path):
    env = dict(os.environ)
    env['PHYMLGUI_DATA_DIR'] = str(tmp_path / 'data')
    return env


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('PHYMLGUI_DATA_DIR', str(tmp_path / 'data'))


def test_cli_without_qt_fails_cleanly_on_empty_fasta(tmp_path):
    empty = tmp_path / 'empty.fasta'
    empty.write_text('')
    code = BLOCK_QT + f"import sys; from phyml_core.cli import main; sys.exit(main(['--file', {str(empty)!r}]))"
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=_env(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stderr
    assert 'ImportError' not in r.stderr
    assert 'FAILED' in r.stdout


def test_entry_point_cli_without_qt(tmp_path):
    empty = tmp_path / 'empty.fasta'
    empty.write_text('')
    code = BLOCK_QT + (f"import sys; sys.argv = ['phymlgui.py', '--file', {str(empty)!r}]; "
                       "import phymlgui; phymlgui.main()")
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=_env(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stderr
    assert 'ImportError' not in r.stderr


def test_cli_usage_error_exit_2(capsys):
    assert cli.main([]) == 2
    assert capsys.readouterr().err


def test_cli_empty_batch_dir_exit_2(tmp_path, capsys):
    folder = tmp_path / 'b'
    folder.mkdir()
    (folder / 'x_aligned.fasta').write_text('>a\nA\n')
    (folder / 'notes.txt').write_text('x')
    assert cli.main(['--batch', str(folder)]) == 2
    assert capsys.readouterr().err


def test_cli_missing_paths_exit_2(tmp_path):
    assert cli.main(['--file', str(tmp_path / 'nope.fasta')]) == 2
    assert cli.main(['--batch', str(tmp_path / 'nope')]) == 2
    f = tmp_path / 'a.fasta'
    f.write_text('')
    assert cli.main(['--file', str(f), '--config', str(tmp_path / 'nope.json')]) == 2
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json')
    assert cli.main(['--file', str(f), '--config', str(bad)]) == 2


def test_cli_unreadable_settings_exit_2(tmp_path, monkeypatch, capsys):
    f = tmp_path / 'a.fasta'
    f.write_text('')

    def boom(path, on_error=None):
        raise PermissionError('locked')
    monkeypatch.setattr(cli.settings, 'load', boom)
    assert cli.main(['--file', str(f)]) == 2
    assert 'locked' in capsys.readouterr().err


class _Fake:
    instances = []

    def __init__(self, params, files, paths, on_log=None, on_status=None, engines=None):
        self.params, self.files = params, files
        _Fake.instances.append(self)
        self.on_log = on_log

    def run(self):
        self.on_log('system', 'a → b\n')
        self.on_log('error', 'bad\n')
        return RunResult([FileResult(self.files[0], 'ok', tree='t.nwk')], False)


def test_cli_logs_arrow_through_cp1251_stdout(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'PipelineRunner', _Fake)
    f = tmp_path / 'a.fasta'
    f.write_text('>a\nA\n')
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding='cp1251', newline='')
    err = io.TextIOWrapper(io.BytesIO(), encoding='cp1251', newline='')
    monkeypatch.setattr(sys, 'stdout', out)
    monkeypatch.setattr(sys, 'stderr', err)
    assert cli.main(['--file', str(f)]) == 0
    out.flush()
    text = raw.getvalue().decode('cp1251')
    assert 'a ? b' in text and 'OK' in text and 'tree: t.nwk' in text
    err.flush()
    assert 'bad' in err.buffer.getvalue().decode('cp1251')


def test_cli_config_overlay_and_batch_selection(tmp_path, monkeypatch):
    _Fake.instances.clear()
    monkeypatch.setattr(cli, 'PipelineRunner', _Fake)
    folder = tmp_path / 'b'
    folder.mkdir()
    for n in ('b.FA', 'a.fasta', 'c.fas', 'a_aligned.fasta', 'z.txt'):
        (folder / n).write_text('>a\nA\n')
    cfg = tmp_path / 'c.json'
    cfg.write_text(json.dumps({'model': 'GTR'}))
    cli.main(['--batch', str(folder), '--config', str(cfg)])
    inst = _Fake.instances[0]
    assert [os.path.basename(p) for p in inst.files] == ['a.fasta', 'b.FA', 'c.fas']
    assert inst.params['model'] == 'GTR'
    assert inst.params['engine'] == 'phyml'


def test_cli_empty_mpi_np_becomes_physical_cores(tmp_path, monkeypatch):
    """A fresh machine has no config: the runner must get a real np, not ''."""
    from phyml_core.utils import detect_cores
    _Fake.instances.clear()
    monkeypatch.setattr(cli, 'PipelineRunner', _Fake)
    f = tmp_path / 'a.fasta'
    f.write_text('>a\nA\n')
    assert cli.main(['--file', str(f), '--config', _write(tmp_path, {'engine': 'iqtree'})]) == 0
    params = _Fake.instances[0].params
    assert params['engine'] == 'iqtree'
    assert params['mpi_np'] == str(detect_cores()[0])


def _write(tmp_path, obj):
    path = tmp_path / 'overlay.json'
    path.write_text(json.dumps(obj))
    return str(path)


def test_cli_damaged_config_is_reported_on_stderr_and_defaults_are_used(tmp_path, monkeypatch, capsys):
    from phyml_core.i18n import _t
    _Fake.instances.clear()
    monkeypatch.setattr(cli, 'PipelineRunner', _Fake)
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'phyml_config.json').write_text('{not json')
    f = tmp_path / 'a.fasta'
    f.write_text('>a\nA\n')
    assert cli.main(['--file', str(f)]) == 0
    assert _t('err_settings_broken').split('{}')[0] in capsys.readouterr().err
    assert _Fake.instances[0].params['model'] == 'HKY85'


def test_cli_unusable_data_dir_exit_2_without_traceback(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / 'file'
    blocker.write_text('x')
    monkeypatch.setenv('PHYMLGUI_DATA_DIR', str(blocker / 'sub'))
    f = tmp_path / 'a.fasta'
    f.write_text('>a\nA\n')
    assert cli.main(['--file', str(f)]) == 2
    err = capsys.readouterr().err
    assert err and 'Traceback' not in err


def test_gui_start_shows_a_message_box_when_the_data_folder_fails(tmp_path):
    """Run in a subprocess: it creates its own QApplication."""
    code = '\n'.join([
        "import sys",
        "from PySide6.QtWidgets import QMessageBox",
        "from phyml_core.paths import AppPaths",
        "shown = []",
        "def boom(cls, *a, **k): raise PermissionError(13, 'no data folder')",
        "AppPaths.detect = classmethod(boom)",
        "QMessageBox.critical = lambda *a, **k: shown.append(a[-1])",
        "sys.argv = ['phymlgui.py']",
        "import phymlgui",
        "try:",
        "    phymlgui.main()",
        "except SystemExit as e:",
        "    print('EXIT', e.code, shown)",
    ])
    env = _env(tmp_path)
    env['QT_QPA_PLATFORM'] = 'offscreen'
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    assert 'EXIT 1' in r.stdout and 'no data folder' in r.stdout, r.stdout + r.stderr
