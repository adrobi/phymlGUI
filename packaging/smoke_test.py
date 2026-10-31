"""Smoke-test a built phymlGUI package (Windows zip or Linux AppImage/AppDir).

    python packaging/smoke_test.py --package dist/phymlGUI-2.0.0-windows-x64.zip --version 2.0.0
    python packaging/smoke_test.py --package dist/phymlGUI-2.0.0-x86_64.AppImage --version 2.0.0 --mpi

Checks: --version; a CLI run on unaligned FASTA with the bundled MUSCLE and serial
PhyML; a CLI run with IQ-TREE; optionally an MPI PhyML run (Linux, OpenMPI from
PATH); the window opens offscreen and closes. Settings go to a temporary folder.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests', 'e2e'))


def _launchers(package, work):
    """(cli argv prefix, gui argv prefix) for the package."""
    if package.endswith('.zip'):
        with zipfile.ZipFile(package) as z:
            z.extractall(work)
        app = os.path.join(work, 'phymlGUI')
        return [os.path.join(app, 'phymlgui-cli.exe')], [os.path.join(app, 'phymlgui.exe')]
    if package.endswith('.AppImage'):
        os.chmod(package, 0o755)
        argv = [os.path.abspath(package), '--appimage-extract-and-run']
        return argv, argv
    run = [os.path.join(package, 'AppRun')]   # an AppDir
    return run, run


def _run(argv, env, timeout=600):
    r = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.returncode, r.stdout + r.stderr


def _analysis(cli, env, work, name, overlay):
    from datasets import make_dataset, write_fasta
    names, _, unaligned = make_dataset()
    folder = os.path.join(work, name)
    os.makedirs(folder)
    fasta = os.path.join(folder, 'unaligned.fasta')
    write_fasta(fasta, names, unaligned)
    config = os.path.join(work, f'{name}.json')
    with open(config, 'w', encoding='utf-8') as f:
        json.dump(overlay, f)
    code, out = _run([*cli, '--file', fasta, '--config', config], env)
    trees = [f for f in os.listdir(folder) if f.endswith(('_phyml_tree.txt', '.treefile'))]
    return code == 0 and bool(trees), out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--mpi', action='store_true', help='also run PhyML-MPI (Linux)')
    args = parser.parse_args(argv)
    failures = []
    with tempfile.TemporaryDirectory(prefix='phymlgui_smoke_') as work:
        cli, gui = _launchers(os.path.abspath(args.package), work)
        env = dict(os.environ, PHYMLGUI_DATA_DIR=os.path.join(work, 'data'),
                   QT_QPA_PLATFORM='offscreen')

        code, out = _run([*cli, '--version'], env, timeout=120)
        ok = code == 0 and out.strip().endswith(f'phymlGUI {args.version}')
        print(f'{"OK  " if ok else "FAIL"} --version: {out.strip()!r}')
        failures += [] if ok else ['--version']

        base = {'datatype': 'nt', 'model': 'HKY85', 'mpi_np': '2', 'use_mpi': False}
        checks = [
            ('phyml', dict(base, engine='phyml', support_method='-4')),
            ('iqtree', dict(base, engine='iqtree', model='MFP', support_method='-4')),
        ]
        if args.mpi:
            checks.append(('phyml-mpi', dict(base, engine='phyml', use_mpi=True,
                                             support_method='bootstrap', bootstrap_replicates='4')))
        for name, overlay in checks:
            ok, out = _analysis(cli, env, work, name, overlay)
            print(f'{"OK  " if ok else "FAIL"} {name} run')
            if not ok:
                failures.append(name)
                print(out[-2000:])

        code, out = _run([*gui, '--smoke-gui'], env, timeout=120)
        print(f'{"OK  " if code == 0 else "FAIL"} window opens and closes')
        if code != 0:
            failures.append('gui')
            print(out[-2000:])
    print('SMOKE TEST ' + ('PASSED' if not failures else f'FAILED: {", ".join(failures)}'))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
