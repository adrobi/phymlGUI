"""Build phymlGUI release packages: a Windows zip and a Linux AppDir/AppImage.

    python packaging/package.py windows --version 2.0.0 --bin bin --out dist
    python packaging/package.py linux   --version 2.0.0 --bin bin --out dist --appimagetool appimagetool

The application sources are copied to a temporary folder, __version__ is stamped
there (the repository is never modified), PyInstaller builds an onedir bundle, and
the analysis programs from --bin plus packaging/licenses/ are added.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_SOURCES = ('phymlgui.py', 'phyml_core', 'phyml_ui', 'locales.json', 'icon.png', 'icon.ico')
TAG_RE = re.compile(r'v(\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.]*)?)')

WINDOWS_README = """phymlGUI {version}

Start phymlgui.exe. Command line: phymlgui-cli.exe --file data.fasta
(or --batch folder, --version).

The analysis programs are in bin/; their licenses are in licenses/.
PhyML needs Microsoft MPI (msmpisetup.exe from Microsoft), also for serial runs:
the bundled PhyML is an MPI build.
Settings are kept next to phymlgui.exe, or in %APPDATA%\\phymlGUI if this
folder is read-only.
"""


def version_from_tag(tag):
    """'v2.0.0' -> '2.0.0', 'v2.0.0-rc1' -> '2.0.0-rc1'; anything else -> ValueError."""
    m = TAG_RE.fullmatch(tag)
    if not m:
        raise ValueError(f'not a release tag (vX.Y.Z[-suffix]): {tag!r}')
    return m.group(1)


def stamp_version(version, init_path):
    """Rewrite __version__ in phyml_core/__init__.py at init_path (a build copy)."""
    with open(init_path, encoding='utf-8') as f:
        text = f.read()
    text, n = re.subn(r'__version__\s*=\s*["\'][^"\']*["\']', f'__version__ = "{version}"', text)
    if n != 1:
        raise ValueError(f'__version__ not found in {init_path}')
    with open(init_path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def _pyinstaller_bundle(version, work):
    """Copy the sources into work/src, stamp the version, run PyInstaller -> bundle dir."""
    src = os.path.join(work, 'src')
    os.makedirs(src)
    for name in APP_SOURCES:
        path = os.path.join(ROOT, name)
        if os.path.isdir(path):
            shutil.copytree(path, os.path.join(src, name),
                            ignore=shutil.ignore_patterns('__pycache__'))
        elif os.path.isfile(path):
            shutil.copy2(path, src)
    os.makedirs(os.path.join(src, 'packaging'))
    shutil.copy2(os.path.join(ROOT, 'packaging', 'phymlgui.spec'), os.path.join(src, 'packaging'))
    stamp_version(version, os.path.join(src, 'phyml_core', '__init__.py'))
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', os.path.join(work, 'dist'),
                    '--workpath', os.path.join(work, 'build'),
                    os.path.join(src, 'packaging', 'phymlgui.spec')], check=True)
    return os.path.join(work, 'dist', 'phymlgui')


def _copy_tools(bin_dir, target):
    os.makedirs(target, exist_ok=True)
    for name in sorted(os.listdir(bin_dir)):
        shutil.copy2(os.path.join(bin_dir, name), os.path.join(target, name))


def build_windows(version, bin_dir, out_dir):
    """phymlGUI-<version>-windows-x64.zip with phymlGUI/{exe, _internal, bin, licenses}."""
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='phymlgui_pkg_') as work:
        bundle = _pyinstaller_bundle(version, work)
        app = os.path.join(work, 'phymlGUI')
        shutil.move(bundle, app)
        _copy_tools(bin_dir, os.path.join(app, 'bin'))
        shutil.copytree(os.path.join(ROOT, 'packaging', 'licenses'), os.path.join(app, 'licenses'))
        with open(os.path.join(app, 'README.txt'), 'w', encoding='utf-8', newline='\r\n') as f:
            f.write(WINDOWS_README.format(version=version))
        out = os.path.join(out_dir, f'phymlGUI-{version}-windows-x64.zip')
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for folder, _, files in os.walk(app):
                for name in files:
                    path = os.path.join(folder, name)
                    z.write(path, os.path.relpath(path, work))
        return out


def build_appdir(version, bin_dir, out_dir):
    """An AppDir in out_dir: AppRun, .desktop, icon, usr/bin/{phymlgui, _internal, bin/}."""
    appdir = os.path.join(out_dir, 'phymlGUI.AppDir')
    shutil.rmtree(appdir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='phymlgui_pkg_') as work:
        bundle = _pyinstaller_bundle(version, work)
        usr_bin = os.path.join(appdir, 'usr', 'bin')
        shutil.copytree(bundle, usr_bin)
    _copy_tools(bin_dir, os.path.join(usr_bin, 'bin'))
    for name in os.listdir(os.path.join(usr_bin, 'bin')):
        os.chmod(os.path.join(usr_bin, 'bin', name), 0o755)
    shutil.copytree(os.path.join(ROOT, 'packaging', 'licenses'),
                    os.path.join(appdir, 'usr', 'share', 'licenses', 'phymlgui'))
    apprun = os.path.join(appdir, 'AppRun')
    shutil.copy2(os.path.join(ROOT, 'packaging', 'appimage', 'AppRun'), apprun)
    os.chmod(apprun, 0o755)
    shutil.copy2(os.path.join(ROOT, 'packaging', 'appimage', 'phymlgui.desktop'), appdir)
    shutil.copy2(os.path.join(ROOT, 'icon.png'), os.path.join(appdir, 'phymlgui.png'))
    return appdir


def build_appimage(version, bin_dir, out_dir, appimagetool, runtime=None):
    """phymlGUI-<version>-x86_64.AppImage built by the pinned appimagetool (and runtime)."""
    if not appimagetool:
        raise ValueError('--appimagetool is required for linux')
    appdir = build_appdir(version, bin_dir, out_dir)
    out = os.path.join(out_dir, f'phymlGUI-{version}-x86_64.AppImage')
    command = [appimagetool, '--appimage-extract-and-run']   # no FUSE needed on CI
    if runtime:
        command += ['--runtime-file', runtime]
    subprocess.run([*command, appdir, out], check=True, env=dict(os.environ, ARCH='x86_64'))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=['windows', 'linux'])
    parser.add_argument('--version', required=True)
    parser.add_argument('--bin', required=True, help='folder with the analysis programs')
    parser.add_argument('--out', default='dist')
    parser.add_argument('--appimagetool', help='path to appimagetool (linux)')
    parser.add_argument('--runtime', help='path to the pinned AppImage runtime (linux)')
    args = parser.parse_args(argv)
    if args.platform == 'windows':
        out = build_windows(args.version, args.bin, args.out)
    else:
        out = build_appimage(args.version, args.bin, args.out, args.appimagetool, args.runtime)
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
