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


def test_fetch_extracts_tar_gz_member(tmp_path):
    import tarfile
    payload = tmp_path / 'iqtree2'
    payload.write_bytes(b'elf')
    archive = tmp_path / 'iq.tar.gz'
    with tarfile.open(archive, 'w:gz') as t:
        t.add(payload, arcname='iqtree-2.4.0-Linux-intel/bin/iqtree2')
        t.add(payload, arcname='iqtree-2.4.0-Linux-intel/bin/other')
    dest = tmp_path / 'bin'
    spec = {'url': archive.as_uri(), 'sha256': _sha(archive),
            'extract': {'iqtree-2.4.0-Linux-intel/bin/iqtree2': 'iqtree2'}}
    paths = fetch_mod.fetch('iqtree', spec, str(dest))
    assert [Path(p) for p in paths] == [dest / 'iqtree2']
    assert sorted(p.name for p in dest.iterdir()) == ['iqtree2']


def test_fetch_runs_build_script(tmp_path):
    import sys
    src = tmp_path / 'src.tar.gz'
    src.write_bytes(b'sources')
    builder = tmp_path / 'builder.py'
    builder.write_text(
        'import sys, pathlib\n'
        'archive, dest = sys.argv[1], pathlib.Path(sys.argv[2])\n'
        'dest.mkdir(parents=True, exist_ok=True)\n'
        "(dest / 'phyml').write_bytes(pathlib.Path(archive).read_bytes())\n", 'utf-8')
    dest = tmp_path / 'bin'
    spec = {'url': src.as_uri(), 'sha256': _sha(src),
            'build': [sys.executable, str(builder)], 'outputs': ['phyml']}
    paths = fetch_mod.fetch('phyml', spec, str(dest))
    assert [Path(p) for p in paths] == [dest / 'phyml']
    assert (dest / 'phyml').read_bytes() == b'sources'


def test_fetch_build_missing_output_fails(tmp_path):
    import sys
    src = tmp_path / 'src.tar.gz'
    src.write_bytes(b'sources')
    builder = tmp_path / 'builder.py'
    builder.write_text('pass\n', 'utf-8')
    spec = {'url': src.as_uri(), 'sha256': _sha(src),
            'build': [sys.executable, str(builder)], 'outputs': ['phyml']}
    with pytest.raises(ValueError):
        fetch_mod.fetch('phyml', spec, str(tmp_path / 'bin'))


@pytest.mark.skipif(__import__('os').name == 'nt', reason='POSIX file modes')
def test_fetch_sets_mode_on_posix(tmp_path):
    import os, stat
    src = tmp_path / 'muscle-linux'
    src.write_bytes(b'elf')
    spec = {'url': src.as_uri(), 'sha256': _sha(src), 'save_as': 'muscle', 'mode': '755'}
    fetch_mod.fetch('muscle', spec, str(tmp_path / 'bin'))
    assert stat.S_IMODE(os.stat(tmp_path / 'bin' / 'muscle').st_mode) == 0o755


def test_manifest_has_both_platforms_and_valid_hashes():
    import json, re
    manifest = json.loads((ROOT / 'packaging' / 'third_party.json').read_text('utf-8'))
    assert {'windows', 'linux'} <= set(manifest)
    for section in ('windows', 'linux'):
        assert manifest[section], section
        for name, spec in manifest[section].items():
            assert re.fullmatch(r'[0-9a-f]{64}', spec['sha256']), (section, name)
            assert spec['url'].startswith('https://'), (section, name)
            assert sum(k in spec for k in ('extract', 'save_as', 'build')) == 1, (section, name)


def test_main_selects_platform_section(tmp_path, monkeypatch):
    import json
    src = tmp_path / 'tool'
    src.write_bytes(b'x')
    manifest = {'windows': {'a': {'url': src.as_uri(), 'sha256': _sha(src), 'save_as': 'a.exe'}},
                'linux': {'b': {'url': src.as_uri(), 'sha256': _sha(src), 'save_as': 'b'}}}
    mpath = tmp_path / 'm.json'
    mpath.write_text(json.dumps(manifest), 'utf-8')
    monkeypatch.setattr(fetch_mod, 'MANIFEST', str(mpath))
    assert fetch_mod.main(['--platform', 'linux', '--dest', str(tmp_path / 'out')]) == 0
    assert sorted(p.name for p in (tmp_path / 'out').iterdir()) == ['b']
