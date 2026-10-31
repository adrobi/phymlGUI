"""Screenshots for the README: real runs of the bundled tools in a throwaway data folder.

    python scripts/make_screenshots.py --fasta testrun/cytb_mammals.fasta --out docs/screenshots

The inputs are copied to testrun/screenshots (the path shows in the window).
Writes, for English and Russian (suffix _ru): main.png (PhyML with MPI bootstrap,
light theme), dark.png (the same tree, slanted layout, dark theme) and iqtree.png
(IQ-TREE with ModelFinder, statistics tab), all rooted on --outgroup. The user's settings and
history are never touched: PHYMLGUI_DATA_DIR points to a temporary folder.
Tools come from --bin (default: build-bin, then bin).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW_SIZE = (1500, 920)


def _tool(bins, name):
    for folder in bins:
        path = os.path.join(ROOT, folder, name)
        if os.path.isfile(path):
            return path
    sys.exit(f'{name} not found in {bins}')


def _config(bins, theme, engine):
    mpiexec = shutil.which('mpiexec') or r'C:\Program Files\Microsoft MPI\Bin\mpiexec.exe'
    return {
        'engine': engine,
        'phyml_path': _tool(bins, 'phyml-mpi.exe'),
        'iqtree_path': _tool(bins, 'iqtree2.exe'),
        'muscle_path': _tool(bins, 'muscle.exe'),
        'mpirun_path': mpiexec,
        'use_mpi': engine == 'phyml',
        'mpi_np': '4',
        'support_method': 'bootstrap',
        'bootstrap_replicates': '100',
        'model': 'HKY85' if engine == 'phyml' else 'MFP',
        'theme': theme,
        'accent': 'green',
    }


def shoot(lang, theme, engine, fasta, bins, out, name, layout='rect', tab=0, outgroup=None):
    """One screenshot in a fresh process: the language is fixed at import time."""
    with tempfile.TemporaryDirectory(prefix='phymlgui_shots_') as tmp:
        data = os.path.join(tmp, 'data')
        os.makedirs(data)
        # the input path shows in the window and the log: keep the user's home out of it
        work = os.path.join(ROOT, 'testrun', 'screenshots')
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        with open(os.path.join(data, 'phyml_config.json'), 'w', encoding='utf-8') as f:
            json.dump(_config(bins, theme, engine), f)
        target = os.path.join(work, os.path.basename(fasta))
        shutil.copy(fasta, target)
        job = dict(lang=lang, fasta=target, png=os.path.join(out, name), layout=layout, tab=tab,
                   outgroup=outgroup)
        env = dict(os.environ, PHYMLGUI_DATA_DIR=data, PHYMLGUI_SHOT=json.dumps(job))
        subprocess.run([sys.executable, os.path.abspath(__file__), '--child'], env=env, check=True)


def child():
    job = json.loads(os.environ['PHYMLGUI_SHOT'])
    sys.path.insert(0, ROOT)
    from phyml_core import i18n
    i18n.LANG = job['lang']
    from PySide6.QtWidgets import QApplication
    from phyml_ui.main_window import PhyMLApp
    app = QApplication(sys.argv)
    window = PhyMLApp()
    window.resize(*WINDOW_SIZE)
    window.move(-WINDOW_SIZE[0] - 200, 0)   # off-screen: nothing flashes on the desktop
    window.show()
    window.fasta_path_input.setText(job['fasta'])
    window.btn_run.click()
    deadline = time.time() + 600
    while not window.btn_run.isEnabled():
        app.processEvents()
        time.sleep(0.05)
        if time.time() > deadline:
            sys.exit('the run did not finish')
    combo = window.tree_view.layout_combo
    combo.setCurrentIndex(combo.findData(job['layout']))
    if job['outgroup']:
        combo = window.tree_view.outgroup_combo
        combo.setCurrentIndex(combo.findData(job['outgroup']))
    window.result_tabs.setCurrentIndex(job['tab'])
    for _ in range(40):
        app.processEvents()
        time.sleep(0.025)
    window.grab().save(job['png'])
    print('wrote', job['png'])
    window.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fasta', default=os.path.join(ROOT, 'testrun', 'cytb_mammals.fasta'))
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots'))
    parser.add_argument('--bin', action='append', help='folder with the tools (repeatable)')
    parser.add_argument('--outgroup', default='Mus_musculus', help='taxon to root the trees on')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        child()
        return 0
    bins = args.bin or ['build-bin', 'bin']
    os.makedirs(args.out, exist_ok=True)
    fasta = os.path.abspath(args.fasta)
    for lang, suffix in (('en', ''), ('ru', '_ru')):
        common = dict(fasta=fasta, bins=bins, out=args.out, outgroup=args.outgroup)
        shoot(lang, 'light', 'phyml', name=f'main{suffix}.png', **common)
        shoot(lang, 'dark', 'phyml', name=f'dark{suffix}.png', layout='slanted', **common)
        shoot(lang, 'light', 'iqtree', name=f'iqtree{suffix}.png', tab=1, **common)
    return 0


if __name__ == '__main__':
    sys.exit(main())
