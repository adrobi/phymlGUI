"""GUI behaviour of PhyMLApp that needs no analysis binaries."""
import pytest
from PySide6.QtWidgets import QSizePolicy

import phyml_ui.main_window as main_window
from phyml_core.engines.base import Issue, format_issue
from phyml_core.history import HistoryStore
from phyml_core.i18n import _t
from phyml_core.report import CSV_NAME
from phyml_core.utils import detect_cores
from phyml_ui.main_window import SettingsDialog
from phyml_ui.themes import build_qss, resolve
from unit.fakes import FakeEngine

ALIGNED = '>A\nACGTACGTAC\n>B\nACGTACGAAC\n>C\nACGAACGTAC\n'
FAIL_MARK, OK_MARK = '✗', '✓'


@pytest.fixture
def restore_stylesheet(qapp):
    original = qapp.styleSheet()
    yield
    qapp.setStyleSheet(original)


def test_defaults_match_detected_cores(window):
    """np defaults to the physical core count; the status bar shows the core info."""
    phys, logi = detect_cores()
    assert window.le_mpi_np.text() == str(window.phys_cores), window.le_mpi_np.text()
    assert (window.phys_cores, window.logi_cores) == (phys, logi)
    assert str(phys) in window.cores_label.text() and str(logi) in window.cores_label.text()


def test_mpi_binary_autodetect(window, tmp_path):
    window.chk_use_mpi.setChecked(False)
    window.phyml_path_input.setText(str(tmp_path / 'phyml.exe'))
    assert not window.chk_use_mpi.isChecked(), 'plain phyml.exe must not enable MPI'
    window.phyml_path_input.setText(str(tmp_path / 'phyml-mpi.exe'))
    assert window.chk_use_mpi.isChecked(), 'phyml-mpi.exe must auto-enable MPI'
    log_text = window.log_console.toPlainText()
    assert 'MPI' in log_text, 'detection message missing from log'


def test_serial_bootstrap_on_mpi_build_blocked(window, warned, tmp_path):
    """MPI binary + MPI off + bootstrap -> blocked with a warning (from PhyML.validate,
    which reaches this check only for a binary that exists)."""
    exe = tmp_path / 'phyml-mpi.exe'
    exe.write_bytes(b'')
    window.phyml_path_input.setText(str(exe))
    window.chk_use_mpi.setChecked(False)  # after the path: the path edit auto-enables MPI
    window.set_combo_by_data(window.cb_support_method, 'bootstrap')
    fasta = tmp_path / 'test_unaligned.fasta'
    fasta.write_text('>a\nACGT\n>b\nACGA\n')
    window.fasta_file = str(fasta)
    window.start_pipeline()
    assert warned, 'warning box must be shown'
    assert warned[0][1] == _t('err_box_title')
    assert _t('mpi_boot_msg') in warned[0][2], 'blocked for the wrong reason'
    assert window.btn_run.isEnabled(), 'Run must stay enabled after blocked start'
    assert window.worker is None or not window.worker.isRunning()


def test_theme_tabs_presets_log_filter_recent(window, qapp, tmp_path, restore_stylesheet):
    """New UI: themes, results tabs, structured log, recent list, cpu timer."""
    window.apply_theme('dark', 'blue')
    theme, accent = resolve('dark', 'blue')
    assert theme == 'dark' and accent == '#2D7DD2'
    assert qapp.styleSheet() == build_qss(theme, accent)
    assert window.log_console._role_colors['out'] == '#E6E8EB', 'phyml output must be themed'
    assert window.log_console._role_colors['system'] == '#2D7DD2', 'system lines use accent'
    assert window.cpu_timer.isActive(), 'CPU monitor timer must be running'
    window.apply_theme('system', 'system')
    assert window.result_tabs.count() == 4, 'expected 4 result tabs (log/stats/summary/queue)'

    # presets: built-ins listed, apply changes support method, user preset saves
    assert window.presets_list.count() >= 3
    texts = [window.presets_list.item(i).text() for i in range(window.presets_list.count())]
    screen_row = next(i for i, t in enumerate(texts)
                      if 'скрининг' in t.lower() or 'screening' in t.lower())
    window._preset_activated(window.presets_list.item(screen_row))
    assert window.cb_support_method.currentData() == '-4', 'screening preset must select aLRT'
    window._user_presets['my-test'] = {k: window.get_current_config()[k] for k in ('model',)}
    window._refresh_presets()
    assert any(window.presets_list.item(i).text() == 'my-test'
               for i in range(window.presets_list.count()))

    # tree viewer zoom / pan mode buttons
    window.tree_view.btn_zoom.click()
    assert (window.tree_view.btn_zoom.isChecked()
            and window.tree_view.mode_label.text() == _t('tree_zoom'))
    window.tree_view.btn_pan.click()
    assert window.tree_view.btn_pan.isChecked() and not window.tree_view.btn_zoom.isChecked()
    window.tree_view.btn_pan.click()
    assert not window.tree_view.btn_pan.isChecked()

    # settings dialog: a path edit is applied and re-triggers the MPI autodetect
    d = SettingsDialog(window, window)
    assert d.edits[0].text() == window.phyml_path_input.text()
    mpi_path = str(tmp_path / 'some' / 'phyml-mpi.exe')
    d.edits[0].setText(mpi_path)
    d.accept()
    assert window.phyml_path_input.text() == mpi_path
    assert window.chk_use_mpi.isChecked(), 'settings edit must re-trigger MPI autodetect'

    # structured log: filter by role
    window.log_console.filter_box.setCurrentIndex(0)
    window.log_console.clear()
    window.log_console.append('error', '[ERROR] test failure line')
    window.log_console.append('out', 'plain phyml output line')
    assert '[ERROR] test failure line' in window.log_console.toPlainText()
    assert 'plain phyml output line' in window.log_console.toPlainText()
    window.set_combo_by_data(window.log_console.filter_box, 'error')
    assert '[ERROR]' in window.log_console.view.toPlainText()
    assert 'plain phyml output line' not in window.log_console.view.toPlainText()
    window.set_combo_by_data(window.log_console.filter_box, 'all')
    assert 'plain phyml output line' in window.log_console.view.toPlainText()

    # recent list: most recent first, no duplicates
    window._remember_recent('X:/a.fasta')
    window._remember_recent('X:/b.fasta')
    window._remember_recent('X:/a.fasta')
    assert window.recent_list.count() == 2 and window._recent[0] == 'X:/a.fasta'


def test_cpu_bar_expands(window):
    """The CPU bar fills the free status bar space."""
    assert window.cpu_sys_bar.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


def test_empty_folder_blocked(window, warned, tmp_path):
    empty_dir = tmp_path / 't8_empty_dir'
    empty_dir.mkdir()
    window.fasta_path_input.setText(str(empty_dir))
    window.start_pipeline()
    assert warned, 'empty folder must trigger a warning'
    assert warned[0][2] == _t('batch_empty'), 'blocked for the wrong reason'
    assert window.worker is None or not window.worker.isRunning()


@pytest.mark.parametrize('engine', ['phyml', 'iqtree'])
@pytest.mark.parametrize('datatype', ['nt', 'aa'])
def test_model_combo_lists_the_models_of_the_engine(window, engine, datatype):
    """The model list comes from the engine registry (data and text both)."""
    from phyml_core.engines import ENGINES
    window.engine_setting = engine
    window.set_combo_by_data(window.cb_datatype, datatype)
    window.update_models()
    shown = [(window.cb_model.itemText(i), window.cb_model.itemData(i)) for i in range(window.cb_model.count())]
    expected = ENGINES[engine].models(datatype)
    assert shown == [(m, m) for m in expected]
    assert window.cb_model.currentData() == expected[0]


def test_unknown_engine_in_the_settings_shows_the_phyml_models(window):
    from phyml_core.engines import ENGINES
    window.engine_setting = 'no-such-engine'
    window.update_models()
    assert [window.cb_model.itemData(i) for i in range(window.cb_model.count())] == ENGINES['phyml'].models('nt')


def test_fasta_info_label_summarizes_the_alignment(window, tmp_path):
    fasta = tmp_path / 'выравнивание 1.fasta'
    fasta.write_text('>A\nACGT--\n>B\nAC\n>C\nACGTA\n', encoding='utf-8')
    window.fasta_path_input.setText(str(fasta))
    assert window.fasta_info_label.text() == _t('fasta_info').format(3, 2, 6, 15.4)


def test_fasta_info_label_is_blank_for_an_empty_file_and_counts_a_folder(window, tmp_path):
    empty = tmp_path / 'empty.fasta'
    empty.write_text('')
    window.fasta_path_input.setText(str(empty))
    assert window.fasta_info_label.text() == ' '
    window.fasta_path_input.setText(str(tmp_path))
    assert window.fasta_info_label.text() == _t('fasta_info').format(1, '—', '—', '—')


# ---------- runs through PipelineRunner (FakeEngine, no binaries) ----------

def use_fake_engine(window, monkeypatch, **params):
    """Give the window a registry holding only FakeEngine; params go into every run config."""
    window.engines = {'fake': FakeEngine()}
    window.engine_setting = 'fake'
    window.update_models()
    original = window.get_current_config
    monkeypatch.setattr(window, 'get_current_config', lambda: {**original(), **params})


def write_fasta(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ALIGNED, encoding='utf-8')
    return str(path)


def run_to_end(window, qtbot, files=None):
    window.start_pipeline(files)
    assert window.worker is not None, 'the run did not start'
    qtbot.waitUntil(lambda: window.btn_run.isEnabled(), timeout=15000)
    window.worker.wait()


def queue_markers(window):
    return [window.queue_list.item(i).text().split('  ')[-1]
            for i in range(window.queue_list.count())]


def test_window_recovers_after_engine_exception(window, qtbot, data_dir, tmp_path,
                                                monkeypatch, warned):
    use_fake_engine(window, monkeypatch, fake_mode='raise')
    fasta = write_fasta(tmp_path / 'in' / 'a.fasta')
    window.fasta_path_input.setText(fasta)
    run_to_end(window, qtbot)
    assert not warned
    assert window.btn_run.isEnabled() and not window.btn_cancel.isEnabled()
    assert 'boom' in window.log_console.toPlainText()
    assert any(level == 'error' and 'boom' in text for level, text in window.log_console._entries)
    assert queue_markers(window) == [FAIL_MARK]
    assert window._failed_files == [fasta]
    assert not window.retry_btn.isHidden()
    rec = HistoryStore(window.paths.history_file).load()[0]
    assert (rec['ok'], rec['n']) == (0, 1)
    assert rec['files'][0]['status'] == 'fail' and 'boom' in rec['files'][0]['error']


def test_successful_run_fills_results_history_and_tree(window, qtbot, tmp_path, monkeypatch,
                                                       warned):
    use_fake_engine(window, monkeypatch, fake_mode='ok')
    fasta = write_fasta(tmp_path / 'in' / 'a.fasta')
    window.fasta_path_input.setText(fasta)
    loaded = []
    monkeypatch.setattr(window.tree_view, 'load_tree', loaded.append)
    run_to_end(window, qtbot)
    result = window.last_result
    assert result.success, window.log_console.toPlainText()
    tree = result.files[0].tree
    assert loaded == [tree]
    assert window.stats_file_label.text().endswith('a.fasta')
    assert window.stats_table.item(0, 1).text() == 'FAKE'
    assert window.summary_table.rowCount() == 1
    assert window.summary_table.item(0, 0).text() == 'a.fasta'
    assert window.summary_table.item(0, 1).text() == 'OK'
    csv_path = tmp_path / 'in' / CSV_NAME
    assert csv_path.is_file()
    assert _t('summary_saved').format(str(csv_path)) in window.log_console.toPlainText()
    assert window.retry_btn.isHidden() and window._failed_files == []
    assert window.open_dir_btn.isEnabled()
    rec = HistoryStore(window.paths.history_file).load()[0]
    assert rec['engine'] == 'fake' and rec['inputs'] == [fasta]
    assert rec['files'][0]['file'] == fasta and rec['files'][0]['tree'] == tree
    assert rec['params']['fake_mode'] == 'ok'
    for key in ('presets', 'recent', 'window'):
        assert key not in rec['params']


def test_tree_not_loaded_when_show_tree_is_off(window, qtbot, tmp_path, monkeypatch):
    use_fake_engine(window, monkeypatch, fake_mode='ok')
    window.fasta_path_input.setText(write_fasta(tmp_path / 'a.fasta'))
    window.chk_show_tree.setChecked(False)
    loaded = []
    monkeypatch.setattr(window.tree_view, 'load_tree', loaded.append)
    run_to_end(window, qtbot)
    assert window.last_result.success and loaded == []


def test_batch_with_a_failure_offers_retry_of_the_failed_file(window, qtbot, tmp_path,
                                                             monkeypatch):
    folder = tmp_path / 'batch'
    good = write_fasta(folder / 'good.fasta')
    bad = write_fasta(folder / 'bad.fasta')
    use_fake_engine(window, monkeypatch, fake_mode={'bad': 'exit3'})
    window.fasta_path_input.setText(str(folder))
    loaded = []
    monkeypatch.setattr(window.tree_view, 'load_tree', loaded.append)
    run_to_end(window, qtbot)
    assert [f.file for f in window.last_result.files] == [bad, good]
    assert queue_markers(window) == [FAIL_MARK, OK_MARK]
    assert window._failed_files == [bad]
    assert not window.retry_btn.isHidden()
    assert loaded == [], 'a batch with a failure shows no tree'
    rec = HistoryStore(window.paths.history_file).load()[0]
    assert rec['inputs'] == [str(folder)] and (rec['ok'], rec['n']) == (1, 2)
    assert window.summary_table.rowCount() == 2

    window._retry_failed()
    qtbot.waitUntil(lambda: window.btn_run.isEnabled(), timeout=15000)
    window.worker.wait()
    assert [f.file for f in window.last_result.files] == [bad]


def test_cancel_from_the_window_marks_the_file_cancelled(window, qtbot, tmp_path, monkeypatch):
    use_fake_engine(window, monkeypatch, fake_mode='hang')
    window.fasta_path_input.setText(write_fasta(tmp_path / 'a.fasta'))
    window.start_pipeline()
    qtbot.waitUntil(lambda: window.worker.active_pid is not None, timeout=10000)
    window.cancel_pipeline()
    assert not window.btn_cancel.isEnabled()
    qtbot.waitUntil(lambda: window.btn_run.isEnabled(), timeout=15000)
    window.worker.wait()
    assert window.last_result.cancelled
    assert window.last_result.files[0].status == 'cancelled'
    assert window._failed_files == [] and window.retry_btn.isHidden()
    assert _t('sys_interrupt').strip() in window.log_console.toPlainText()


def test_summary_write_error_is_logged(window, qtbot, tmp_path, monkeypatch):
    use_fake_engine(window, monkeypatch, fake_mode='ok')
    window.fasta_path_input.setText(write_fasta(tmp_path / 'a.fasta'))
    window.chk_show_tree.setChecked(False)

    def broken(rows, out_dir):
        raise ValueError('xlsx exploded')
    monkeypatch.setattr(main_window.report, 'write_summary', broken)
    run_to_end(window, qtbot)
    assert _t('err_summary_save').format('xlsx exploded') in window.log_console.toPlainText()
    assert window.btn_run.isEnabled()


def test_prerun_validation_lists_all_errors(window, data_dir, tmp_path, warned):
    window.engine_setting = 'phyml'
    window.update_models()
    window.fasta_path_input.setText(write_fasta(tmp_path / 'a.fasta'))
    window.le_tstv.setText('abc')
    window.le_classes.setText('x')
    window.start_pipeline()
    assert len(warned) == 1
    _, title, text = warned[0][:3]
    assert title == _t('err_box_title')
    lines = text.split('\n')
    assert format_issue(Issue('error', 'val_not_number', ('tstv', 'abc'))) in lines
    assert format_issue(Issue('error', 'val_not_number', ('classes', 'x'))) in lines
    assert window.worker is None and window.btn_run.isEnabled()
