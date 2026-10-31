"""Check that our Windows RAxML-NG build matches the official Linux binary.

The two binaries run on different machines in CI, so this has two steps:

    python packaging/raxml_parity.py run --exe raxml-ng.exe --out parity-windows
    python packaging/raxml_parity.py run --exe ./raxml-ng   --out parity-linux
    python packaging/raxml_parity.py compare parity-windows parity-linux

`run` builds a fixed synthetic alignment and runs, with --seed 42: an ML search,
50 bootstrap replicates, and a likelihood evaluation of a fixed tree under JC.
`compare` applies the rules from the RAxML-NG Windows spike: identical best tree
(RF 0) with |ΔlnL| < 1e-3, identical bootstrap replicates, and the same
fixed-tree likelihood to 6 decimals.
"""
import argparse
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LNL_TOLERANCE = 1e-3
FIXED_TREE = ('(((A1_testsp:0.02,A2_testsp:0.02):0.02,(A3_testsp:0.02,A4_testsp:0.02):0.02):0.15,'
              '((B1_testsp:0.02,B2_testsp:0.02):0.02,(B3_testsp:0.02,B4_testsp:0.02):0.02):0.15);')


def _read(folder, name):
    with open(os.path.join(folder, name), encoding='utf-8', errors='replace') as f:
        return f.read().replace('\r\n', '\n')


def _lnl(text):
    m = re.search(r'Final LogLikelihood:\s*(-?[\d.]+)', text)
    if not m:
        raise ValueError('no "Final LogLikelihood" line')
    return float(m.group(1))


def _splits(newick):
    from Bio import Phylo
    tree = Phylo.read(io.StringIO(newick), 'newick')
    names = {t.name for t in tree.get_terminals()}
    anchor = min(names)
    out = set()
    for clade in tree.get_nonterminals():
        side = frozenset(t.name for t in clade.get_terminals())
        side = side if anchor not in side else frozenset(names - side)
        if 1 < len(side) < len(names) - 1:
            out.add(side)
    return out


def compare(win_dir, lin_dir):
    """Differences between the two output folders; an empty list means they match."""
    problems = []

    def check(name, test):
        try:
            message = test(_read(win_dir, name), _read(lin_dir, name))
        except (OSError, ValueError) as e:
            message = str(e)
        if message:
            problems.append(f'{name}: {message}')

    def best_tree(w, l):
        if _splits(w.strip()) != _splits(l.strip()):
            return 'best trees differ (RF > 0)'

    def search_lnl(w, l):
        diff = abs(_lnl(w) - _lnl(l))
        if diff >= LNL_TOLERANCE:
            return f'|ΔlnL| = {diff:.2e} >= {LNL_TOLERANCE:g}'

    def bootstraps(w, l):
        win_trees = [t for t in w.splitlines() if t.strip()]
        lin_trees = [t for t in l.splitlines() if t.strip()]
        if len(win_trees) != len(lin_trees):
            return f'{len(win_trees)} vs {len(lin_trees)} replicates'
        differing = sum(_splits(a) != _splits(b) for a, b in zip(win_trees, lin_trees))
        if differing:
            return f'{differing} of {len(win_trees)} replicate trees differ'

    def fixed(w, l):
        if round(_lnl(w), 6) != round(_lnl(l), 6):
            return f'fixed-tree lnL {_lnl(w)} vs {_lnl(l)}'

    check('search.raxml.bestTree', best_tree)
    check('search.raxml.log', search_lnl)
    check('boot.raxml.bootstraps', bootstraps)
    check('eval.raxml.log', fixed)
    return problems


def run(exe, out):
    """Run the parity analyses with exe into out (inputs are generated here)."""
    sys.path.insert(0, os.path.join(ROOT, 'tests', 'e2e'))
    sys.path.insert(0, ROOT)
    from dataset_gen import make_dataset, write_fasta
    from phyml_core import alignment
    os.makedirs(out, exist_ok=True)
    names, aligned, _ = make_dataset()
    fasta = os.path.join(out, 'parity.fasta')
    write_fasta(fasta, names, aligned)
    phy = os.path.join(out, 'parity.phy')
    alignment.write_phylip(alignment.read_fasta(fasta), phy)
    with open(os.path.join(out, 'fixed.tree'), 'w') as f:
        f.write(FIXED_TREE + '\n')
    # the same SIMD kernel on both runners: RAxML-NG otherwise picks one per CPU
    common = ['--msa', 'parity.phy', '--seed', '42', '--redo', '--simd', 'avx2']
    runs = [
        ['--search', *common, '--model', 'GTR+G', '--threads', '1', '--prefix', 'search'],
        ['--bootstrap', *common, '--model', 'GTR+G', '--threads', '2', '--bs-trees', '50',
         '--prefix', 'boot'],
        ['--evaluate', *common, '--model', 'JC', '--tree', 'fixed.tree', '--opt-model', 'off',
         '--opt-branches', 'off', '--threads', '1', '--prefix', 'eval'],
    ]
    for args in runs:
        subprocess.run([os.path.abspath(exe), *args], cwd=out, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run')
    r.add_argument('--exe', required=True)
    r.add_argument('--out', required=True)
    c = sub.add_parser('compare')
    c.add_argument('win_dir')
    c.add_argument('lin_dir')
    args = parser.parse_args(argv)
    if args.command == 'run':
        run(args.exe, args.out)
        return 0
    problems = compare(args.win_dir, args.lin_dir)
    for p in problems:
        print('DIFF', p)
    print('RAxML-NG parity: ' + ('OK' if not problems else f'{len(problems)} difference(s)'))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
