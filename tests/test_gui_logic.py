"""GUI logic tests for the new MPI/core/CPU-monitoring features."""
import os, sys, json, time, shutil

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import phymlgui
from PySide6.QtWidgets import QMessageBox

# 1. locales.json: valid JSON, all new keys present in both languages
BIN_ROOT = ROOT
PHYML_OK = all(os.path.exists(p) for p in (
    os.path.join(BIN_ROOT, 'phymlgui v1.1', 'phyml-mpi.exe'),
    os.path.join(BIN_ROOT, 'tools', 'muscle.exe'),
    r'C:\Program Files\Microsoft MPI\Bin\mpiexec.exe'))

loc = json.load(open('locales.json', encoding='utf-8'))
new_keys = ['cores_info', 'cpu_sys', 'cpu_analysis', 'cpu_analysis_idle',
            'cpu_analysis_done', 'mpi_detected', 'mpi_boot_title', 'mpi_boot_msg']
for lang in ('en', 'ru'):
    for k in new_keys:
        assert k in loc[lang], f'{lang} missing {k}'
print('PASS locales: new keys present in en+ru')

app = phymlgui.QApplication([])

# keep existing config out of the way to test defaults
had_config = os.path.exists(phymlgui.CONFIG_FILE)
if had_config:
    shutil.move(phymlgui.CONFIG_FILE, phymlgui.CONFIG_FILE + '.bak')

try:
    w = phymlgui.PhyMLApp()

    # 2. np default == physical cores; status bar shows core info
    assert w.le_mpi_np.text() == str(w.phys_cores), w.le_mpi_np.text()
    assert w.phys_cores == 8 and w.logi_cores == 16, (w.phys_cores, w.logi_cores)
    assert '8' in w.cores_label.text() and '16' in w.cores_label.text()
    print(f'PASS defaults: np={w.le_mpi_np.text()}, cores label: {w.cores_label.text()!r}')

    # 3. MPI binary autodetection
    w.chk_use_mpi.setChecked(False)
    w.phyml_path_input.setText(r'D:\tools\phyml.exe')
    assert not w.chk_use_mpi.isChecked(), 'plain phyml.exe must not enable MPI'
    w.phyml_path_input.setText(r'D:\phyml\phymlgui v1.1\phyml-mpi.exe')
    assert w.chk_use_mpi.isChecked(), 'phyml-mpi.exe must auto-enable MPI'
    log_text = w.log_console.toPlainText()
    assert 'MPI' in log_text, 'detection message missing from log'
    print('PASS mpi autodetect: checkbox auto-enabled + logged')

    # 4. validation: MPI binary + MPI off + bootstrap -> blocked with warning
    w.chk_use_mpi.setChecked(False)
    w.set_combo_by_data(w.cb_support_method, 'bootstrap')
    w.fasta_file = os.path.join('testrun', 'test_unaligned.fasta')
    warned = []
    phymlgui.QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a) or QMessageBox.Ok)
    w.start_pipeline()
    assert warned, 'warning box must be shown'
    assert w.btn_run.isEnabled(), 'Run must stay enabled after blocked start'
    assert w.worker is None or not w.worker.isRunning()
    print('PASS validation: serial bootstrap on MPI build blocked with warning')

    # 5. CPU monitor during a real MPI run
    run_dir = os.path.join('testrun', 't6_monitor')
    shutil.rmtree(run_dir, ignore_errors=True)
    os.makedirs(run_dir, exist_ok=True)
    shutil.copy(w.fasta_file, run_dir)
    fasta = os.path.join(run_dir, 'test_unaligned.fasta')

    config = {
        'phyml_path': os.path.join(ROOT, 'phymlgui v1.1', 'phyml-mpi.exe'),
        'muscle_path': os.path.join(ROOT, 'tools', 'muscle.exe'),
        'mpirun_path': r'C:\Program Files\Microsoft MPI\Bin\mpiexec.exe',
        'mpi_np': '2', 'use_mpi': True, 'datatype': 'nt', 'model': 'HKY85',
        'support_method': 'bootstrap', 'bootstrap_replicates': '20',
        'freq': 'default', 'tstv': 'e', 'pinv': '0.0', 'classes': '4',
        'gamma': 'e', 'search': 'NNI', 'optimize': 'tlr', 'parsimony': False,
    }
    os.chdir(run_dir)
    fasta = os.path.abspath('test_unaligned.fasta')
    w._cpu_samples = []
    worker = phymlgui.PipelineWorker(config, fasta)
    w.worker = worker
    done, wlogs = [], []
    worker.log_signal.connect(wlogs.append)
    worker.finished_signal.connect(lambda ok, tree: done.append((ok, tree)))
    worker.start()
    ticks = 0
    while not done and ticks < 300:
        app.processEvents()
        time.sleep(0.3)
        w.update_cpu_status()
        ticks += 1
    os.chdir(ROOT)
    assert done, 'worker did not finish'
    assert done[0][0], 'pipeline failed:\n' + '\n'.join(wlogs[-10:])
    assert w._cpu_samples, 'no CPU samples collected'
    peak = max(w._cpu_samples)
    assert peak > 50, f'analysis CPU unexpectedly low: peak {peak}'
    print(f'PASS cpu monitor: {len(w._cpu_samples)} samples, peak {peak:.0f}% '
          f'(~{peak/100:.1f} cores), final label: {w.cpu_run_label.text()!r}')

    # 6. new UI: themes, results tabs, structured log, recent list, cpu timer
    from phyml_ui.themes import resolve, build_qss
    w.apply_theme('dark', 'blue')
    theme, accent = resolve('dark', 'blue')
    assert theme == 'dark' and accent == '#2D7DD2'
    assert app.styleSheet() == build_qss(theme, accent)
    assert w.log_console._role_colors['out'] == '#E6E8EB', 'phyml output must be themed'
    assert w.log_console._role_colors['system'] == '#2D7DD2', 'system lines use accent'
    assert w.cpu_timer.isActive(), 'CPU monitor timer must be running'
    w.apply_theme('system', 'system')
    assert w.result_tabs.count() == 4, 'expected 4 result tabs (log/stats/summary/queue)'
    # presets: built-ins listed, apply changes support method, user preset saves
    assert w.presets_list.count() >= 3
    texts = [w.presets_list.item(i).text() for i in range(w.presets_list.count())]
    screen_row = next(i for i, t in enumerate(texts) if 'скрининг' in t.lower() or 'screening' in t.lower())
    w._preset_activated(w.presets_list.item(screen_row))
    assert w.cb_support_method.currentData() == '-4', 'screening preset must select aLRT'
    w._user_presets['my-test'] = {k: w.get_current_config()[k] for k in ('model',)}
    w._refresh_presets()
    assert any(w.presets_list.item(i).text() == 'my-test' for i in range(w.presets_list.count()))
    w.tree_view.btn_zoom.click()
    assert w.tree_view.btn_zoom.isChecked() and w.tree_view.mode_label.text() == phymlgui._t('tree_zoom')
    w.tree_view.btn_pan.click()
    assert w.tree_view.btn_pan.isChecked() and not w.tree_view.btn_zoom.isChecked()
    w.tree_view.btn_pan.click()
    assert not w.tree_view.btn_pan.isChecked()
    from phyml_ui.main_window import SettingsDialog
    d = SettingsDialog(w, w)
    assert d.edits[0].text() == w.phyml_path_input.text()
    d.edits[0].setText('D:/some/phyml-mpi.exe')
    d.accept()
    assert w.phyml_path_input.text() == 'D:/some/phyml-mpi.exe'
    assert w.chk_use_mpi.isChecked(), 'settings edit must re-trigger MPI autodetect'
    w.log_console.filter_box.setCurrentIndex(0)
    w.log_console.clear()
    w.log_console.append('[ERROR] test failure line')
    w.log_console.append('plain phyml output line')
    assert '[ERROR] test failure line' in w.log_console.toPlainText()
    assert 'plain phyml output line' in w.log_console.toPlainText()
    w.set_combo_by_data(w.log_console.filter_box, 'error')
    assert '[ERROR]' in w.log_console.view.toPlainText()
    assert 'plain phyml output line' not in w.log_console.view.toPlainText()
    w.set_combo_by_data(w.log_console.filter_box, 'all')
    assert 'plain phyml output line' in w.log_console.view.toPlainText()
    w._remember_recent('X:/a.fasta'); w._remember_recent('X:/b.fasta')
    w._remember_recent('X:/a.fasta')
    assert w.recent_list.count() == 2 and w._recent[0] == 'X:/a.fasta'
    print('PASS new UI: theme toggle, 4 result tabs, log filter, recent list')
    print('ALL GUI LOGIC TESTS PASSED')
finally:
    if had_config:
        shutil.move(phymlgui.CONFIG_FILE + '.bak', phymlgui.CONFIG_FILE)
