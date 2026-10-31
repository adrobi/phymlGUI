"""Release metadata helpers (packaging/release_meta.py)."""
import hashlib
import importlib.util
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('release_meta', ROOT / 'packaging' / 'release_meta.py')
meta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(meta)


@pytest.mark.parametrize('ref, version', [('refs/tags/v2.0.0', '2.0.0'),
                                          ('refs/tags/v2.0.0-rc1', '2.0.0-rc1'),
                                          ('refs/heads/release', '0.0.0-dev')])
def test_release_version_from_ref(ref, version):
    assert meta.version_for_ref(ref) == version


@pytest.mark.parametrize('ref', ['refs/tags/release-1', 'refs/tags/v2', 'refs/tags/2.0.0'])
def test_release_tag_validation(ref):
    with pytest.raises(ValueError):
        meta.version_for_ref(ref)


def test_sha256sums_format(tmp_path):
    a, b = tmp_path / 'a.zip', tmp_path / 'b.AppImage'
    a.write_bytes(b'one')
    b.write_bytes(b'two')
    out = tmp_path / 'SHA256SUMS'
    meta.write_sha256sums([str(a), str(b)], str(out))
    lines = out.read_text('utf-8').splitlines()
    assert lines == [f'{hashlib.sha256(b"one").hexdigest()}  a.zip',
                     f'{hashlib.sha256(b"two").hexdigest()}  b.AppImage']


def test_release_notes_lists_tools():
    manifest = json.loads((ROOT / 'packaging' / 'third_party.json').read_text('utf-8'))
    notes = meta.release_notes('2.0.0', manifest)
    assert 'phymlGUI 2.0.0' in notes
    for section in ('windows', 'linux'):
        for name, spec in manifest[section].items():
            assert f" {spec['version'].split(' (')[0]} |" in notes, (section, name)
    assert 'Microsoft MPI' in notes and 'OpenMPI' in notes and 'SHA256SUMS' in notes


def test_raxml_source_bundle(tmp_path):
    src = tmp_path / 'raxml-ng_v2.0.3_source.zip'
    with zipfile.ZipFile(src, 'w') as z:
        z.writestr('CMakeLists.txt', 'project(raxml)')
    patch = tmp_path / 'windows.patch'
    patch.write_text('--- a\n+++ b\n')
    out = tmp_path / 'raxml-ng-2.0.3-source+patch.tar.gz'
    meta.raxml_source_bundle(str(src), str(patch), str(out))
    with tarfile.open(out) as t:
        assert sorted(t.getnames()) == ['raxml-ng-2.0.3-source+patch/raxml-ng-2.0.3-windows.patch',
                                        'raxml-ng-2.0.3-source+patch/raxml-ng_v2.0.3_source.zip']


def test_release_notes_are_bilingual():
    manifest = json.loads((ROOT / 'packaging' / 'third_party.json').read_text('utf-8'))
    notes = meta.release_notes('2.0.0', manifest)
    for text in ('Download', 'Скачать', 'Microsoft MPI', 'OpenMPI', 'SHA256SUMS'):
        assert text in notes, text
    assert notes.index('Download') < notes.index('Скачать')


def test_release_notes_hold_the_version_highlights_in_both_languages(tmp_path):
    manifest = json.loads((ROOT / 'packaging' / 'third_party.json').read_text('utf-8'))
    (tmp_path / '2.0.0.md').write_text('## Highlights\n\nNew window.\n', 'utf-8')
    (tmp_path / '2.0.0.ru.md').write_text('## Главное\n\nНовое окно.\n', 'utf-8')
    for version in ('2.0.0', '2.0.0-rc1'):   # a release candidate uses the notes of its release
        notes = meta.release_notes(version, manifest, notes_dir=str(tmp_path))
        assert notes.startswith(f'# phymlGUI {version}\n\n## Highlights\n\nNew window.\n'), version
        order = [notes.index(t) for t in ('Highlights', 'Download', 'Главное', 'Скачать')]
        assert order == sorted(order), version
    plain = meta.release_notes('2.1.0', manifest, notes_dir=str(tmp_path))
    assert 'Highlights' not in plain and 'Главное' not in plain and 'Скачать' in plain
