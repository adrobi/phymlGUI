import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOCK_QT = "import sys; sys.modules['PySide6'] = None; "


def test_core_has_no_qt():
    code = BLOCK_QT + ("import pkgutil, importlib, phyml_core; "
                       "[importlib.import_module(m.name) for m in "
                       "pkgutil.walk_packages(phyml_core.__path__, 'phyml_core.')]")
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_entry_point_has_no_compat_reexports():
    code = BLOCK_QT + "import phymlgui; print(hasattr(phymlgui, 'PhyMLApp'), hasattr(phymlgui, 'QApplication'))"
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ['False', 'False']
