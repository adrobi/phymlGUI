import json
import os
import shutil

import pytest
from conftest import DATA, ROOT

from phyml_core.engines import ENGINES
from phyml_core.engines.base import Engine, EngineOutputs, Issue, format_issue
from phyml_core.engines.iqtree import (UFBOOT_MIN_REPLICATES, IqTree, parse_iqtree_stats,
                                       ufboot_replicates)
from phyml_core.engines.phyml import PhyML
from phyml_core.launchers import Native
from phyml_core.paths import AppPaths

Q = {'model': 'MFP', 'mpi_np': '2', 'support_method': 'bootstrap', 'bootstrap_replicates': '1000'}

NT_MODELS = ["MFP", "GTR+F+G4", "HKY+F+G4", "TIM2+F+G4", "TVM+F+G4"]
AA_MODELS = ["MFP", "LG+G4", "WAG+G4", "JTT+G4", "mtREV+G4"]


@pytest.fixture
def paths(tmp_path):
    return AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path / 'data'))


@pytest.fixture
def exe(tmp_path):
    """An existing IQ-TREE-looking file outside bin/."""
    path = tmp_path / 'iqtree2.exe'
    path.write_bytes(b'')
    return str(path)


def keys(issues):
    return [i.key for i in issues]


# --- identity / registry ------------------------------------------------------------------

def test_identity():
    engine = IqTree()
    assert isinstance(engine, Engine)
    assert (engine.key, engine.name, engine.label_key) == ('iqtree', 'IQ-TREE', 'engine_iqtree')


def test_registry_keys():
    assert list(ENGINES) == ['phyml', 'iqtree']
    assert isinstance(ENGINES['phyml'], PhyML) and isinstance(ENGINES['iqtree'], IqTree)
    assert all(engine.key == key for key, engine in ENGINES.items())


@pytest.mark.parametrize('key', ['engine_iqtree', 'iqtree_ufboot_min'])
def test_texts_exist_in_both_languages(key):
    loc = json.loads((ROOT / 'locales.json').read_text(encoding='utf-8'))
    assert loc['en'][key] and loc['ru'][key]
    assert loc['en'][key].count('{}') == loc['ru'][key].count('{}')


def test_ufboot_warning_text_takes_the_new_and_the_requested_count():
    assert '1000' in format_issue(Issue('warning', 'iqtree_ufboot_min', ('1000', '100')))


# --- command ------------------------------------------------------------------------------

def test_command_ufboot():
    assert IqTree().command('C:/b/iqtree2.exe', 'D:/d/a.phy', Q) == [
        'C:/b/iqtree2.exe', '-s', 'D:/d/a.phy', '--prefix', 'D:/d/a_iqtree', '-redo',
        '-m', 'MFP', '-T', '2', '-B', '1000']


def test_command_alrt_and_none():
    alrt = IqTree().command('x', 'D:/d/a.phy', dict(Q, support_method='-4'))
    assert alrt == ['x', '-s', 'D:/d/a.phy', '--prefix', 'D:/d/a_iqtree', '-redo',
                    '-m', 'MFP', '-T', '2', '--alrt', '1000']
    none = IqTree().command('x', 'D:/d/a.phy', dict(Q, support_method='0'))
    assert none == ['x', '-s', 'D:/d/a.phy', '--prefix', 'D:/d/a_iqtree', '-redo', '-m', 'MFP', '-T', '2']
    assert none[-2:] == ['-T', '2']


@pytest.mark.parametrize('method', ['-1', '-2', '-3', '-4', '-5'])
def test_command_any_negative_support_method_is_alrt(method):
    assert IqTree().command('x', 'a.phy', dict(Q, support_method=method))[-2:] == ['--alrt', '1000']


def test_command_uses_the_documented_defaults_for_a_bare_dict():
    assert IqTree().command('x', 'a.phy', {}) == [
        'x', '-s', 'a.phy', '--prefix', 'a_iqtree', '-redo', '-m', 'MFP', '-T', '2', '-B', '1000']


def test_command_never_emits_fewer_than_1000_ufboot_replicates():
    argv = IqTree().command('x', 'a.phy', dict(Q, bootstrap_replicates='100'))
    assert argv[argv.index('-B') + 1] == '1000'
    assert IqTree().command('x', 'a.phy', dict(Q, bootstrap_replicates='5000'))[-1] == '5000'


def test_command_passes_model_and_threads():
    argv = IqTree().command('x', 'a.phy', dict(Q, model='HKY+F+G4', mpi_np='8'))
    assert argv[argv.index('-m') + 1] == 'HKY+F+G4' and argv[argv.index('-T') + 1] == '8'


def test_command_ignores_phyml_only_and_mpi_settings():
    params = dict(Q, use_mpi=True, mpirun_path='mpiexec', datatype='aa', freq='m', tstv='e', pinv='0.1',
                  classes='4', gamma='e', search='SPR', optimize='tlr', parsimony=True)
    assert IqTree().command('x', 'a.phy', params) == IqTree().command('x', 'a.phy', Q)


def test_command_prefix_is_the_phylip_name_without_its_last_extension():
    argv = IqTree().command('x', 'D:/d/a.b.phy', Q)
    assert argv[argv.index('--prefix') + 1] == 'D:/d/a.b_iqtree'


def test_command_survives_none_values():
    argv = IqTree().command('x', 'a.phy', {'model': None, 'mpi_np': None, 'support_method': None,
                                           'bootstrap_replicates': None})
    assert None not in argv and argv[argv.index('-m') + 1] == 'MFP' and argv[argv.index('-T') + 1] == '2'


# --- normalize ----------------------------------------------------------------------------

def test_normalize_raises_ufboot():
    p, notes = IqTree().normalize(dict(Q, bootstrap_replicates='100'))
    assert p['bootstrap_replicates'] == '1000' and notes == [Issue('warning', 'iqtree_ufboot_min', ('1000', '100'))]
    assert IqTree().normalize(dict(Q, bootstrap_replicates='5000')) == (dict(Q, bootstrap_replicates='5000'), [])


def test_normalize_keeps_1000_and_does_not_mutate_the_input():
    params = dict(Q, bootstrap_replicates='100')
    normalized, _ = IqTree().normalize(params)
    assert params['bootstrap_replicates'] == '100' and normalized is not params
    assert IqTree().normalize(Q) == (Q, [])


def test_normalize_reports_the_value_the_user_typed():
    _, notes = IqTree().normalize(dict(Q, bootstrap_replicates=' 100 '))
    assert notes == [Issue('warning', 'iqtree_ufboot_min', ('1000', '100'))]
    p, notes = IqTree().normalize(dict(Q, bootstrap_replicates=''))
    assert p['bootstrap_replicates'] == '1000' and notes == [Issue('warning', 'iqtree_ufboot_min', ('1000', ''))]


def test_normalize_leaves_an_absent_replicate_count_absent():
    bare = {k: v for k, v in Q.items() if k != 'bootstrap_replicates'}
    assert IqTree().normalize(bare) == (bare, [])


@pytest.mark.parametrize('method', ['-4', '0'])
def test_normalize_ignores_replicates_unless_bootstrap(method):
    params = dict(Q, support_method=method, bootstrap_replicates='100')
    assert IqTree().normalize(params) == (params, [])


def test_ufboot_replicates_raised_to_1000():
    """IQ-TREE UFBoot refuses < 1000 replicates: the PhyML-sized value is raised."""
    assert UFBOOT_MIN_REPLICATES == 1000
    assert ufboot_replicates('100') == '1000'
    assert ufboot_replicates('1000') == '1000'
    assert ufboot_replicates('5000') == '5000'
    assert ufboot_replicates('') == '1000'
    assert ufboot_replicates('abc') == '1000'


# --- executable ---------------------------------------------------------------------------

def test_executable_prefers_the_configured_file(paths, exe):
    assert IqTree().executable({'iqtree_path': exe}, paths) == exe


def test_executable_falls_back_to_bin(paths):
    bin_exe = os.path.join(paths.bin_dir, 'iqtree2.exe')
    os.makedirs(paths.bin_dir)
    open(bin_exe, 'wb').close()
    assert IqTree().executable({'iqtree_path': ''}, paths) == bin_exe
    assert IqTree().executable({}, paths) == bin_exe


def test_executable_ignores_the_phyml_path(paths, exe):
    assert IqTree().executable({'phyml_path': exe}, paths) != exe


def test_executable_returns_the_configured_path_when_nothing_exists(paths, tmp_path):
    missing = str(tmp_path / 'gone.exe')
    assert IqTree().executable({'iqtree_path': missing}, paths) == missing


# --- validate -----------------------------------------------------------------------------

def test_validate_ok(paths, exe):
    assert IqTree().validate(dict(Q, iqtree_path=exe), paths) == []


def test_validate(paths, tmp_path, exe):
    missing = str(tmp_path / 'missing.exe')
    assert IqTree().validate(dict(Q, iqtree_path=missing), paths) == [
        Issue('error', 'val_no_exe', ('IQ-TREE', missing))]
    assert IqTree().validate(dict(Q, iqtree_path=exe, mpi_np='x'), paths) == [
        Issue('error', 'val_not_number', ('mpi_np', 'x'))]
    assert IqTree().validate(dict(Q, iqtree_path=exe), paths) == []


def test_validate_a_directory_is_not_an_exe(paths, tmp_path):
    assert keys(IqTree().validate(dict(Q, iqtree_path=str(tmp_path)), paths)) == ['val_no_exe']


def test_validate_empty_path_without_bin_reports_the_missing_exe(paths):
    issues = IqTree().validate(dict(Q, iqtree_path=''), paths)
    assert keys(issues) == ['val_no_exe'] and issues[0].args[0] == 'IQ-TREE'


def test_validate_uses_the_bin_fallback(paths):
    os.makedirs(paths.bin_dir)
    open(os.path.join(paths.bin_dir, 'iqtree2.exe'), 'wb').close()
    assert IqTree().validate(dict(Q, iqtree_path=''), paths) == []


@pytest.mark.parametrize('value, ok', [('1', True), ('2', True), ('16', True), (' 4 ', True), ('', False),
                                       ('0', False), ('-2', False), ('1.5', False), ('x', False), ('AUTO', False)])
def test_validate_threads_are_always_a_positive_integer(paths, exe, value, ok):
    for use_mpi in (False, True):          # IQ-TREE has no MPI mode: -T is checked either way
        issues = IqTree().validate(dict(Q, iqtree_path=exe, mpi_np=value, use_mpi=use_mpi), paths)
        assert (issues == []) is ok
        if not ok:
            assert issues == [Issue('error', 'val_not_number', ('mpi_np', value))]


def test_validate_an_absent_thread_count_means_the_default(paths, exe):
    params = {k: v for k, v in Q.items() if k != 'mpi_np'}
    assert IqTree().validate(dict(params, iqtree_path=exe), paths) == []


@pytest.mark.parametrize('value, ok', [('1000', True), ('100', True), ('1', True), ('5000', True), ('', False),
                                       ('0', False), ('10.5', False), ('abc', False), ('-5', False)])
def test_validate_replicates_when_bootstrap(paths, exe, value, ok):
    """Anything below 1000 is valid input: normalize() raises it."""
    issues = IqTree().validate(dict(Q, iqtree_path=exe, bootstrap_replicates=value), paths)
    assert (issues == []) is ok
    if not ok:
        assert issues == [Issue('error', 'val_not_number', ('bootstrap_replicates', value))]


@pytest.mark.parametrize('method', ['-4', '0'])
def test_validate_ignores_replicates_unless_bootstrap(paths, exe, method):
    assert IqTree().validate(dict(Q, iqtree_path=exe, support_method=method, bootstrap_replicates='abc'), paths) == []


def test_validate_ignores_phyml_only_parameters(paths, exe):
    params = dict(Q, iqtree_path=exe, tstv='x', pinv='9', classes='0', gamma='-1', use_mpi=True,
                  mpirun_path='nowhere')
    assert IqTree().validate(params, paths) == []


def test_validate_collects_all_problems_at_once(paths, tmp_path):
    issues = IqTree().validate(dict(Q, iqtree_path=str(tmp_path / 'no.exe'), mpi_np='x',
                                    bootstrap_replicates='y'), paths)
    assert keys(issues) == ['val_no_exe', 'val_not_number', 'val_not_number']
    assert [i.args[0] for i in issues[1:]] == ['bootstrap_replicates', 'mpi_np']


def test_validate_survives_none_values(paths, exe):
    params = dict(Q, iqtree_path=exe, mpi_np=None, bootstrap_replicates=None, support_method=None)
    assert IqTree().validate(params, paths) == []


def test_validate_messages_name_the_ui_label_not_the_settings_key(paths, exe):
    issues = IqTree().validate(dict(Q, iqtree_path=exe, mpi_np='x'), paths)
    assert 'mpi_np' not in format_issue(issues[0])


# --- outputs / stats / launcher / models --------------------------------------------------

def test_outputs():
    out = IqTree().outputs('D:/d/a.phy')
    assert out == EngineOutputs(tree='D:/d/a_iqtree.treefile', stats='D:/d/a_iqtree.iqtree',
                                boot_trees=None, log='D:/d/a_iqtree.log')
    assert out.boot_trees is None


def test_outputs_share_the_prefix_of_the_command():
    argv = IqTree().command('x', 'D:/d/a.phy', Q)
    prefix = argv[argv.index('--prefix') + 1]
    out = IqTree().outputs('D:/d/a.phy')
    assert out.tree == prefix + '.treefile' and out.stats == prefix + '.iqtree' and out.log == prefix + '.log'


def test_parse_iqtree_stats_reads_the_real_report():
    s = parse_iqtree_stats(str(DATA / 'x.iqtree'))
    assert s['model'] == 'JC' and s['taxa'] == '8' and s['lnL'] == '-1828.7117'


def test_engine_parse_stats_reads_the_stats_output(tmp_path):
    phylip = tmp_path / 'a.phy'
    shutil.copy(DATA / 'x.iqtree', tmp_path / 'a_iqtree.iqtree')
    stats = IqTree().parse_stats(IqTree().outputs(str(phylip)))
    assert stats['model'] == 'JC' and stats['lnL'] == '-1828.7117' and stats['time']


def test_parse_stats_of_a_missing_file_is_empty(tmp_path):
    assert IqTree().parse_stats(IqTree().outputs(str(tmp_path / 'nope.phy'))) == {}
    assert parse_iqtree_stats(str(tmp_path / 'nope.iqtree')) == {}


def test_launcher_is_native():
    assert IqTree().launcher(Q) == Native()
    assert IqTree().launcher(dict(Q, use_mpi=True, mpirun_path='mpiexec', mpi_np='4')) == Native()
    assert IqTree().launcher({}) == Native()


def test_models_list_has_hky_not_hky2():
    assert 'HKY+F+G4' in IqTree().models('nt') and 'HKY2+F+G4' not in IqTree().models('nt')


def test_models_unchanged():
    assert IqTree().models('nt') == NT_MODELS
    assert IqTree().models('aa') == AA_MODELS


def test_models_returns_a_fresh_list():
    IqTree().models('nt').append('junk')
    assert IqTree().models('nt') == NT_MODELS


def test_both_engines_offer_a_model_list_per_datatype():
    for engine in ENGINES.values():
        assert engine.models('nt') and engine.models('aa') and engine.models('nt') != engine.models('aa')
