import json

from conftest import ROOT


def test_locales_have_same_keys():
    loc = json.loads((ROOT / 'locales.json').read_text(encoding='utf-8'))
    assert set(loc) >= {'en', 'ru'}
    assert len(loc['en']) == len(loc['ru']), 'locale key sets diverge'
    assert set(loc['en']) == set(loc['ru']), 'locale key sets diverge'


def test_mpi_and_cpu_keys_present():
    """The MPI autodetect and CPU monitor strings exist in both languages."""
    loc = json.loads((ROOT / 'locales.json').read_text(encoding='utf-8'))
    keys = ['cores_info', 'cpu_sys', 'cpu_analysis', 'cpu_analysis_idle',
            'cpu_analysis_done', 'mpi_detected', 'mpi_boot_title', 'mpi_boot_msg']
    for lang in ('en', 'ru'):
        for k in keys:
            assert k in loc[lang], f'{lang} missing {k}'
