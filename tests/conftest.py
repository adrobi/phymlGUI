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
def isolated_config(tmp_path, monkeypatch):
    """Point the window's config/history files at tmp_path (interim: Task 5 uses data_dir)."""
    import phyml_ui.main_window as main_window
    monkeypatch.setattr(main_window, 'CONFIG_FILE', str(tmp_path / 'phyml_config.json'))
    monkeypatch.setattr(main_window, 'HISTORY_FILE', str(tmp_path / 'phyml_history.json'))
    return tmp_path


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
