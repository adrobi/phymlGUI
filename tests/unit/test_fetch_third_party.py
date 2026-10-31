import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'fetch_third_party', ROOT / 'scripts' / 'fetch_third_party.py')
fetch_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_mod)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_fetch_verifies_sha256(tmp_path):
    src = tmp_path / 'tool.exe'
    src.write_bytes(b'payload')
    dest = tmp_path / 'bin'
    spec = {'url': src.as_uri(), 'sha256': '0' * 64, 'save_as': 'tool.exe'}
    with pytest.raises(ValueError) as err:
        fetch_mod.fetch('tool', spec, str(dest))
    assert '0' * 64 in str(err.value)
    assert _sha(src) in str(err.value)
    assert not dest.exists() or list(dest.iterdir()) == []


def test_fetch_save_as(tmp_path):
    src = tmp_path / 'muscle-win64.v5.3.exe'
    src.write_bytes(b'payload')
    dest = tmp_path / 'bin'
    spec = {'url': src.as_uri(), 'sha256': _sha(src), 'save_as': 'muscle.exe'}
    paths = fetch_mod.fetch('muscle', spec, str(dest))
    assert [Path(p) for p in paths] == [dest / 'muscle.exe']
    assert (dest / 'muscle.exe').read_bytes() == b'payload'


def test_fetch_extracts_listed_members(tmp_path):
    archive = tmp_path / 'pkg.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('pkg/bin/tool.exe', b'exe')
        z.writestr('pkg/readme.txt', b'text')
    dest = tmp_path / 'bin'
    spec = {'url': archive.as_uri(), 'sha256': _sha(archive),
            'extract': {'pkg/bin/tool.exe': 'tool.exe'}}
    paths = fetch_mod.fetch('pkg', spec, str(dest))
    assert [Path(p) for p in paths] == [dest / 'tool.exe']
    assert sorted(p.name for p in dest.iterdir()) == ['tool.exe']
    assert (dest / 'tool.exe').read_bytes() == b'exe'
