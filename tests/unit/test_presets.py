from phyml_core import presets, settings

OLD_KEYS = ('datatype', 'model', 'support_method', 'bootstrap_replicates',
            'freq', 'tstv', 'pinv', 'classes', 'gamma', 'search',
            'optimize', 'parsimony')


def test_preset_keys_are_the_old_twelve_plus_engine():
    assert presets.PRESET_KEYS == OLD_KEYS + ('engine',)


def test_preset_keys_are_all_settings_keys():
    assert set(presets.PRESET_KEYS) <= set(settings.DEFAULTS)


def test_builtin_screening_uses_alrt():
    assert presets.BUILTIN['preset_builtin_screen']['support_method'] == '-4'


def test_builtin_values_are_the_current_ones_plus_phyml_engine():
    assert set(presets.BUILTIN) == {'preset_builtin_screen', 'preset_builtin_pub'}
    assert presets.BUILTIN['preset_builtin_screen'] == {
        'datatype': 'nt', 'model': 'HKY85', 'support_method': '-4',
        'bootstrap_replicates': '100', 'freq': 'default', 'tstv': 'e',
        'pinv': '0.0', 'classes': '4', 'gamma': 'e', 'search': 'NNI',
        'optimize': 'tlr', 'parsimony': False, 'engine': 'phyml'}
    assert presets.BUILTIN['preset_builtin_pub'] == {
        'datatype': 'nt', 'model': 'GTR', 'support_method': 'bootstrap',
        'bootstrap_replicates': '1000', 'freq': 'default', 'tstv': 'e',
        'pinv': 'e', 'classes': '4', 'gamma': 'e', 'search': 'BEST',
        'optimize': 'tlr', 'parsimony': False, 'engine': 'phyml'}
    for preset in presets.BUILTIN.values():
        assert set(preset) == set(presets.PRESET_KEYS)


def test_extract_excludes_paths_and_display():
    cfg = dict(settings.DEFAULTS, engine='iqtree', model='GTR', phyml_path=r'D:\bin\phyml.exe',
               iqtree_path=r'D:\bin\iqtree2.exe', theme='dark', accent='blue',
               recent=['a.fasta'], show_tree=False, use_mpi=True, mpi_np='4')
    got = presets.extract(cfg)
    assert set(got) == set(presets.PRESET_KEYS)
    assert got['engine'] == 'iqtree' and got['model'] == 'GTR'
    for excluded in ('phyml_path', 'iqtree_path', 'theme', 'accent', 'recent', 'show_tree',
                     'use_mpi', 'mpi_np', 'presets', 'window', 'schema_version'):
        assert excluded not in got


def test_extract_takes_only_the_keys_that_are_present():
    assert presets.extract({'model': 'JC69', 'theme': 'dark'}) == {'model': 'JC69'}
    assert presets.extract({}) == {}


def test_apply_switches_engine_and_keeps_paths():
    params = dict(settings.DEFAULTS, engine='phyml', phyml_path=r'D:\bin\phyml.exe',
                  iqtree_path=r'D:\bin\iqtree2.exe', theme='dark', model='HKY85')
    preset = dict(presets.BUILTIN['preset_builtin_pub'], engine='iqtree')
    out = presets.apply(preset, params)
    assert out['engine'] == 'iqtree' and out['model'] == 'GTR' and out['search'] == 'BEST'
    assert out['bootstrap_replicates'] == '1000' and out['pinv'] == 'e'
    assert out['phyml_path'] == r'D:\bin\phyml.exe' and out['iqtree_path'] == r'D:\bin\iqtree2.exe'
    assert out['theme'] == 'dark'
    assert out is not params and params['engine'] == 'phyml' and params['model'] == 'HKY85'


def test_apply_ignores_keys_outside_the_preset_keys():
    preset = {'model': 'GTR', 'phyml_path': 'evil.exe', 'theme': 'dark', 'recent': ['x']}
    params = {'model': 'HKY85', 'phyml_path': 'good.exe', 'theme': 'light', 'recent': []}
    out = presets.apply(preset, params)
    assert out == {'model': 'GTR', 'phyml_path': 'good.exe', 'theme': 'light', 'recent': []}


def test_apply_preset_without_engine_keeps_the_current_engine():
    # presets saved before the engine became part of them
    old_user_preset = {k: presets.BUILTIN['preset_builtin_pub'][k] for k in OLD_KEYS}
    assert presets.apply(old_user_preset, {'engine': 'iqtree', 'model': 'HKY85'}) == dict(
        old_user_preset, engine='iqtree')


def test_apply_does_not_share_nested_values_with_params():
    params = {'recent': ['a.fasta']}
    out = presets.apply({'model': 'GTR'}, params)
    out['recent'].append('b.fasta')
    assert params['recent'] == ['a.fasta']


def test_extract_then_apply_roundtrip():
    cfg = dict(settings.DEFAULTS, engine='iqtree', model='GTR', search='BEST', parsimony=True)
    saved = presets.extract(cfg)
    fresh = dict(settings.DEFAULTS)
    assert presets.apply(saved, fresh) == dict(fresh, engine='iqtree', model='GTR', search='BEST',
                                               parsimony=True)
