from conftest import DATA
from phyml_core.pipeline import parse_stats, parse_iqtree_stats


def test_parse_phyml_stats():
    s = parse_stats(str(DATA / 'x_phyml_stats.txt'))
    assert s['model'] == 'HKY85' and s['taxa'] == '8' and s['lnL'] == '-1811.15467'
    assert s['gamma'] == '881.743' and s['tstv'] == '0.980317'


def test_parse_iqtree_stats():
    s = parse_iqtree_stats(str(DATA / 'x.iqtree'))
    assert s['model'] == 'JC' and s['taxa'] == '8' and s['lnL'] == '-1828.7117'
