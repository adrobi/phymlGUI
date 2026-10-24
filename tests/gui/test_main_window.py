"""GUI behaviour of PhyMLApp that needs no analysis binaries."""
import pytest
from PySide6.QtWidgets import QMessageBox, QSizePolicy

from phyml_core.i18n import _t
from phyml_core.utils import detect_cores
from phyml_ui.main_window import PhyMLApp, SettingsDialog
from phyml_ui.themes import build_qss, resolve


@pytest.fixture
def window(isolated_config, qtbot):
    # isolated_config goes first so it is torn down last: qtbot closes the
    # window at teardown and closeEvent still writes the (patched) config file
    w = PhyMLApp()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def warned(monkeypatch):
    """Replace QMessageBox.warning; the list collects the (parent, title, text) calls."""
    shown = []
    monkeypatch.setattr(QMessageBox, 'warning',
                        staticmethod(lambda *a, **k: shown.append(a) or QMessageBox.Ok))
    return shown


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
    """MPI binary + MPI off + bootstrap -> blocked with a warning."""
    window.phyml_path_input.setText(str(tmp_path / 'phyml-mpi.exe'))
    window.chk_use_mpi.setChecked(False)  # after the path: the path edit auto-enables MPI
    window.set_combo_by_data(window.cb_support_method, 'bootstrap')
    fasta = tmp_path / 'test_unaligned.fasta'
    fasta.write_text('>a\nACGT\n>b\nACGA\n')
    window.fasta_file = str(fasta)
    window.start_pipeline()
    assert warned, 'warning box must be shown'
    assert warned[0][1] == _t('mpi_boot_title'), 'blocked for the wrong reason'
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
    window.log_console.append('[ERROR] test failure line')
    window.log_console.append('plain phyml output line')
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
