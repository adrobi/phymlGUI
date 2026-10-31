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

NOTES = """phymlGUI {version}

Downloads:
- `phymlGUI-{version}-windows-x64.zip` - unpack and start `phymlgui.exe`
  (command line: `phymlgui-cli.exe`). PhyML needs Microsoft MPI
  (also for serial runs: the bundled PhyML is an MPI build).
- `phymlGUI-{version}-x86_64.AppImage` - `chmod +x` and run; without FUSE use
  `--appimage-extract-and-run`. MPI mode needs OpenMPI (`sudo apt install openmpi-bin`).
- `SHA256SUMS` - checksums of the files above.
- `raxml-ng-2.0.3-source+patch.tar.gz` - RAxML-NG sources and the patch used for the
  Windows build (AGPL-3.0).

Bundled programs:
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


def release_notes(version, manifest):
    lines = []
    for section, label in (('windows', 'Windows'), ('linux', 'Linux')):
        for name, spec in manifest[section].items():
            lines.append(f'- {label}: {name} {spec["version"]}')
    return NOTES.format(version=version, tools='\n'.join(lines))


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
