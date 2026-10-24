import json
import os

import pytest

from phyml_core import settings
from phyml_core.i18n import _t
from phyml_core.paths import CONFIG_NAME, HISTORY_NAME, AppPaths


def test_defaults_match_the_window_config_keys():
    expected = {
        'engine': 'phyml', 'iqtree_path': '', 'phyml_path': '', 'mpirun_path': 'mpiexec',
        'muscle_path': '', 'datatype': 'nt', 'model': 'HKY85', 'support_method': 'bootstrap',
        'bootstrap_replicates': '100', 'use_mpi': False, 'mpi_np': '', 'freq': 'default',
        'tstv': 'e', 'pinv': '0.0', 'classes': '4', 'gamma': 'e', 'search': 'NNI',
        'optimize': 'tlr', 'parsimony': False, 'show_tree': True, 'theme': 'system',
        'accent': 'green', 'recent': [], 'presets': {}, 'window': {}, 'schema_version': 2,
    }
    assert settings.DEFAULTS == expected
    assert settings.SCHEMA_VERSION == 2
    assert settings.PATH_KEYS == ('phyml_path', 'iqtree_path', 'muscle_path', 'mpirun_path')


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = settings.load(str(tmp_path / 'absent.json'))
    assert cfg == settings.DEFAULTS and cfg is not settings.DEFAULTS
    cfg['recent'].append('x')                       # mutating the result must not leak
    cfg['window']['w'] = 1
    assert settings.DEFAULTS['recent'] == [] and settings.DEFAULTS['window'] == {}


def test_load_fills_missing_keys_and_coerces_types(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({'mpi_np': 8, 'recent': None, 'use_mpi': 'yes', 'custom_key': 1}), 'utf-8')
    cfg = settings.load(str(path))
    assert cfg['mpi_np'] == '8' and cfg['recent'] == [] and cfg['use_mpi'] is False
    assert cfg['custom_key'] == 1 and cfg['model'] == 'HKY85' and cfg['schema_version'] == 2


def test_load_coercion_rules(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({
        'bootstrap_replicates': 200,      # number -> str
        'pinv': 0.5,                      # float -> str
        'model': None,                    # not str/number -> default
        'theme': ['dark'],                # list for a str -> default
        'use_mpi': True,                  # real bool kept
        'parsimony': 1,                   # int is not a bool -> default
        'show_tree': 'false',             # str is not a bool -> default
        'recent': ['a.fasta', 'b.fasta'],
        'presets': [],                    # list for a dict -> default
        'window': {'w': 800},
        'schema_version': 1,              # always rewritten to the current version
    }), 'utf-8')
    cfg = settings.load(str(path))
    assert cfg['bootstrap_replicates'] == '200' and cfg['pinv'] == '0.5'
    assert cfg['model'] == 'HKY85' and cfg['theme'] == 'system'
    assert cfg['use_mpi'] is True and cfg['parsimony'] is False and cfg['show_tree'] is True
    assert cfg['recent'] == ['a.fasta', 'b.fasta'] and cfg['presets'] == {}
    assert cfg['window'] == {'w': 800} and cfg['schema_version'] == 2


def test_load_bool_is_not_a_string_number(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({'mpi_np': True}), 'utf-8')
    assert settings.load(str(path))['mpi_np'] == ''


def test_load_broken_json_keeps_copy_and_reports(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text('{oops', 'utf-8')
    errors = []
    cfg = settings.load(str(path), on_error=errors.append)
    assert cfg == settings.DEFAULTS
    assert len(errors) == 1 and '.broken' in errors[0]
    assert errors[0] == _t('err_settings_broken').format(str(path) + '.broken')
    broken = tmp_path / 'c.json.broken'
    assert broken.read_text('utf-8') == '{oops'
    assert path.read_text('utf-8') == '{oops'       # the damaged file itself is not rewritten


def test_load_broken_json_without_callback(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text('', 'utf-8')                     # empty file is not valid JSON either
    assert settings.load(str(path)) == settings.DEFAULTS
    assert (tmp_path / 'c.json.broken').exists()


def test_load_non_object_json_is_broken(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text('[1, 2]', 'utf-8')
    errors = []
    assert settings.load(str(path), errors.append) == settings.DEFAULTS
    assert len(errors) == 1 and (tmp_path / 'c.json.broken').read_text('utf-8') == '[1, 2]'


def test_load_non_utf8_file_is_broken(tmp_path):
    path = tmp_path / 'c.json'
    path.write_bytes('{"model": "Ж"}'.encode('cp1251'))
    errors = []
    assert settings.load(str(path), errors.append) == settings.DEFAULTS
    assert len(errors) == 1 and (tmp_path / 'c.json.broken').read_bytes() == path.read_bytes()


def test_load_unreadable_existing_file_raises(tmp_path):
    # the path exists but cannot be read (a directory is deterministic on Windows and POSIX):
    # load must not hand out defaults that a later save would write over the real settings
    errors = []
    with pytest.raises(OSError):
        settings.load(str(tmp_path), on_error=errors.append)
    assert errors == [] and not os.path.exists(str(tmp_path) + '.broken')


def test_save_is_atomic_and_roundtrips(tmp_path):
    path = tmp_path / 'c.json'
    cfg = settings.load(str(path))
    cfg['model'] = 'GTR'
    cfg['recent'] = [r'D:\данные\проект 1\a.fasta']
    cfg['custom_key'] = {'k': [1, 2]}
    settings.save(str(path), cfg)
    assert settings.load(str(path)) == cfg
    assert os.listdir(tmp_path) == ['c.json']
    settings.save(str(path), dict(cfg, model='JC69'))            # overwrite an existing file
    assert settings.load(str(path))['model'] == 'JC69'
    assert os.listdir(tmp_path) == ['c.json']


def test_save_writes_readable_utf8_json(tmp_path):
    path = tmp_path / 'c.json'
    settings.save(str(path), {'recent': ['D:/данные/a.fasta']})
    text = path.read_text('utf-8')
    assert 'данные' in text and '\\u' not in text                # ensure_ascii=False
    assert text.startswith('{\n    "recent"')                    # indent=4


def test_save_raises_oserror_for_directory_target(tmp_path):
    target = tmp_path / 'sub'
    target.mkdir()
    with pytest.raises(OSError):
        settings.save(str(target), {'a': 1})
    assert os.listdir(tmp_path) == ['sub']                       # no temp file left behind


def test_save_failure_keeps_previous_file(tmp_path):
    path = tmp_path / 'c.json'
    settings.save(str(path), {'a': 1})
    with pytest.raises(TypeError):
        settings.save(str(path), {'a': object()})                # not JSON-serialisable
    assert json.loads(path.read_text('utf-8')) == {'a': 1}
    assert os.listdir(tmp_path) == ['c.json']


def _paths(tmp_path):
    app = tmp_path / 'Мои программы' / 'phymlGUI'
    (app / 'bin').mkdir(parents=True)
    return AppPaths(app_dir=str(app), data_dir=str(app))


def test_to_disk_from_disk_roundtrip(tmp_path):
    p = _paths(tmp_path)
    inside = str(tmp_path / 'Мои программы' / 'phymlGUI' / 'bin' / 'phyml-mpi.exe')
    outside = str(tmp_path / 'данные' / 'a.fasta')
    cfg = dict(settings.DEFAULTS, phyml_path=inside, muscle_path=r'C:\tools\muscle.exe',
               recent=[inside, outside], model='GTR')
    stored = settings.to_disk(cfg, p)
    assert stored['phyml_path'] == os.path.join('bin', 'phyml-mpi.exe')    # relative on disk
    assert stored['muscle_path'] == r'C:\tools\muscle.exe'
    assert stored['recent'] == [os.path.join('bin', 'phyml-mpi.exe'), outside]
    assert stored['model'] == 'GTR'
    assert cfg['phyml_path'] == inside                                     # input not mutated
    restored = settings.from_disk(stored, p)
    assert restored == cfg                                                 # absolute again


def test_to_disk_from_disk_leave_missing_and_foreign_values_alone(tmp_path):
    p = _paths(tmp_path)
    assert settings.to_disk({'model': 'JC69'}, p) == {'model': 'JC69'}
    assert settings.from_disk({'model': 'JC69'}, p) == {'model': 'JC69'}
    odd = {'phyml_path': None, 'recent': 'not-a-list'}
    assert settings.from_disk(settings.to_disk(odd, p), p) == odd


def test_default_mpiexec_command_name_survives_a_save_load_cycle(tmp_path):
    # 'mpiexec' is resolved through PATH; it must never become <app_dir>\mpiexec
    p = _paths(tmp_path)
    cfg = dict(settings.DEFAULTS)
    assert settings.from_disk(settings.to_disk(cfg, p), p)['mpirun_path'] == 'mpiexec'
    # but a bare file name that really sits in app_dir is still resolved against it
    tool = os.path.join(p.app_dir, 'muscle.exe')
    open(tool, 'wb').close()
    stored = settings.to_disk(dict(cfg, muscle_path=tool), p)
    assert stored['muscle_path'] == 'muscle.exe'
    assert settings.from_disk(stored, p)['muscle_path'] == tool


def test_migrate_legacy_copies_once(tmp_path):
    cwd = tmp_path / 'old cwd'
    data = tmp_path / 'новая папка'
    cwd.mkdir()
    data.mkdir()
    (cwd / CONFIG_NAME).write_text('{"model": "GTR"}', 'utf-8')
    (cwd / HISTORY_NAME).write_text('[]', 'utf-8')
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(data))
    assert settings.migrate_legacy(p, str(cwd)) == [HISTORY_NAME, CONFIG_NAME]  # config last
    assert (data / CONFIG_NAME).read_text('utf-8') == '{"model": "GTR"}'
    assert (data / HISTORY_NAME).read_text('utf-8') == '[]'
    assert (cwd / CONFIG_NAME).exists() and (cwd / HISTORY_NAME).exists()  # originals stay
    assert settings.migrate_legacy(p, str(cwd)) == []                      # once only


def test_migrate_legacy_copies_what_exists(tmp_path):
    cwd = tmp_path / 'cwd'
    data = tmp_path / 'data'
    cwd.mkdir()
    data.mkdir()
    (cwd / HISTORY_NAME).write_text('[]', 'utf-8')
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(data))
    assert settings.migrate_legacy(p, str(cwd)) == [HISTORY_NAME]
    assert not (data / CONFIG_NAME).exists()


def test_migrate_legacy_history_only_copies_once(tmp_path):
    cwd = tmp_path / 'cwd'
    data = tmp_path / 'data'
    cwd.mkdir()
    data.mkdir()
    (cwd / HISTORY_NAME).write_text('["old"]', 'utf-8')
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(data))
    assert settings.migrate_legacy(p, str(cwd)) == [HISTORY_NAME]
    (data / HISTORY_NAME).write_text('["newer, written by the app"]', 'utf-8')
    assert settings.migrate_legacy(p, str(cwd)) == []        # no config in data_dir, still once
    assert (data / HISTORY_NAME).read_text('utf-8') == '["newer, written by the app"]'
    assert not (data / CONFIG_NAME).exists()


def test_migrate_legacy_never_overwrites_existing_files(tmp_path):
    cwd = tmp_path / 'cwd'
    data = tmp_path / 'data'
    cwd.mkdir()
    data.mkdir()
    (cwd / CONFIG_NAME).write_text('{"model": "GTR"}', 'utf-8')
    (cwd / HISTORY_NAME).write_text('["old"]', 'utf-8')
    (data / HISTORY_NAME).write_text('["keep me"]', 'utf-8')    # the app died before saving a config
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(data))
    assert settings.migrate_legacy(p, str(cwd)) == [CONFIG_NAME]
    assert (data / HISTORY_NAME).read_text('utf-8') == '["keep me"]'
    assert (data / CONFIG_NAME).read_text('utf-8') == '{"model": "GTR"}'


def test_migrate_legacy_failed_history_copy_keeps_gate_open(tmp_path, monkeypatch):
    cwd = tmp_path / 'cwd'
    data = tmp_path / 'data'
    cwd.mkdir()
    data.mkdir()
    (cwd / CONFIG_NAME).write_text('{"model": "GTR"}', 'utf-8')
    (cwd / HISTORY_NAME).write_text('[]', 'utf-8')
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(data))
    real_copy2 = settings.shutil.copy2

    def failing_copy2(src, dst, **kwargs):
        if os.path.basename(src) == HISTORY_NAME:
            raise OSError('disk full')
        return real_copy2(src, dst, **kwargs)

    monkeypatch.setattr(settings.shutil, 'copy2', failing_copy2)
    with pytest.raises(OSError):
        settings.migrate_legacy(p, str(cwd))
    assert not (data / CONFIG_NAME).exists()                 # config not copied: the gate stays open
    monkeypatch.undo()
    assert settings.migrate_legacy(p, str(cwd)) == [HISTORY_NAME, CONFIG_NAME]   # retried in full


def test_migrate_legacy_nothing_to_copy(tmp_path):
    cwd = tmp_path / 'cwd'
    cwd.mkdir()
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(tmp_path / 'not created yet'))
    assert settings.migrate_legacy(p, str(cwd)) == []
    assert not (tmp_path / 'not created yet').exists()


def test_migrate_legacy_creates_missing_data_dir(tmp_path):
    cwd = tmp_path / 'cwd'
    cwd.mkdir()
    (cwd / CONFIG_NAME).write_text('{}', 'utf-8')
    data = tmp_path / 'not created yet'
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(data))
    assert settings.migrate_legacy(p, str(cwd)) == [CONFIG_NAME]
    assert (data / CONFIG_NAME).exists()


def test_migrate_legacy_noop_when_cwd_is_data_dir(tmp_path):
    (tmp_path / CONFIG_NAME).write_text('{"model": "GTR"}', 'utf-8')
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(tmp_path))
    assert settings.migrate_legacy(p, str(tmp_path)) == []
    assert (tmp_path / CONFIG_NAME).read_text('utf-8') == '{"model": "GTR"}'


def test_migrate_legacy_noop_when_data_dir_has_config(tmp_path):
    cwd = tmp_path / 'cwd'
    data = tmp_path / 'data'
    cwd.mkdir()
    data.mkdir()
    (cwd / CONFIG_NAME).write_text('{"model": "GTR"}', 'utf-8')
    (data / CONFIG_NAME).write_text('{"model": "JC69"}', 'utf-8')
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(data))
    assert settings.migrate_legacy(p, str(cwd)) == []
    assert (data / CONFIG_NAME).read_text('utf-8') == '{"model": "JC69"}'  # never overwritten
