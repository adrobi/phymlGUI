"""Download the pinned third-party binaries (IQ-TREE, MUSCLE) into a folder.

Every download is verified against the SHA256 in packaging/third_party.json
before anything is written to the destination.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, 'packaging', 'third_party.json')


def _download(url, target):
    sha = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as resp, open(target, 'wb') as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            sha.update(chunk)
            out.write(chunk)
    return sha.hexdigest()


def fetch(name, spec, dest):
    """Download spec['url'], check SHA256, put the files into dest; return their paths."""
    with tempfile.TemporaryDirectory(prefix='phymlgui_fetch_') as tmp:
        archive = os.path.join(tmp, 'download')
        actual = _download(spec['url'], archive)
        expected = spec['sha256'].lower()
        if actual != expected:
            raise ValueError(f'{name}: SHA256 mismatch: expected {expected}, got {actual}')
        os.makedirs(dest, exist_ok=True)
        written = []
        if 'extract' in spec:
            with zipfile.ZipFile(archive) as z:
                for member, out_name in spec['extract'].items():
                    target = os.path.join(dest, out_name)
                    with z.open(member) as src, open(target, 'wb') as out:
                        shutil.copyfileobj(src, out)
                    written.append(target)
        else:
            target = os.path.join(dest, spec['save_as'])
            shutil.copyfile(archive, target)
            written.append(target)
        return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', default='bin')
    parser.add_argument('--only', action='append', choices=None,
                        help='fetch only this tool (repeatable)')
    args = parser.parse_args(argv)
    with open(MANIFEST, encoding='utf-8') as f:
        manifest = json.load(f)
    names = args.only or list(manifest)
    unknown = [n for n in names if n not in manifest]
    if unknown:
        print(f'unknown tool(s): {", ".join(unknown)}', file=sys.stderr)
        return 2
    for name in names:
        try:
            paths = fetch(name, manifest[name], args.dest)
        except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
            print(f'{name}: {exc}', file=sys.stderr)
            return 1
        for p in paths:
            print(f'{name}: {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
