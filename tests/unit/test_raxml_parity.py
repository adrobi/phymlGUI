"""RAxML-NG Windows vs Linux parity check (packaging/raxml_parity.py)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('raxml_parity', ROOT / 'packaging' / 'raxml_parity.py')
parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parity)

TREE = '((A:0.1,B:0.2):0.05,(C:0.1,D:0.3):0.05,E:0.2);\n'
SWAPPED = '((A:0.1,C:0.2):0.05,(B:0.1,D:0.3):0.05,E:0.2);\n'


def _outputs(folder, best=TREE, boots=(TREE, SWAPPED), lnl='-1823.506511', fixed='-1900.123456'):
    folder.mkdir(parents=True)
    (folder / 'search.raxml.bestTree').write_text(best)
    (folder / 'search.raxml.log').write_text(f'... Final LogLikelihood: {lnl}\n')
    (folder / 'boot.raxml.bootstraps').write_text(''.join(boots))
    (folder / 'eval.raxml.log').write_text(f'Final LogLikelihood: {fixed}\n')
    return str(folder)


def test_identical_outputs_match(tmp_path):
    assert parity.compare(_outputs(tmp_path / 'w'), _outputs(tmp_path / 'l')) == []


def test_crlf_and_tiny_lnl_difference_still_match(tmp_path):
    win = _outputs(tmp_path / 'w', best=TREE.replace('\n', '\r\n'), lnl='-1823.5066')
    assert parity.compare(win, _outputs(tmp_path / 'l')) == []


def test_different_best_tree_is_reported(tmp_path):
    problems = parity.compare(_outputs(tmp_path / 'w', best=SWAPPED), _outputs(tmp_path / 'l'))
    assert len(problems) == 1 and 'search.raxml.bestTree' in problems[0]


def test_lnl_difference_is_reported(tmp_path):
    problems = parity.compare(_outputs(tmp_path / 'w', lnl='-1823.40'), _outputs(tmp_path / 'l'))
    assert len(problems) == 1 and 'search.raxml.log' in problems[0]


def test_bootstrap_and_fixed_tree_differences_are_reported(tmp_path):
    win = _outputs(tmp_path / 'w', boots=(TREE, TREE), fixed='-1900.123999')
    problems = parity.compare(win, _outputs(tmp_path / 'l'))
    assert len(problems) == 2
    assert any('bootstraps' in p for p in problems) and any('eval.raxml.log' in p for p in problems)


def test_missing_file_is_reported(tmp_path):
    lin = _outputs(tmp_path / 'l')
    win = _outputs(tmp_path / 'w')
    (Path(win) / 'boot.raxml.bootstraps').unlink()
    problems = parity.compare(win, lin)
    assert problems and 'boot.raxml.bootstraps' in problems[0]
