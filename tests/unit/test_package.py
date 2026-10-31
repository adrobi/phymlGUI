"""Release packaging helpers (packaging/package.py) and the --version flag."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('package', ROOT / 'packaging' / 'package.py')
package = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(package)


@pytest.mark.parametrize('tag, version', [('v2.0.0', '2.0.0'), ('v2.0.0-rc1', '2.0.0-rc1'),
                                          ('v10.11.12', '10.11.12')])
def test_version_from_tag(tag, version):
    assert package.version_from_tag(tag) == version


@pytest.mark.parametrize('tag', ['2.0.0', 'v2', 'v2.0', 'release-1', 'v2.0.0 ', 'v2.0.0-'])
def test_version_from_tag_rejects(tag):
    with pytest.raises(ValueError):
        package.version_from_tag(tag)


def test_stamp_version_does_not_touch_repo_file(tmp_path):
    repo_init = ROOT / 'phyml_core' / '__init__.py'
    before = repo_init.read_bytes()
    copy = tmp_path / '__init__.py'
    copy.write_bytes(before)
    package.stamp_version('2.0.0-rc1', str(copy))
    assert '__version__ = "2.0.0-rc1"' in copy.read_text('utf-8')
    assert repo_init.read_bytes() == before


def test_cli_version_flag():
    from phyml_core import __version__
    r = subprocess.run([sys.executable, str(ROOT / 'phymlgui.py'), '--version'],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f'phymlGUI {__version__}'
