"""Download (or build) the pinned third-party programs into a folder.

packaging/third_party.json has one section per platform ("windows", "linux",
and "build_tools" for packaging helpers). Every download is verified against
its SHA256 before anything is written to the destination. An entry then
either extracts listed members of a zip/tar.gz ("extract"), saves the file
under a new name ("save_as"), or runs a build command ("build": argv that
receives the downloaded archive and the destination) and checks "outputs".
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, 'packaging', 'third_party.json')


def default_platform():
    return 'windows' if os.name == 'nt' else 'linux'


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


def _extract(archive, members, dest):
    written = []
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for member, out_name in members.items():
                target = os.path.join(dest, out_name)
                with z.open(member) as src, open(target, 'wb') as out:
                    shutil.copyfileobj(src, out)
                written.append(target)
    else:
        with tarfile.open(archive) as t:
            for member, out_name in members.items():
                src = t.extractfile(member)
                if src is None:
                    raise KeyError(member)
                target = os.path.join(dest, out_name)
                with src, open(target, 'wb') as out:
                    shutil.copyfileobj(src, out)
                written.append(target)
    return written


def _build(spec, archive, dest):
    subprocess.run([*spec['build'], archive, dest], check=True, cwd=ROOT)
    written = [os.path.join(dest, name) for name in spec.get('outputs', [])]
    missing = [p for p in written if not os.path.isfile(p)]
    if missing:
        raise ValueError(f'build did not produce: {", ".join(missing)}')
    return written


def fetch(name, spec, dest):
    """Download spec['url'], check SHA256, put the files into dest; return their paths."""
    with tempfile.TemporaryDirectory(prefix='phymlgui_fetch_') as tmp:
        archive = os.path.join(tmp, 'download')
        actual = _download(spec['url'], archive)
        expected = spec['sha256'].lower()
        if actual != expected:
            raise ValueError(f'{name}: SHA256 mismatch: expected {expected}, got {actual}')
        os.makedirs(dest, exist_ok=True)
        if 'build' in spec:
            written = _build(spec, archive, os.path.abspath(dest))
        elif 'extract' in spec:
            written = _extract(archive, spec['extract'], dest)
        else:
            target = os.path.join(dest, spec['save_as'])
            shutil.copyfile(archive, target)
            written = [target]
        if spec.get('mode') and os.name != 'nt':
            for path in written:
                os.chmod(path, int(spec['mode'], 8))
        return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', default=default_platform(),
                        help='manifest section: windows, linux or build_tools')
    parser.add_argument('--dest', default='bin')
    parser.add_argument('--only', action='append',
                        help='fetch only this tool (repeatable, comma lists allowed)')
    args = parser.parse_args(argv)
    with open(MANIFEST, encoding='utf-8') as f:
        manifest = json.load(f)
    section = manifest.get(args.platform)
    if section is None:
        print(f'unknown platform section: {args.platform}', file=sys.stderr)
        return 2
    names = [n for item in (args.only or []) for n in item.split(',') if n] or list(section)
    unknown = [n for n in names if n not in section]
    if unknown:
        print(f'unknown tool(s): {", ".join(unknown)}', file=sys.stderr)
        return 2
    for name in names:
        try:
            paths = fetch(name, section[name], args.dest)
        except (ValueError, OSError, KeyError, zipfile.BadZipFile, tarfile.TarError,
                subprocess.CalledProcessError) as exc:
            print(f'{name}: {exc}', file=sys.stderr)
            return 1
        for p in paths:
            print(f'{name}: {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
