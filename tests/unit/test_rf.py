import io

from Bio import Phylo

from phyml_ui.tree_viewer import rf_distance, tree_splits


def _tree(newick):
    return Phylo.read(io.StringIO(newick), 'newick')


def test_rf_identical_and_quartet_swap():
    t1 = _tree('(A,(B,(C,D)));')
    t2 = _tree('(A,(C,(B,D)));')
    assert rf_distance(t1, t1) == (0, 0.0)
    assert rf_distance(t1, t2) == (1, 1.0)


def test_tree_splits_count():
    assert len(tree_splits(_tree('(A,(B,(C,D)));'))) == 1
