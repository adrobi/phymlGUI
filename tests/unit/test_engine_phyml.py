import json
import os
import shutil

import pytest
from phyml_core.utils import default_mpirun, exe_name
from conftest import DATA, ROOT

from phyml_core import settings
from phyml_core.engines import ENGINES
from phyml_core.engines.base import (Engine, EngineOutputs, Issue, format_issue, parse_decimal,
                                     positive_int, positive_number)
from phyml_core.engines.phyml import PhyML, parse_phyml_stats
from phyml_core.launchers import Mpi, Native
from phyml_core.paths import AppPaths

P = {'datatype': 'nt', 'model': 'HKY85', 'support_method': 'bootstrap', 'bootstrap_replicates': '100',
     'freq': 'default', 'tstv': 'e', 'pinv': '0.0', 'classes': '4', 'gamma': 'e',
     'search': 'NNI', 'optimize': 'tlr', 'parsimony': False}

NT_MODELS = ["HKY85", "JC69", "K80", "F81", "F84", "TN93", "GTR", "custom"]
AA_MODELS = ["LG", "WAG", "JTT", "MtREV", "Dayhoff", "DCMut", "RtREV", "CPREV", "VT", "Blosum62",
             "MtMam", "MtArt", "HIVw", "HIVb", "custom"]


@pytest.fixture
def paths(tmp_path):
    return AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path / 'data'))


@pytest.fixture
def exe(tmp_path):
    """An existing PhyML-looking file outside bin/."""
    path = tmp_path / exe_name('phyml')
    path.write_bytes(b'')
    return str(path)


def keys(issues):
    return [i.key for i in issues]


# --- base helpers -------------------------------------------------------------------------

def test_engine_is_abstract():
    with pytest.raises(TypeError):
        Engine()


def test_phyml_is_registered_with_its_identity():
    assert isinstance(ENGINES['phyml'], PhyML)
    engine = PhyML()
    assert (engine.key, engine.name, engine.label_key) == ('phyml', 'PhyML', 'engine_phyml')


def test_issue_and_outputs_are_frozen_values():
    assert Issue('error', 'k') == Issue('error', 'k', ())
    assert Issue('warning', 'k', ('a',)).args == ('a',)
    assert EngineOutputs('t', 's', None, None).boot_trees is None
    with pytest.raises(Exception):
        Issue('error', 'k').key = 'other'


def test_format_issue_fills_the_localized_template():
    from phyml_core.i18n import _t
    issue = Issue('error', 'val_not_number', ('threshold', '0'))
    assert format_issue(issue) == _t('val_not_number').format('threshold', '0')
    assert 'threshold' in format_issue(issue) and '0' in format_issue(issue)


@pytest.mark.parametrize('lang', ['en', 'ru'])
@pytest.mark.parametrize('name, label_key', [
    ('bootstrap_replicates', 'lbl_boot'), ('mpi_np', 'lbl_mpi_np'), ('pinv', 'lbl_pinv'),
    ('classes', 'lbl_classes'), ('tstv', 'lbl_tstv'), ('gamma', 'lbl_gamma')])
def test_format_issue_uses_ui_labels_for_parameter_names(monkeypatch, lang, name, label_key):
    from phyml_core import i18n
    monkeypatch.setattr(i18n, 'LANG', lang)
    label = i18n._t(label_key)
    assert label.endswith(':')                      # the UI label carries a trailing colon...
    shown = label[:-1].strip()                      # ...which the message drops
    text = format_issue(Issue('error', 'val_not_number', (name, 'x')))
    assert text == i18n._t('val_not_number').format(shown, 'x')
    assert shown in text and name not in text


def test_format_issue_labels_only_parameter_names_of_val_not_number():
    from phyml_core.i18n import _t
    issue = Issue('error', 'val_no_exe', ('mpi_np', 'C:/x'))
    assert format_issue(issue) == _t('val_no_exe').format('mpi_np', 'C:/x')
    assert 'mpi_np_typo' in format_issue(Issue('error', 'val_not_number', ('mpi_np_typo', 'x')))


@pytest.mark.parametrize('key', ['val_not_number', 'val_no_exe', 'val_no_mpiexec', 'mpi_boot_msg'])
def test_validation_messages_exist_in_both_languages(key):
    loc = json.loads((ROOT / 'locales.json').read_text(encoding='utf-8'))
    assert loc['en'][key] and loc['ru'][key]
    assert loc['en'][key].count('{}') == loc['ru'][key].count('{}')


@pytest.mark.parametrize('value', ['1', '100', '0.5', '2.', '.5', '0.001', ' 3 '])
def test_positive_number_accepts_plain_positive_decimals(value):
    assert positive_number(value)


@pytest.mark.parametrize('value', ['', '0', '0.0', '-1', 'abc', 'e', 'nan', 'inf', '1_0', '1,5', '\u0661\u0662',
                                   '+1', '-1e3', '1e', 'e3', '1e+', '1e-', '1e3.5', '1e_3', '1 e3', 'infinity',
                                   '1e999', '0e0', '1e-999', '1e\u0663', '\u0661e3'])
def test_positive_number_rejects_everything_else(value):
    assert not positive_number(value)


@pytest.mark.parametrize('value, expected', [('1e-3', 0.001), ('2E2', 200.0), ('1.5e+1', 15.0), ('.5e1', 5.0),
                                             ('2.e1', 20.0), (' 1e3 ', 1000.0), ('0.5', 0.5), ('3', 3.0)])
def test_parse_decimal_accepts_exponent_notation(value, expected):
    assert parse_decimal(value) == expected
    assert positive_number(value)


@pytest.mark.parametrize('value', ['', '-1', '+1', 'nan', 'inf', '1e999', '1_0', '\u0661\u0662', 'e3', '1e'])
def test_parse_decimal_rejects_what_float_would_misread(value):
    assert parse_decimal(value) is None


@pytest.mark.parametrize('value, ok', [('1', True), ('100', True), (' 4 ', True), ('0', False), ('-2', False),
                                       ('2.5', False), ('', False), ('x', False)])
def test_positive_int(value, ok):
    assert positive_int(value) is ok


# --- command ------------------------------------------------------------------------------

def test_command_matches_current_argv():
    assert PhyML().command('C:/b/phyml.exe', 'D:/d/a.phy', P) == [
        'C:/b/phyml.exe', '-i', 'D:/d/a.phy', '-d', 'nt', '-m', 'HKY85', '-b', '100',
        '-t', 'e', '-v', '0.0', '-c', '4', '-a', 'e', '-s', 'NNI', '-o', 'tlr']


def test_command_alrt_freq_parsimony_and_empty_values():
    argv = PhyML().command('x', 'a.phy', dict(P, support_method='-4', freq='m', parsimony=True, tstv=''))
    assert argv[argv.index('-b') + 1] == '-4' and argv[argv.index('-f') + 1] == 'm'
    assert '-t' not in argv and argv[-1] == '-p'


def test_command_omits_freq_when_missing():
    params = {k: v for k, v in P.items() if k != 'freq'}
    argv = PhyML().command('x', 'a.phy', params)
    assert '-f' not in argv and None not in argv


def test_command_omits_every_empty_optional_value():
    argv = PhyML().command('x', 'a.phy', dict(P, tstv='', pinv='', classes='', gamma='', freq=''))
    assert argv == ['x', '-i', 'a.phy', '-d', 'nt', '-m', 'HKY85', '-b', '100', '-s', 'NNI', '-o', 'tlr']


def test_command_freq_default_is_not_passed():
    assert '-f' not in PhyML().command('x', 'a.phy', dict(P, freq='default'))


def test_command_uses_the_documented_defaults_for_a_bare_dict():
    assert PhyML().command('x', 'a.phy', {}) == [
        'x', '-i', 'a.phy', '-d', 'nt', '-m', 'HKY85', '-b', '100', '-s', 'NNI', '-o', 'tlr']


def test_command_has_no_launcher_prefix_and_ignores_mpi_settings():
    argv = PhyML().command('x', 'a.phy', dict(P, use_mpi=True, mpirun_path='mpiexec', mpi_np='4'))
    assert argv[0] == 'x' and 'mpiexec' not in argv and '-np' not in argv


# --- launcher / outputs / stats / models --------------------------------------------------

def test_launcher_mpi_and_native():
    launcher = PhyML().launcher(dict(P, use_mpi=True, mpirun_path='C:/MPI/mpiexec.exe', mpi_np='2'))
    assert launcher == Mpi('C:/MPI/mpiexec.exe', 2)
    assert launcher.wrap(['x']) == ['C:/MPI/mpiexec.exe', '-np', '2', 'x']
    assert PhyML().launcher(dict(P, use_mpi=False)).wrap(['x']) == ['x']
    assert PhyML().launcher(P) == Native()


def test_launcher_resolves_a_bare_mpiexec_through_path(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda name, *a, **k: 'C:/MS/mpiexec.exe' if name == 'mpiexec' else None)
    launcher = PhyML().launcher(dict(P, use_mpi=True, mpirun_path='mpiexec', mpi_np='3'))
    assert launcher == Mpi('C:/MS/mpiexec.exe', 3)


def test_launcher_keeps_the_stored_name_when_which_finds_nothing(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    assert PhyML().launcher(dict(P, use_mpi=True, mpirun_path='mpiexec', mpi_np='2')) == Mpi('mpiexec', 2)


def test_outputs():
    out = PhyML().outputs('D:/d/a.phy')
    assert out == EngineOutputs(tree='D:/d/a.phy_phyml_tree.txt', stats='D:/d/a.phy_phyml_stats.txt',
                                boot_trees='D:/d/a.phy_phyml_boot_trees.txt', log=None)


def test_parse_phyml_stats_reads_the_real_report():
    s = parse_phyml_stats(str(DATA / 'x_phyml_stats.txt'))
    assert s['model'] == 'HKY85' and s['taxa'] == '8' and s['lnL'] == '-1811.15467'


def test_engine_parse_stats_reads_the_stats_output(tmp_path):
    phylip = tmp_path / 'a.phy'
    shutil.copy(DATA / 'x_phyml_stats.txt', str(phylip) + '_phyml_stats.txt')
    stats = PhyML().parse_stats(PhyML().outputs(str(phylip)))
    assert stats['model'] == 'HKY85' and stats['time']


def test_parse_stats_of_a_missing_file_is_empty(tmp_path):
    assert PhyML().parse_stats(PhyML().outputs(str(tmp_path / 'nope.phy'))) == {}


def test_models_unchanged():
    assert PhyML().models('nt') == NT_MODELS
    assert PhyML().models('aa') == AA_MODELS


def test_models_returns_a_fresh_list():
    PhyML().models('nt').append('junk')
    assert PhyML().models('nt') == NT_MODELS


def test_normalize_changes_nothing():
    params = dict(P)
    normalized, issues = PhyML().normalize(params)
    assert normalized == P and issues == []
    assert normalized is not params


# --- executable ---------------------------------------------------------------------------

def test_executable_prefers_the_configured_file(paths, exe):
    assert PhyML().executable({'phyml_path': exe}, paths) == exe


def test_executable_falls_back_to_bin(paths):
    bin_exe = os.path.join(paths.bin_dir, exe_name('phyml-mpi'))
    os.makedirs(paths.bin_dir)
    open(bin_exe, 'wb').close()
    assert PhyML().executable({'phyml_path': ''}, paths) == bin_exe
    assert PhyML().executable({}, paths) == bin_exe


def test_executable_picks_the_build_matching_the_mpi_mode(paths):
    os.makedirs(paths.bin_dir)
    for name in (exe_name('phyml'), exe_name('phyml-mpi')):
        open(os.path.join(paths.bin_dir, name), 'wb').close()
    assert PhyML().executable({'use_mpi': True}, paths) == os.path.join(paths.bin_dir, exe_name('phyml-mpi'))
    serial = os.path.join(paths.bin_dir, exe_name('phyml'))
    assert PhyML().executable({'use_mpi': False}, paths) == serial
    assert PhyML().executable({}, paths) == serial


def test_serial_bootstrap_is_valid_when_the_serial_build_is_bundled(paths):
    """AppImage ships phyml and phyml-mpi: defaults (bootstrap, no MPI) must use phyml."""
    os.makedirs(paths.bin_dir)
    for name in (exe_name('phyml'), exe_name('phyml-mpi')):
        with open(os.path.join(paths.bin_dir, name), 'wb') as f:
            f.write(b'MPI_Init' if name.startswith('phyml-mpi') else b'serial')
    issues = PhyML().validate({'use_mpi': False, 'support_method': 'bootstrap'}, paths)
    assert [i.key for i in issues] == []


def test_executable_resolves_a_stored_relative_path(paths):
    os.makedirs(os.path.join(paths.app_dir, 'tools'))
    target = os.path.join(paths.app_dir, 'tools', exe_name('phyml'))
    open(target, 'wb').close()
    assert PhyML().executable({'phyml_path': os.path.join('tools', exe_name('phyml'))}, paths) == target


def test_executable_returns_the_configured_path_when_nothing_exists(paths, tmp_path):
    missing = str(tmp_path / 'gone.exe')
    assert PhyML().executable({'phyml_path': missing}, paths) == missing


# --- validate -----------------------------------------------------------------------------

def test_validate_ok(paths, exe):
    assert PhyML().validate(dict(P, phyml_path=exe, use_mpi=False, support_method='-4'), paths) == []


def test_validate_accepts_the_shipped_defaults(paths, exe):
    """pinv '0.0' and the other defaults must validate."""
    assert PhyML().validate(dict(settings.DEFAULTS, phyml_path=exe), paths) == []


def test_validate_missing_exe(paths, tmp_path):
    missing = str(tmp_path / 'missing.exe')
    assert PhyML().validate(dict(P, phyml_path=missing), paths) == [
        Issue('error', 'val_no_exe', ('PhyML', missing))]


def test_validate_a_directory_is_not_an_exe(paths, tmp_path):
    assert keys(PhyML().validate(dict(P, phyml_path=str(tmp_path)), paths)) == ['val_no_exe']


def test_validate_empty_path_without_bin_reports_the_missing_exe(paths):
    issues = PhyML().validate(dict(P, phyml_path=''), paths)
    assert keys(issues) == ['val_no_exe'] and issues[0].args[0] == 'PhyML'


def test_validate_uses_the_bin_fallback(paths):
    os.makedirs(paths.bin_dir)
    open(os.path.join(paths.bin_dir, exe_name('phyml')), 'wb').close()
    assert PhyML().validate(dict(P, phyml_path=''), paths) == []


def test_validate_serial_bootstrap_on_mpi_build(paths, tmp_path):
    mpi_exe = tmp_path / exe_name('phyml-mpi')
    mpi_exe.write_bytes(b'')
    issues = PhyML().validate(dict(P, phyml_path=str(mpi_exe), use_mpi=False), paths)
    assert issues == [Issue('error', 'mpi_boot_msg')]


def test_validate_mpi_build_is_fine_with_mpi_alrt_or_a_serial_build(paths, tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: 'C:/MS/mpiexec.exe')
    mpi_exe = tmp_path / exe_name('phyml-mpi')
    mpi_exe.write_bytes(b'')
    base = dict(P, phyml_path=str(mpi_exe), mpirun_path='mpiexec', mpi_np='2')
    assert PhyML().validate(dict(base, use_mpi=True), paths) == []
    assert PhyML().validate(dict(base, use_mpi=False, support_method='-4'), paths) == []
    serial = tmp_path / exe_name('phyml')
    serial.write_bytes(b'')
    assert PhyML().validate(dict(base, phyml_path=str(serial), use_mpi=False), paths) == []


def test_validate_serial_bootstrap_check_sees_the_bin_fallback(paths):
    os.makedirs(paths.bin_dir)
    open(os.path.join(paths.bin_dir, exe_name('phyml-mpi')), 'wb').close()
    assert keys(PhyML().validate(dict(P, phyml_path='', use_mpi=False), paths)) == ['mpi_boot_msg']


def test_validate_reports_only_the_missing_exe_not_a_guess_about_its_build(paths, tmp_path):
    missing = str(tmp_path / exe_name('phyml-mpi'))
    assert keys(PhyML().validate(dict(P, phyml_path=missing, use_mpi=False), paths)) == ['val_no_exe']


def test_validate_numbers(paths, exe):
    issues = PhyML().validate(dict(P, phyml_path=exe, bootstrap_replicates='abc', classes='0', pinv='x'), paths)
    assert keys(issues) == ['val_not_number'] * 3
    assert {i.args for i in issues} == {('bootstrap_replicates', 'abc'), ('classes', '0'), ('pinv', 'x')}
    assert all(i.level == 'error' for i in issues)
    # 'e' means "estimate" and is a legal value for pinv and gamma (and tstv)
    assert PhyML().validate(dict(P, phyml_path=exe, pinv='e', gamma='e', tstv='e'), paths) == []


@pytest.mark.parametrize('pinv, ok', [('0', True), ('0.0', True), ('0.35', True), ('.5', True), ('0.999', True),
                                      ('e', True), ('', True), ('1', False), ('1.0', False), ('-0.1', False),
                                      ('2', False), ('abc', False)])
def test_validate_pinv_is_e_or_a_fraction_below_one(paths, exe, pinv, ok):
    issues = PhyML().validate(dict(P, phyml_path=exe, pinv=pinv), paths)
    assert (issues == []) is ok
    if not ok:
        assert issues == [Issue('error', 'val_not_number', ('pinv', pinv))]


@pytest.mark.parametrize('field', ['tstv', 'gamma'])
@pytest.mark.parametrize('value, ok', [('e', True), ('', True), ('4.0', True), ('2', True), ('0.5', True),
                                       ('1e-3', True), ('2E2', True),
                                       ('0', False), ('-1', False), ('x', False), ('1e', False), ('nan', False)])
def test_validate_tstv_and_gamma_are_e_or_positive(paths, exe, field, value, ok):
    issues = PhyML().validate(dict(P, phyml_path=exe, **{field: value}), paths)
    assert (issues == []) is ok
    if not ok:
        assert issues == [Issue('error', 'val_not_number', (field, value))]


@pytest.mark.parametrize('value, ok', [('4', True), ('1', True), ('', True), ('0', False), ('2.5', False),
                                       ('-3', False), ('e', False), ('x', False)])
def test_validate_classes_are_a_positive_integer_or_empty(paths, exe, value, ok):
    issues = PhyML().validate(dict(P, phyml_path=exe, classes=value), paths)
    assert (issues == []) is ok


@pytest.mark.parametrize('value, ok', [('100', True), ('1', True), ('', False), ('0', False), ('10.5', False),
                                       ('abc', False)])
def test_validate_bootstrap_replicates_when_bootstrap(paths, exe, value, ok):
    issues = PhyML().validate(dict(P, phyml_path=exe, bootstrap_replicates=value), paths)
    assert (issues == []) is ok


def test_validate_ignores_bootstrap_replicates_for_alrt(paths, exe):
    assert PhyML().validate(dict(P, phyml_path=exe, support_method='-4', bootstrap_replicates='abc'), paths) == []


def test_validate_ignores_mpi_np_when_mpi_is_off(paths, exe):
    assert PhyML().validate(dict(P, phyml_path=exe, use_mpi=False, mpi_np=''), paths) == []


@pytest.mark.parametrize('value, ok', [('2', True), ('16', True), ('', False), ('0', False), ('x', False),
                                       ('1.5', False)])
def test_validate_mpi_np_when_mpi_is_on(paths, exe, monkeypatch, value, ok):
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: 'C:/MS/mpiexec.exe')
    issues = PhyML().validate(dict(P, phyml_path=exe, use_mpi=True, mpi_np=value), paths)
    assert (issues == []) is ok
    if not ok:
        assert issues == [Issue('error', 'val_not_number', ('mpi_np', value))]


def test_validate_mpiexec_missing(paths, exe, tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    gone = str(tmp_path / 'MPI' / 'mpiexec.exe')
    issues = PhyML().validate(dict(P, phyml_path=exe, use_mpi=True, mpirun_path=gone, mpi_np='2'), paths)
    assert issues == [Issue('error', 'val_no_mpiexec', (gone,))]
    bare = PhyML().validate(dict(P, phyml_path=exe, use_mpi=True, mpirun_path='mpiexec', mpi_np='2'), paths)
    assert bare == [Issue('error', 'val_no_mpiexec', ('mpiexec',))]


def test_validate_mpiexec_present_as_a_file_or_a_command_name(paths, exe, tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    real = tmp_path / 'mpiexec.exe'
    real.write_bytes(b'')
    params = dict(P, phyml_path=exe, use_mpi=True, mpi_np='2')
    assert PhyML().validate(dict(params, mpirun_path=str(real)), paths) == []
    monkeypatch.setattr(shutil, 'which', lambda name, *a, **k: 'C:/MS/mpiexec.exe' if name == 'mpiexec' else None)
    assert PhyML().validate(dict(params, mpirun_path='mpiexec'), paths) == []


@pytest.mark.parametrize('blank', ['', '   '])
def test_blank_mpirun_path_falls_back_to_mpiexec(paths, exe, monkeypatch, blank):
    launcher_name = default_mpirun()   # mpiexec on Windows, mpirun elsewhere
    monkeypatch.setattr(shutil, 'which', lambda name, *a, **k: '/x/' + name if name == launcher_name else None)
    params = dict(P, phyml_path=exe, use_mpi=True, mpirun_path=blank, mpi_np='3')
    assert PhyML().validate(params, paths) == []
    assert PhyML().launcher(params) == Mpi('/x/' + launcher_name, 3)
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    assert PhyML().validate(params, paths) == [Issue('error', 'val_no_mpiexec', (launcher_name,))]


def test_validate_mpiexec_is_not_checked_when_mpi_is_off(paths, exe, monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    assert PhyML().validate(dict(P, phyml_path=exe, use_mpi=False, mpirun_path='nowhere'), paths) == []


def test_validate_collects_all_problems_at_once(paths, tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    issues = PhyML().validate(dict(P, phyml_path=str(tmp_path / 'no.exe'), use_mpi=True, mpirun_path='nowhere',
                                   mpi_np='x', classes='0'), paths)
    assert sorted(keys(issues)) == ['val_no_exe', 'val_no_mpiexec', 'val_not_number', 'val_not_number']


def test_validate_survives_none_values(paths, exe):
    assert PhyML().validate(dict(P, phyml_path=exe, tstv=None, pinv=None, classes=None, gamma=None), paths) == []
