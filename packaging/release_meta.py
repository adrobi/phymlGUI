"""Release metadata for the GitHub workflow: version, SHA256SUMS, notes, AGPL sources.

    python packaging/release_meta.py version "$GITHUB_REF"
    python packaging/release_meta.py sha256sums out/SHA256SUMS out/*.zip out/*.AppImage
    python packaging/release_meta.py notes 2.0.0 out/notes.md
    python packaging/release_meta.py raxml-source <source.zip> <patch> <out.tar.gz>
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, 'packaging', 'third_party.json')
DEV_VERSION = '0.0.0-dev'

_spec = importlib.util.spec_from_file_location('package', os.path.join(ROOT, 'packaging', 'package.py'))
_package = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_package)

NOTES_DIR = os.path.join(ROOT, 'packaging', 'release_notes')
TOOL_NAMES = {'phyml': 'PhyML', 'iqtree': 'IQ-TREE', 'muscle': 'MUSCLE', 'raxml': 'RAxML-NG'}

DOWNLOAD_EN = """### Download and requirements

- **Windows 10/11, 64-bit:** `phymlGUI-{version}-windows-x64.zip`. Unpack the whole archive and run `phymlgui.exe` (`phymlgui-cli.exe` for the command line). PhyML needs [Microsoft MPI](https://github.com/microsoft/Microsoft-MPI/releases) (`msmpisetup.exe`), also for serial runs: the bundled PhyML is an MPI build.
- **Linux x86_64:** `phymlGUI-{version}-x86_64.AppImage`. Run `chmod +x` and start it; without FUSE add `--appimage-extract-and-run`. Needs glibc 2.35 or newer (Ubuntu 22.04+). MPI mode needs OpenMPI: `sudo apt install openmpi-bin`.
- `SHA256SUMS`: checksums of the files, `sha256sum -c SHA256SUMS`.
- `raxml-ng-2.0.3-source+patch.tar.gz`: RAxML-NG sources and the patch of the Windows build (AGPL-3.0).

Python is not required.

### Bundled programs

| Program | Windows | Linux |
| --- | --- | --- |
{tools}
"""

DOWNLOAD_RU = """### Скачать и требования

- **Windows 10/11, 64 бит:** `phymlGUI-{version}-windows-x64.zip`. Распакуйте архив целиком и запустите `phymlgui.exe` (`phymlgui-cli.exe` — для командной строки). PhyML требует [Microsoft MPI](https://github.com/microsoft/Microsoft-MPI/releases) (`msmpisetup.exe`), в том числе для последовательного режима: встроенный PhyML собран с MPI.
- **Linux x86_64:** `phymlGUI-{version}-x86_64.AppImage`. Выполните `chmod +x` и запустите; без FUSE добавьте `--appimage-extract-and-run`. Нужен glibc 2.35 или новее (Ubuntu 22.04+). Для MPI-режима нужен OpenMPI: `sudo apt install openmpi-bin`.
- `SHA256SUMS` — контрольные суммы файлов, `sha256sum -c SHA256SUMS`.
- `raxml-ng-2.0.3-source+patch.tar.gz` — исходники RAxML-NG и патч сборки для Windows (AGPL-3.0).

Python не нужен.

### Программы в комплекте

| Программа | Windows | Linux |
| --- | --- | --- |
{tools}
"""


def version_for_ref(ref):
    """'refs/tags/vX.Y.Z[-s]' -> 'X.Y.Z[-s]' (ValueError for any other tag);
    a branch ref (manual run) -> '0.0.0-dev'."""
    if ref.startswith('refs/tags/'):
        return _package.version_from_tag(ref[len('refs/tags/'):])
    return DEV_VERSION


def write_sha256sums(files, out):
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        for path in files:
            with open(path, 'rb') as src:
                digest = hashlib.sha256(src.read()).hexdigest()
            f.write(f'{digest}  {os.path.basename(path)}\n')


def _highlights(version, suffix, notes_dir):
    """packaging/release_notes/<X.Y.Z><suffix>; a pre-release uses its release's file."""
    path = os.path.join(notes_dir, version.split('-')[0] + suffix)
    if not os.path.isfile(path):
        return ''
    with open(path, encoding='utf-8') as f:
        return f.read().strip() + '\n\n'


def release_notes(version, manifest, notes_dir=NOTES_DIR):
    """English, then Russian: the version's highlights, downloads and bundled programs."""
    rows = []
    for name, label in TOOL_NAMES.items():
        # '2.0.3 (native build, ...)' -> '2.0.3': the build notes are in the text above
        cells = [manifest[section].get(name, {}).get('version', '—').split(' (')[0]
                 for section in ('windows', 'linux')]
        rows.append(f'| {label} | {cells[0]} | {cells[1]} |')
    tools = '\n'.join(rows)
    english = _highlights(version, '.md', notes_dir) + DOWNLOAD_EN.format(version=version, tools=tools)
    russian = _highlights(version, '.ru.md', notes_dir) + DOWNLOAD_RU.format(version=version, tools=tools)
    return f'# phymlGUI {version}\n\n{english}\n---\n\n{russian}'


def raxml_source_bundle(source_zip, patch, out):
    """A tar.gz with the official RAxML-NG source zip and our Windows patch."""
    folder = 'raxml-ng-2.0.3-source+patch'
    with tarfile.open(out, 'w:gz') as t:
        t.add(source_zip, arcname=f'{folder}/{os.path.basename(source_zip)}')
        t.add(patch, arcname=f'{folder}/raxml-ng-2.0.3-windows.patch')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('version').add_argument('ref')
    s = sub.add_parser('sha256sums')
    s.add_argument('out')
    s.add_argument('files', nargs='+')
    n = sub.add_parser('notes')
    n.add_argument('version')
    n.add_argument('out')
    r = sub.add_parser('raxml-source')
    r.add_argument('source_zip')
    r.add_argument('patch')
    r.add_argument('out')
    args = parser.parse_args(argv)
    if args.command == 'version':
        try:
            print(version_for_ref(args.ref))
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
    elif args.command == 'sha256sums':
        write_sha256sums(args.files, args.out)
    elif args.command == 'notes':
        with open(MANIFEST, encoding='utf-8') as f:
            manifest = json.load(f)
        with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(release_notes(args.version, manifest))
    else:
        raxml_source_bundle(args.source_zip, args.patch, args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
