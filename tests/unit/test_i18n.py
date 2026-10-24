import json

from conftest import ROOT


def test_locales_have_same_keys():
    loc = json.loads((ROOT / 'locales.json').read_text(encoding='utf-8'))
    assert set(loc) >= {'en', 'ru'}
    assert len(loc['en']) == len(loc['ru']), 'locale key sets diverge'
    assert set(loc['en']) == set(loc['ru']), 'locale key sets diverge'
