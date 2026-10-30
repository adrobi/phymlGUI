"""PhyMLApp keeps its settings and history in the data folder (AppPaths), never in the cwd."""
import json
import os
import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QInputDialog

import phyml_ui.main_window as main_window
from phyml_core import presets
from phyml_core.history import HistoryStore, display_input, new_record
from phyml_core.i18n import _t
from phyml_core.paths import AppPaths
from phyml_core.runner import STAT_KEYS, FileResult, RunResult
from phyml_core.utils import detect_cores


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def log_text(window):
    return window.log_console.toPlainText()


def file_result(path, status='ok', tree='', **stats):
    """A FileResult as PipelineRunner makes it: every stats key present."""
    full = {key: '' for key in STAT_KEYS}
    full.update(stats)
    return FileResult(path, status, tree=tree, stats=full)


def finish_run(window, inputs, *files, config=None):
    """What start_pipeline records about a run, then the history entry for its result."""
    window._run_inputs = list(inputs)
    window._run_config = config if config is not None else window.get_current_config()
    window._append_history(RunResult(list(files), cancelled=False))


def raising(exc):
    def fail(*args, **kwargs):
        raise exc
    return fail


# ---------- where the files go ----------

def test_config_saved_in_data_dir(window, data_dir):
    window.set_combo_by_data(window.cb_model, 'GTR')
    saved = read_json(data_dir / 'phyml_config.json')
    assert saved['model'] == 'GTR'
    assert saved['schema_version'] == 2
    assert not (Path.cwd() / 'phyml_config.json').exists()


def test_window_uses_detected_paths_by_default(window, data_dir):
    assert window.paths.data_dir == str(data_dir)
    assert window.paths.config_file == str(data_dir / 'phyml_config.json')
    assert os.path.samefile(window.paths.app_dir, Path(__file__).resolve().parents[2])


def test_history_written_to_data_dir(window, data_dir):
    finish_run(window, ['x.fasta'], file_result('x.fasta', tree='x.txt'))
    records = HistoryStore(window.paths.history_file).load()
    assert records[0]['ok'] == 1
    assert (data_dir / 'phyml_history.json').is_file()
    assert not (Path.cwd() / 'phyml_history.json').exists()
    assert window.history_list.count() == 1


def test_tool_path_inside_app_dir_saved_relative(data_dir, tmp_path, make_window):
    paths = AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path / 'd'))
    os.makedirs(paths.data_dir)
    os.makedirs(paths.bin_dir)
    exe = os.path.join(paths.bin_dir, 'phyml-mpi.exe')
    sample = os.path.join(paths.app_dir, 'проба 1.fasta')
    Path(sample).write_text('>a\nACGT\n', encoding='utf-8')
    w = make_window(paths)
    w._remember_recent(sample)
    w.phyml_path_input.setText(exe)
    w.auto_save()   # the path holders are not bound to auto-save; the Settings dialog saves
    saved = read_json(paths.config_file)
    assert saved['phyml_path'] == os.path.join('bin', 'phyml-mpi.exe')
    assert saved['recent'] == ['проба 1.fasta']
    assert w.phyml_path_input.text() == exe, 'the field keeps the absolute path'
    w2 = make_window(paths)
    assert w2.phyml_path_input.text() == exe, 'a stored relative path is resolved on load'
    assert w2._recent == [sample]


def test_tool_path_outside_app_dir_stays_absolute(data_dir, tmp_path, make_window):
    paths = AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path / 'd'))
    os.makedirs(paths.data_dir)
    exe = str(tmp_path / 'elsewhere' / 'muscle.exe')
    w = make_window(paths)
    w.muscle_path_input.setText(exe)
    w.auto_save()
    assert read_json(paths.config_file)['muscle_path'] == exe


# ---------- legacy files ----------

def test_legacy_config_migrated_on_first_start(data_dir, make_window):
    legacy = Path.cwd() / 'phyml_config.json'
    legacy.write_text(json.dumps({'model': 'GTR'}), encoding='utf-8')
    w = make_window()
    assert w.cb_model.currentData() == 'GTR'
    expected = _t('settings_migrated').format(str(legacy), str(data_dir / 'phyml_config.json'))
    assert expected in log_text(w)
    assert legacy.is_file(), 'the original stays in place'
    assert read_json(data_dir / 'phyml_config.json')['model'] == 'GTR'


def test_legacy_history_migrated_and_listed(data_dir, make_window):
    record = new_record(inputs=['a.fasta'], engine='phyml', params={}, duration_s=1.0,
                        files=[{'file': 'a.fasta', 'status': 'ok', 'tree': '', 'stats': {}, 'error': ''}])
    (Path.cwd() / 'phyml_history.json').write_text(json.dumps([record]), encoding='utf-8')
    w = make_window()
    assert w.history_list.count() == 1
    assert log_text(w).count(_t('settings_migrated').split('{}')[0]) == 1  # no config to copy


def test_migration_runs_once(data_dir, make_window):
    (Path.cwd() / 'phyml_config.json').write_text('{"model": "GTR"}', encoding='utf-8')
    first = make_window()
    assert _t('settings_migrated').split('{}')[0] in log_text(first)
    second = make_window()
    assert _t('settings_migrated').split('{}')[0] not in log_text(second)


def test_failed_migration_is_logged_and_start_continues(data_dir, make_window, monkeypatch):
    monkeypatch.setattr(main_window.settings, 'migrate_legacy',
                        raising(PermissionError(13, 'copy denied')))
    w = make_window()
    assert 'copy denied' in log_text(w)
    assert _t('err_load').split('{}')[0].strip() in log_text(w)
    assert w.cb_model.currentData() == 'HKY85'


def test_failed_migration_blocks_autosave_and_retries_next_start(data_dir, make_window, monkeypatch):
    """Defaults must not close the migration gate: with no config in data_dir yet, the next
    start has to find the legacy files still to be copied."""
    legacy = Path.cwd() / 'phyml_config.json'
    legacy.write_text(json.dumps({'model': 'GTR'}), encoding='utf-8')
    target = data_dir / 'phyml_config.json'
    with monkeypatch.context() as broken:
        broken.setattr(main_window.settings, 'migrate_legacy',
                       raising(PermissionError(13, 'copy denied')))
        w = make_window()
        assert w.cb_model.currentData() == 'HKY85'
        w.set_combo_by_data(w.cb_model, 'JC69')
        w.auto_save()
        w.close()
    assert not target.exists(), 'defaults were written over the config that was to be migrated'

    second = make_window()
    assert second.cb_model.currentData() == 'GTR'
    assert _t('settings_migrated').format(str(legacy), str(target)) in log_text(second)
    assert read_json(target)['model'] == 'GTR'


def test_failed_migration_keeps_autosave_when_the_config_exists(data_dir, make_window, monkeypatch):
    """The gate is already closed by a real config: nothing to protect, saving goes on."""
    (data_dir / 'phyml_config.json').write_text('{"model": "GTR"}', encoding='utf-8')
    monkeypatch.setattr(main_window.settings, 'migrate_legacy',
                        raising(PermissionError(13, 'copy denied')))
    w = make_window()
    w.set_combo_by_data(w.cb_model, 'JC69')
    assert read_json(data_dir / 'phyml_config.json')['model'] == 'JC69'


# ---------- loading ----------

def test_missing_config_gives_defaults_without_load_message(window):
    assert window.cb_model.currentData() == 'HKY85'
    assert _t('sys_load').strip() not in log_text(window)


def test_existing_config_logs_load_message(data_dir, make_window):
    (data_dir / 'phyml_config.json').write_text(
        json.dumps({'model': 'GTR', 'bootstrap_replicates': '333'}), encoding='utf-8')
    w = make_window()
    assert w.cb_model.currentData() == 'GTR' and w.le_bootstrap_replicates.text() == '333'
    assert _t('sys_load').strip() in log_text(w)
    assert not any(text.endswith('\n') for _, text in w.log_console._entries)


@pytest.mark.parametrize('stored, shown', [('', None), ('3', '3')])
def test_empty_mpi_np_means_physical_cores(data_dir, make_window, stored, shown):
    (data_dir / 'phyml_config.json').write_text(json.dumps({'mpi_np': stored}), encoding='utf-8')
    w = make_window()
    assert w.le_mpi_np.text() == (shown or str(detect_cores()[0]))


def test_bare_mpiexec_is_resolved_through_path(data_dir, make_window, monkeypatch):
    found = str(data_dir / 'bin' / 'mpiexec.exe')
    monkeypatch.setattr(shutil, 'which', lambda name: found if name == 'mpiexec' else None)
    w = make_window()
    assert w.mpirun_path_input.text() == found


def test_bare_mpiexec_kept_when_not_found(data_dir, make_window, monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    w = make_window()
    assert w.mpirun_path_input.text() == 'mpiexec'


def test_damaged_config_reported_and_replaced_by_defaults(data_dir, make_window):
    config = data_dir / 'phyml_config.json'
    config.write_bytes(b'{ not json')
    w = make_window()
    broken = str(config) + '.broken'
    assert _t('err_settings_broken').format(broken) in log_text(w)
    assert Path(broken).read_bytes() == b'{ not json'
    assert w.cb_model.currentData() == 'HKY85'
    w.set_combo_by_data(w.cb_model, 'GTR')
    assert read_json(config)['model'] == 'GTR', 'a damaged file does not stop saving'


def test_unreadable_config_keeps_the_file_and_disables_autosave(data_dir, make_window, monkeypatch):
    config = data_dir / 'phyml_config.json'
    config.write_text('{"model": "GTR"}', encoding='utf-8')
    before = config.read_bytes()
    monkeypatch.setattr(main_window.settings, 'load', raising(PermissionError(13, 'locked')))
    w = make_window()
    assert 'locked' in log_text(w)
    assert _t('err_load').split('{}')[0].strip() in log_text(w)
    assert not any(text.endswith('\n') for _, text in w.log_console._entries)
    w.set_combo_by_data(w.cb_model, 'JC69')
    w.auto_save()
    w.close()
    assert config.read_bytes() == before, 'defaults must never replace the unreadable file'


def test_unknown_settings_survive_a_save(data_dir, make_window):
    config = data_dir / 'phyml_config.json'
    config.write_text(json.dumps({'future_key': {'a': 1}}), encoding='utf-8')
    w = make_window()
    w.set_combo_by_data(w.cb_model, 'GTR')
    saved = read_json(config)
    assert saved['future_key'] == {'a': 1} and saved['model'] == 'GTR'


def test_save_error_is_logged_once_per_failure(window, monkeypatch):
    monkeypatch.setattr(main_window.settings, 'save', raising(OSError('read-only disk')))
    for model in ('GTR', 'JC69', 'K80'):
        window.set_combo_by_data(window.cb_model, model)
    prefix = _t('err_settings_save').split('{}')[0]
    assert log_text(window).count('read-only disk') == 1
    assert prefix in log_text(window)


# ---------- history ----------

def test_history_record_holds_params_and_full_file_paths(window, tmp_path):
    folder = tmp_path / 'run folder'
    files = [str(folder / 'a.fasta'), str(folder / 'б.fasta')]
    trees = [str(folder / 'a.phy_phyml_tree.txt'), '']
    window.set_combo_by_data(window.cb_model, 'GTR')
    finish_run(window, [str(folder)],
               file_result(files[0], 'ok', trees[0], model='GTR', taxa='8', lnL='-123.4',
                           gamma='0.5', tstv='2.1', time='3s'),
               file_result(files[1], 'fail'))

    rec = HistoryStore(window.paths.history_file).load()[0]
    assert rec['inputs'] == [str(folder)]
    assert rec['engine'] == 'phyml'
    assert (rec['ok'], rec['n']) == (1, 2)
    assert rec['params']['model'] == 'GTR'
    for key in ('presets', 'recent', 'window'):
        assert key not in rec['params']
    assert [e['file'] for e in rec['files']] == files
    assert [e['status'] for e in rec['files']] == ['ok', 'fail']
    assert rec['files'][0]['tree'] == trees[0]
    assert rec['files'][0]['stats'] == {'model': 'GTR', 'taxa': '8', 'lnL': '-123.4',
                                        'gamma': '0.5', 'tstv': '2.1', 'time': '3s'}
    assert 'error' in rec['files'][0]
    assert isinstance(rec['duration_s'], float)
    assert window.history_list.item(0).text() == _t('hist_entry').format(
        rec['ts'], 'run folder/', 1, 2)


def test_history_params_come_from_the_run_config(window):
    """A change made to the form while the run was going must not rewrite what was run."""
    window.set_combo_by_data(window.cb_model, 'GTR')
    config = window.get_current_config()
    window.set_combo_by_data(window.cb_model, 'JC69')
    finish_run(window, ['x.fasta'], file_result('x.fasta'), config=config)
    assert HistoryStore(window.paths.history_file).load()[0]['params']['model'] == 'GTR'


def test_single_file_run_is_listed_by_its_name(window, tmp_path):
    fasta = str(tmp_path / 'one.fasta')
    finish_run(window, [fasta], file_result(fasta, tree='t.txt'))
    rec = HistoryStore(window.paths.history_file).load()[0]
    assert display_input(rec) == 'one.fasta'
    assert window.history_list.item(0).text() == _t('hist_entry').format(rec['ts'], 'one.fasta', 1, 1)


def test_history_list_shows_old_and_new_records_and_opens_the_best_tree(window, tmp_path, monkeypatch):
    tree = tmp_path / 'best.txt'
    tree.write_text('(a,b);', encoding='utf-8')
    store = HistoryStore(window.paths.history_file)
    store.append({'ts': '2020-01-01 10:00', 'input': 'old.fasta', 'ok': 2, 'n': 3, 'time': '5s',
                  'model': 'HKY85', 'engine': 'phyml', 'tree': str(tmp_path / 'gone.txt')})
    store.append(new_record(
        inputs=[str(tmp_path / 'batch')], engine='phyml', params={}, duration_s=2.0,
        files=[{'file': str(tmp_path / 'batch' / 'a.fasta'), 'status': 'fail', 'tree': '',
                'stats': {}, 'error': ''},
               {'file': str(tmp_path / 'batch' / 'b.fasta'), 'status': 'ok', 'tree': str(tree),
                'stats': {}, 'error': ''}]))
    window._refresh_history()
    assert window.history_list.count() == 2
    new_item, old_item = window.history_list.item(0), window.history_list.item(1)
    assert new_item.text().split(' | ')[1] == 'batch/'
    assert old_item.text() == _t('hist_entry').format('2020-01-01 10:00', 'old.fasta', 2, 3)

    shown = []
    monkeypatch.setattr(window.tree_view, 'load_tree', shown.append)
    window._open_history_entry(new_item)
    assert shown == [str(tree)]
    window._open_history_entry(old_item)
    assert shown == [str(tree)], 'a vanished tree is not loaded'
    assert _t('hist_no_tree') in log_text(window)


def test_history_write_error_is_logged_without_crash(window, monkeypatch):
    monkeypatch.setattr(HistoryStore, 'append', raising(OSError('disk full')))
    finish_run(window, ['x.fasta'], file_result('x.fasta'))
    assert 'disk full' in log_text(window)
    assert _t('err_settings_save').split('{}')[0] in log_text(window)


def test_unreadable_history_is_logged_without_crash(data_dir, make_window, monkeypatch):
    monkeypatch.setattr(HistoryStore, 'load', raising(PermissionError(13, 'history locked')))
    w = make_window()
    assert 'history locked' in log_text(w)
    assert w.history_list.count() == 0
    finish_run(w, ['x.fasta'], file_result('x.fasta'))   # must not raise either
    assert not (data_dir / 'phyml_history.json').exists()


# ---------- presets ----------

def preset_item(window, label_key):
    for i in range(window.presets_list.count()):
        item = window.presets_list.item(i)
        if item.data(main_window.Qt.UserRole) == ('builtin', label_key):
            return item
    raise AssertionError(label_key)


def test_builtin_preset_switches_the_engine(window):
    window.engine_setting = 'iqtree'
    window.update_models()
    window._preset_activated(preset_item(window, 'preset_builtin_pub'))
    assert window.engine_setting == 'phyml'
    assert window.cb_model.currentData() == 'GTR'
    assert window.cb_search.currentData() == 'BEST'
    assert read_json(window.paths.config_file)['engine'] == 'phyml'


def test_user_preset_without_engine_keeps_the_current_one(window):
    window.engine_setting = 'iqtree'
    window.update_models()
    window._user_presets['old'] = {'datatype': 'nt', 'model': 'HKY+F+G4', 'search': 'SPR'}
    window._refresh_presets()
    item = next(window.presets_list.item(i) for i in range(window.presets_list.count())
                if window.presets_list.item(i).text() == 'old')
    window._preset_activated(item)
    assert window.engine_setting == 'iqtree'
    assert window.cb_model.currentData() == 'HKY+F+G4' and window.cb_search.currentData() == 'SPR'


def test_saved_user_preset_holds_the_engine_and_is_persisted(window, monkeypatch):
    monkeypatch.setattr(QInputDialog, 'getText', staticmethod(lambda *a, **k: ('mine', True)))
    window.set_combo_by_data(window.cb_model, 'GTR')
    window._save_preset()
    expected = presets.extract(window.get_current_config())
    assert window._user_presets['mine'] == expected
    assert expected['engine'] == 'phyml'
    assert read_json(window.paths.config_file)['presets']['mine'] == expected
