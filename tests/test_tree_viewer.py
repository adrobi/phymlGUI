"""Tests for the stage-2 tree viewer: layouts, collapse, outgroup, consensus, RF."""
import io
import os
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import phymlgui
from phyml_ui.tree_viewer import TreeViewerWidget, rf_distance
from Bio import Phylo

# 1. RF distance: identical -> 0, swapped quartet -> max
t1 = Phylo.read(io.StringIO('(A,(B,(C,D)));'), 'newick')
t2 = Phylo.read(io.StringIO('(A,(C,(B,D)));'), 'newick')
assert rf_distance(t1, t1) == (0, 0.0)
raw, norm = rf_distance(t1, t2)
assert raw == 1 and norm == 1.0, (raw, norm)
print('PASS rf: identical=0, quartet swap=1 (100%)')

app = phymlgui.QApplication([])
if not os.path.isdir('testrun') or not any(
        os.path.exists(os.path.join('testrun', d, f))
        for d in os.listdir('testrun') if os.path.isdir(os.path.join('testrun', d))
        for f in os.listdir(os.path.join('testrun', d)) if f.endswith('_phyml_tree.txt')):
    print('SKIP: no rendered trees available; run tests/run_tests.py first')
    sys.exit(0)

w = TreeViewerWidget()

# real tree with supports from the e2e runs
tree_file = None
for d in ('t9_real_ncbi', 't2_unaligned_mpi_boot'):
    p = os.path.join('testrun', d)
    if os.path.isdir(p):
        for f in os.listdir(p):
            if f.endswith('_phyml_tree.txt'):
                tree_file = os.path.join(p, f)
                break
    if tree_file:
        break
assert tree_file, 'no e2e tree available; run run_tests.py first'

w.load_tree(tree_file)
assert len(w._leaf_order) == 8

# 2. all three layouts render without errors
for layout in ('rect', 'slanted', 'circle'):
    w.set_layout(layout)
    assert w.layout == layout
print('PASS layouts: rect / slanted / circle render')

# 2b. manual distance grid is actually drawn (ax.grid dies with axis_off)
w.set_layout('rect')
from matplotlib.lines import Line2D
grid_on = sum(1 for l in w.ax.lines if isinstance(l, Line2D))
w.chk_grid.setChecked(False)
grid_off = sum(1 for l in w.ax.lines if isinstance(l, Line2D))
w.chk_grid.setChecked(True)
assert grid_on >= 3 and grid_off < grid_on, (grid_on, grid_off)
print(f'PASS grid: {grid_on} distance gridlines drawn, toggleable')

# 2c. theme-aware colors recolor the render
w.set_colors('#E6E8EB', '#37C894', '#26282D')
assert w._bg == '#26282D' and w.figure.patch.get_facecolor()[:3] != (1, 1, 1)
w.set_colors('#424242', '#1E9E6A', '#FFFFFF')
print('PASS theme colors: branches/background follow the app theme')

# 3. support threshold + grid toggles do not break rendering
w.threshold_slider.setValue(70)
assert w.threshold == 70
w.chk_grid.setChecked(False)
w.chk_supports.setChecked(False)
w.chk_supports.setChecked(True)
print('PASS options: threshold, grid, supports')

# 4. collapse: first real internal clade folds into one display leaf
src = Phylo.read(tree_file, 'newick')
candidates = [cl for cl in src.get_nonterminals()
              if 2 <= len(cl.get_terminals()) < len(src.get_terminals())]
assert candidates, 'no internal clades to collapse'
target = frozenset(t.name for t in candidates[0].get_terminals())
w.set_layout('rect')
before = len(w._leaf_order)
w.collapse_clade(target)
assert len(w._leaf_order) == before - len(target) + 1, (before, len(w._leaf_order))
w.collapse_clade(target)
assert len(w._leaf_order) == before
print(f'PASS collapse: clade of {len(target)} taxa folds to one leaf and back')

# 5. outgroup reroot renders
w.outgroup_combo.setCurrentIndex(3)  # some taxon
assert w.outgroup is not None
w.outgroup_combo.setCurrentIndex(0)
print('PASS outgroup: reroot and reset')

# 6. consensus from a bootstrap trees file
boot = tree_file.replace('_phyml_tree.txt', '_phyml_boot_trees.txt')
if os.path.exists(boot):
    trees = list(Phylo.parse(boot, 'newick'))
    w.load_tree_object(Phylo, 'unused') if False else None
    from Bio.Phylo.Consensus import majority_consensus
    cons = majority_consensus(trees)
    w.load_tree_object(cons, 'consensus-test')
    assert len(w._leaf_order) == 8
    print(f'PASS consensus: majority over {len(trees)} replicate trees')
else:
    print('SKIP consensus: no *_boot_trees.txt next to the tree')

print('ALL TREE VIEWER TESTS PASSED')
