"""Stage-2 tree viewer: layouts, grid, colors, collapse, outgroup, consensus."""
import io

import pytest
from Bio import Phylo
from Bio.Phylo.Consensus import majority_consensus
from matplotlib.lines import Line2D

from conftest import DATA
from phyml_ui.tree_viewer import TreeViewerWidget

TREE_FILE = DATA / 'cytb_tree.nwk'
BOOT_TREES_FILE = DATA / 'cytb_boot_trees.nwk'


@pytest.fixture
def viewer(qtbot):
    """A viewer with the 8-taxon CytB tree (with supports) loaded."""
    w = TreeViewerWidget()
    qtbot.addWidget(w)
    w.load_tree(str(TREE_FILE))
    assert len(w._leaf_order) == 8
    return w


def test_circle_polytomy_centered(qtbot):
    """Circular layout: a polytomy node sits in the middle of its children's arc."""
    w = TreeViewerWidget()
    qtbot.addWidget(w)
    w.load_tree_object(
        Phylo.read(io.StringIO('((A:1,B:1,C:1,D:1):1,E:1,F:1);'), 'newick'), 'polytomy')
    w.set_layout('circle')
    tree, coords = w._coords
    node = tree.root.clades[0]
    child_angles = [coords[id(c)][1] for c in node.clades]
    expected = (min(child_angles) + max(child_angles)) / 2
    assert abs(coords[id(node)][1] - expected) < 1e-9, (coords[id(node)][1], expected)


def test_layouts_render(viewer):
    for layout in ('rect', 'slanted', 'circle'):
        viewer.set_layout(layout)
        assert viewer.layout == layout


def test_grid_drawn_and_toggleable(viewer):
    """The manual distance grid is actually drawn (ax.grid dies with axis_off)."""
    viewer.set_layout('rect')
    grid_on = sum(1 for l in viewer.ax.lines if isinstance(l, Line2D))
    viewer.chk_grid.setChecked(False)
    grid_off = sum(1 for l in viewer.ax.lines if isinstance(l, Line2D))
    viewer.chk_grid.setChecked(True)
    assert grid_on >= 3 and grid_off < grid_on, (grid_on, grid_off)


def test_theme_colors(viewer):
    """Theme-aware colors recolor the render."""
    viewer.set_colors('#E6E8EB', '#37C894', '#26282D')
    assert viewer._bg == '#26282D' and viewer.figure.patch.get_facecolor()[:3] != (1, 1, 1)
    viewer.set_colors('#424242', '#1E9E6A', '#FFFFFF')


def test_threshold_grid_supports_options(viewer):
    """Support threshold + grid/support toggles do not break rendering."""
    viewer.threshold_slider.setValue(70)
    assert viewer.threshold == 70
    viewer.chk_grid.setChecked(False)
    viewer.chk_supports.setChecked(False)
    viewer.chk_supports.setChecked(True)


def test_collapse_and_expand(viewer):
    """The first real internal clade folds into one display leaf and back."""
    src = Phylo.read(str(TREE_FILE), 'newick')
    candidates = [cl for cl in src.get_nonterminals()
                  if 2 <= len(cl.get_terminals()) < len(src.get_terminals())]
    assert candidates, 'no internal clades to collapse'
    target = frozenset(t.name for t in candidates[0].get_terminals())
    viewer.set_layout('rect')
    before = len(viewer._leaf_order)
    viewer.collapse_clade(target)
    assert len(viewer._leaf_order) == before - len(target) + 1, (before, len(viewer._leaf_order))
    viewer.collapse_clade(target)
    assert len(viewer._leaf_order) == before


def test_outgroup_reroot_and_reset(viewer):
    viewer.outgroup_combo.setCurrentIndex(3)  # some taxon
    assert viewer.outgroup is not None
    viewer.outgroup_combo.setCurrentIndex(0)
    assert viewer.outgroup is None


def test_majority_consensus_from_boot_trees(viewer):
    trees = list(Phylo.parse(str(BOOT_TREES_FILE), 'newick'))
    assert len(trees) == 20
    cons = majority_consensus(trees)
    viewer.load_tree_object(cons, 'consensus-test')
    assert len(viewer._leaf_order) == 8
