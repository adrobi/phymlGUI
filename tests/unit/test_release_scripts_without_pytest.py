"""Release jobs install only requirements.txt: their scripts must not need pytest."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRELUDE = f"""
import importlib.util, sys
sys.modules['pytest'] = None   # import pytest -> ImportError, as on a release runner
def load(name):
    spec = importlib.util.spec_from_file_location(name, {str(ROOT / 'packaging')!r} + '/' + name + '.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
"""


def _run(code, cwd):
    return subprocess.run([sys.executable, '-c', PRELUDE + code], cwd=cwd,
                          capture_output=True, text=True, timeout=120)


def test_parity_inputs_are_generated_without_pytest(tmp_path):
    r = _run("""
try:
    load('raxml_parity').run('no-such-raxml-ng', 'out')
except FileNotFoundError:
    pass
""", tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'out' / 'parity.phy').is_file()


def test_smoke_dataset_is_generated_without_pytest(tmp_path):
    r = _run("""
import os
try:
    load('smoke_test')._analysis(['no-such-phymlgui'], dict(os.environ), '.', 'phyml', {})
except FileNotFoundError:
    pass
""", tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'phyml' / 'unaligned.fasta').is_file()
