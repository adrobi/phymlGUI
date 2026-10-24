import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'tests' / 'data'
sys.path.insert(0, str(ROOT))

_BINARIES = {
    # kind: (env var, bin/ file name, extra local locations)
    'phyml': ('PHYMLGUI_PHYML', 'phyml-mpi.exe',
              [ROOT / 'phymlgui v1.1' / 'phyml-mpi.exe']),
    'mpiexec': ('PHYMLGUI_MPIEXEC', 'mpiexec.exe',
                [Path(r'C:\Program Files\Microsoft MPI\Bin\mpiexec.exe')]),
    'iqtree': ('PHYMLGUI_IQTREE', 'iqtree2.exe',
               [ROOT / 'tools' / 'iqtree2' / 'iqtree2.exe']),
    'muscle': ('PHYMLGUI_MUSCLE', 'muscle.exe',
               [ROOT / 'tools' / 'muscle.exe']),
    'raxml': ('PHYMLGUI_RAXML', 'raxml-ng.exe', []),
}

# marker name -> binary kind (needs_mpi is satisfied by mpiexec)
_MARKER_KINDS = {
    'needs_phyml': 'phyml',
    'needs_mpi': 'mpiexec',
    'needs_iqtree': 'iqtree',
    'needs_muscle': 'muscle',
}


def find_binary(kind):
    """Path to an analysis binary or None: env var, then ROOT/bin, then local installs."""
    env_var, bin_name, local = _BINARIES[kind]
    candidates = []
    if os.environ.get(env_var):
        candidates.append(Path(os.environ[env_var]))
    candidates.append(ROOT / 'bin' / bin_name)
    candidates.extend(local)
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def pytest_runtest_setup(item):
    for marker, kind in _MARKER_KINDS.items():
        if item.get_closest_marker(marker) and find_binary(kind) is None:
            pytest.skip(f'{kind} not found (set {_BINARIES[kind][0]})')


@pytest.fixture(scope='session')
def binaries():
    return {kind: find_binary(kind) for kind in _BINARIES}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """An empty user-data folder for the window, and an empty working folder.

    PHYMLGUI_DATA_DIR sends config and history to tmp_path/data. The cwd is moved to the
    empty tmp_path/cwd, so the legacy migration finds no phyml_config.json there (the real
    one sits in the repository root) and nothing a test does can reach the real files.
    """
    data = tmp_path / 'data'
    cwd = tmp_path / 'cwd'
    data.mkdir()
    cwd.mkdir()
    monkeypatch.setenv('PHYMLGUI_DATA_DIR', str(data))
    monkeypatch.chdir(cwd)
    return data


@pytest.fixture
def make_window(data_dir, qtbot, qapp):
    """Factory of PhyMLApp windows on the isolated data folder: make_window(paths=None).

    The windows are destroyed at teardown, not just closed, and the application stylesheet
    is put back. A started window styles the whole application, and a closed window that
    stays alive makes every later one slower to build (a deleteLater() that only goes
    through processEvents() never deletes anything).

    data_dir is a dependency, so it is torn down after the windows: closing a window runs
    closeEvent -> auto_save(), which must still see the isolated folder (the env override
    and the cwd), never the real one.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from phyml_ui.main_window import PhyMLApp
    original_style = qapp.styleSheet()
    created = []

    def make(paths=None):
        w = PhyMLApp(paths=paths)
        qtbot.addWidget(w)
        created.append(w)
        return w

    yield make
    for w in created:
        w.close()
        w.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.setStyleSheet(original_style)


@pytest.fixture
def window(make_window):
    """A PhyMLApp on an isolated data folder (see make_window)."""
    return make_window()


@pytest.fixture
def warned(monkeypatch):
    """Replace QMessageBox.warning; the returned list collects the call args."""
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, 'warning',
                        staticmethod(lambda *a, **k: shown.append(a) or QMessageBox.Ok))
    return shown


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


@pytest.fixture(scope='session', autouse=True)
def guard_user_files():
    """Fail the session if a test touched the user's real config or history."""
    files = [ROOT / 'phyml_config.json', ROOT / 'phyml_history.json']
    before = {f: _digest(f) for f in files}
    yield
    after = {f: _digest(f) for f in files}
    assert after == before, 'tests modified the real user config/history files'
