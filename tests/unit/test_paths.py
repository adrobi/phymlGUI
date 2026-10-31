import os
import subprocess
import sys

from conftest import ROOT

from phyml_core.paths import CONFIG_NAME, HISTORY_NAME, AppPaths, default_app_dir


def test_file_names():
    assert CONFIG_NAME == 'phyml_config.json'
    assert HISTORY_NAME == 'phyml_history.json'


def test_default_app_dir_is_repo_root_from_sources(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    assert os.path.samefile(default_app_dir(), ROOT)


def test_default_app_dir_is_exe_folder_when_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'phymlgui.exe'))
    assert default_app_dir() == str(tmp_path)


def test_detect_uses_env_override(tmp_path):
    p = AppPaths.detect(env={'PHYMLGUI_DATA_DIR': str(tmp_path / 'd')}, app_dir=str(tmp_path))
    assert p.data_dir == str(tmp_path / 'd') and os.path.isdir(p.data_dir)


def test_detect_prefers_writable_app_dir(tmp_path):
    p = AppPaths.detect(env={}, is_writable=lambda d: True, app_dir=str(tmp_path))
    assert p.data_dir == str(tmp_path)


def test_detect_falls_back_to_appdata(tmp_path):
    p = AppPaths.detect(env={'APPDATA': str(tmp_path / 'ad')}, is_writable=lambda d: False,
                        app_dir=str(tmp_path / 'app'), platform='nt')
    assert p.data_dir == str(tmp_path / 'ad' / 'phymlGUI') and os.path.isdir(p.data_dir)


def test_detect_default_probe_creates_and_removes_temp_file(tmp_path):
    # the default is_writable probe must pick a writable app_dir and leave no trace in it
    p = AppPaths.detect(env={}, app_dir=str(tmp_path))
    assert p.data_dir == str(tmp_path)
    assert os.listdir(tmp_path) == []


def test_detect_default_probe_rejects_missing_dir(tmp_path):
    missing = tmp_path / 'no-such-app'
    p = AppPaths.detect(env={'APPDATA': str(tmp_path / 'ad')}, app_dir=str(missing), platform='nt')
    assert p.data_dir == str(tmp_path / 'ad' / 'phymlGUI')
    assert not missing.exists()


def test_detect_uses_cyrillic_and_spaces(tmp_path):
    base = tmp_path / 'Мои данные' / 'проект 1'
    p = AppPaths.detect(env={'PHYMLGUI_DATA_DIR': str(base)}, app_dir=str(tmp_path))
    assert os.path.isdir(base) and p.data_dir == str(base)
    assert p.config_file == os.path.join(str(base), 'phyml_config.json')
    assert p.history_file == os.path.join(str(base), 'phyml_history.json')


def test_derived_locations(tmp_path):
    p = AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path / 'data'))
    assert p.bin_dir == os.path.join(str(tmp_path / 'app'), 'bin')
    assert p.config_file == os.path.join(str(tmp_path / 'data'), CONFIG_NAME)
    assert p.history_file == os.path.join(str(tmp_path / 'data'), HISTORY_NAME)


def test_to_stored_roundtrip_cyrillic(tmp_path):
    app = tmp_path / 'Мои программы' / 'phymlGUI'
    p = AppPaths(app_dir=str(app), data_dir=str(app))
    inside = str(app / 'bin' / 'muscle.exe')
    assert p.to_stored(inside) == os.path.join('bin', 'muscle.exe')
    assert p.from_stored(p.to_stored(inside)) == inside
    outside = str(tmp_path / 'данные' / 'a.fasta')
    assert p.to_stored(outside) == outside and p.to_stored('') == ''


def test_to_stored_ignores_prefix_lookalike_and_case(tmp_path):
    app = tmp_path / 'phymlGUI'
    p = AppPaths(app_dir=str(app), data_dir=str(app))
    lookalike = str(tmp_path / 'phymlGUI-old' / 'muscle.exe')
    assert p.to_stored(lookalike) == lookalike          # shares a string prefix, not a folder
    if os.name == 'nt':                                  # Windows paths compare case-insensitively
        assert p.to_stored(str(app).upper() + '\\bin\\x.exe') == os.path.join('bin', 'x.exe')


def test_to_stored_keeps_relative_input_untouched(tmp_path):
    # a bare command name (the default mpirun_path) must not be turned into a cwd-based path
    p = AppPaths(app_dir=str(tmp_path), data_dir=str(tmp_path))
    assert p.to_stored('mpiexec') == 'mpiexec'


def test_from_stored_absolute_and_empty_unchanged(tmp_path):
    p = AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path))
    absolute = str(tmp_path / 'elsewhere' / 'x.exe')
    assert p.from_stored(absolute) == absolute and p.from_stored('') == ''
    assert p.from_stored('bin/x.exe') == os.path.join(str(tmp_path / 'app'), 'bin/x.exe')


def test_find_tool_prefers_stored_then_bin(tmp_path):
    app = tmp_path / 'app'
    (app / 'bin').mkdir(parents=True)
    p = AppPaths(app_dir=str(app), data_dir=str(app))
    configured = tmp_path / 'custom' / 'muscle.exe'
    configured.parent.mkdir()
    configured.write_bytes(b'')
    bundled = app / 'bin' / 'muscle.exe'
    bundled.write_bytes(b'')
    # the configured file exists -> it wins over bin/
    assert p.find_tool(str(configured), ('muscle.exe',)) == str(configured)
    # configured file is gone, bin/muscle.exe exists -> bin/
    assert p.find_tool(str(tmp_path / 'gone.exe'), ('muscle.exe',)) == str(bundled)
    # empty setting -> bin/, honouring the order of names
    (app / 'bin' / 'muscle5.exe').write_bytes(b'')
    assert p.find_tool('', ('muscle5.exe', 'muscle.exe')) == str(app / 'bin' / 'muscle5.exe')
    assert p.find_tool('', ('absent.exe', 'muscle.exe')) == str(bundled)
    # nothing exists -> the configured path, so the error message names it
    bundled.unlink()
    (app / 'bin' / 'muscle5.exe').unlink()
    missing = str(tmp_path / 'gone.exe')
    assert p.find_tool(missing, ('muscle.exe',)) == missing
    assert p.find_tool(os.path.join('bin', 'gone.exe'), ('muscle.exe',)) == os.path.join(
        str(app), 'bin', 'gone.exe')
    assert p.find_tool('', ('muscle.exe',)) == ''


def test_resource_prefers_meipass(tmp_path, monkeypatch):
    app = tmp_path / 'app'
    bundle = tmp_path / 'bundle'
    app.mkdir()
    bundle.mkdir()
    (bundle / 'locales.json').write_text('{}', 'utf-8')
    p = AppPaths(app_dir=str(app), data_dir=str(app))
    monkeypatch.setattr(sys, '_MEIPASS', str(bundle), raising=False)
    assert p.resource('locales.json') == str(bundle / 'locales.json')
    # not in the bundle -> falls back to app_dir
    assert p.resource('icon.ico') == str(app / 'icon.ico')
    monkeypatch.delattr(sys, '_MEIPASS')
    assert p.resource('locales.json') == str(app / 'locales.json')


def test_paths_module_is_qt_free():
    code = ("import sys, phyml_core.paths, phyml_core.settings; "
            "assert not [m for m in sys.modules if m.split('.')[0] in ('PySide6', 'PyQt5', 'PyQt6')]")
    result = subprocess.run([sys.executable, '-c', code], cwd=str(ROOT),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
