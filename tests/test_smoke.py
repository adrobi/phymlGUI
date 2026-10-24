"""Smoke test: runs everywhere (CI included), needs no analysis binaries."""
import json
import os
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 1. module imports and i18n integrity
import phymlgui
from phyml_core.pipeline import parse_stats, parse_iqtree_stats
from phyml_ui.tree_viewer import rf_distance, tree_splits
from phyml_ui.themes import resolve, build_qss, role_colors, ACCENTS, system_theme
from phyml_ui.main_window import LogConsole, CONFIG_FILE

loc = json.load(open(os.path.join(ROOT, 'locales.json'), encoding='utf-8'))
assert set(loc) >= {'en', 'ru'}
assert len(loc['en']) == len(loc['ru']), 'locale key sets diverge'
print(f'PASS imports and i18n: {len(loc["en"])} keys in both languages')

# 2. theme resolution and dynamic QSS
theme, accent = resolve('dark', 'blue')
assert theme == 'dark' and accent == ACCENTS['blue']
qss = build_qss(theme, accent)
assert accent in qss and 'QPushButton#btn_run' in qss
assert role_colors(theme, accent)['out'] == '#E6E8EB'
assert system_theme() in ('light', 'dark')
print('PASS themes: resolve, build_qss, role colors')

# 3. stats parsers on synthetic content (no binaries needed)
import io
import tempfile
from Bio import Phylo

tmp = tempfile.mkdtemp()
phy_stats = os.path.join(tmp, 'x_phyml_stats.txt')
open(phy_stats, 'w', encoding='utf-8').write(
    '. Model of nucleotides substitution: \tHKY85\n'
    '. Number of taxa: \t\t8\n'
    '. Log-likelihood: \t\t-1811.15467\n'
    '  - Gamma shape parameter: \t881.743\n'
    '. transition/transversion ratio: \t0.980317\n'
    '. Time used:\t\t\t0h0m0s (0 seconds)\n')
s = parse_stats(phy_stats)
assert s['model'] == 'HKY85' and s['taxa'] == '8' and s['lnL'] == '-1811.15467'
assert s['gamma'] == '881.743' and s['tstv'] == '0.980317'

iq = os.path.join(tmp, 'x.iqtree')
open(iq, 'w', encoding='utf-8').write(
    'Input data: 8 sequences with 600 nucleotide sites\n'
    'Best-fit model according to BIC: JC\n'
    'Log-likelihood of the tree: -1828.7117 (s.e. 50.96)\n'
    'Total wall-clock time used: 0.7434 seconds (0h:0m:0s)\n')
s2 = parse_iqtree_stats(iq)
assert s2['model'] == 'JC' and s2['taxa'] == '8' and s2['lnL'] == '-1828.7117'
print('PASS stats parsers: phyml and iqtree formats')

# 4. RF distance / splits on newick strings
t1 = Phylo.read(io.StringIO('(A,(B,(C,D)));'), 'newick')
t2 = Phylo.read(io.StringIO('(A,(C,(B,D)));'), 'newick')
assert rf_distance(t1, t1) == (0, 0.0)
assert rf_distance(t1, t2) == (1, 1.0)
assert len(tree_splits(t1)) == 1
print('PASS rf distance and splits')

# 5. log classification
app = phymlgui.QApplication([])
log = LogConsole()
assert log._classify('[ERROR] bad') == 'error'
assert log._classify('[+] done') == 'success'
assert log._classify('[*] system line') == 'system'
assert log._classify('. PhyML raw output') == 'out'
log.append('[ERROR] bad')
log.append('raw')
assert '[ERROR] bad' in log.toPlainText() and 'raw' in log.toPlainText()
print('PASS log console roles')

# 6. main window builds offscreen
w = phymlgui.PhyMLApp()
assert w.result_tabs.count() == 4
assert w.presets_list.count() >= 3
assert w.cpu_timer.isActive()
print('PASS main window builds offscreen')

print('ALL SMOKE TESTS PASSED')
