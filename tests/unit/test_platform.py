"""Linux portability of the core: tool names, PATH lookup, data dir, mpirun."""
import json
import os
import shutil

from phyml_core import settings, utils
from phyml_core.engines.base import Issue
from phyml_core.engines.phyml import PhyML
from phyml_core.paths import AppPaths


def test_exe_name_per_platform(monkeypatch):
    monkeypatch.setattr(utils, 'IS_WINDOWS', True)
    assert utils.exe_name('muscle') == 'muscle.exe'
    assert utils.default_mpirun() == 'mpiexec'
    monkeypatch.setattr(utils, 'IS_WINDOWS', False)
    assert utils.exe_name('muscle') == 'muscle'
    assert utils.default_mpirun() == 'mpirun'


def test_find_tool_falls_back_to_path(tmp_path, monkeypatch):
    p = AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path))
    on_path = str(tmp_path / 'usr' / 'muscle')
    monkeypatch.setattr(shutil, 'which', lambda name, *a, **k: on_path if name == 'muscle' else None)
    assert p.find_tool('', ('muscle',)) == on_path
    # bin/ still wins over PATH
    os.makedirs(p.bin_dir)
    bundled = os.path.join(p.bin_dir, 'muscle')
    open(bundled, 'w').close()
    assert p.find_tool('', ('muscle',)) == bundled


def test_detect_falls_back_to_xdg_on_linux(tmp_path):
    xdg = tmp_path / 'xdg'
    p = AppPaths.detect(env={'XDG_CONFIG_HOME': str(xdg)}, is_writable=lambda d: False,
                        app_dir=str(tmp_path / 'app'), platform='posix')
    assert p.data_dir == str(xdg / 'phymlGUI') and os.path.isdir(p.data_dir)
    home = tmp_path / 'home'
    p = AppPaths.detect(env={'HOME': str(home)}, is_writable=lambda d: False,
                        app_dir=str(tmp_path / 'app'), platform='posix')
    assert p.data_dir == str(home / '.config' / 'phymlGUI')


def test_validate_mpirun_missing_on_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, 'IS_WINDOWS', False)
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    exe = tmp_path / 'phyml-mpi'
    exe.write_text('')
    paths = AppPaths(app_dir=str(tmp_path), data_dir=str(tmp_path))
    params = dict(settings.DEFAULTS, phyml_path=str(exe), use_mpi=True, mpi_np='2',
                  mpirun_path='mpirun', support_method='bootstrap')
    assert PhyML().validate(params, paths) == [Issue('error', 'val_no_mpiexec', ('mpirun',))]
    # an empty field falls back to the platform default, mpirun
    assert PhyML().validate(dict(params, mpirun_path=''), paths) == [
        Issue('error', 'val_no_mpiexec', ('mpirun',))]


def test_windows_config_loads_on_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, 'IS_WINDOWS', False)
    monkeypatch.setattr(shutil, 'which', lambda *a, **k: None)
    cfg_file = tmp_path / 'phyml_config.json'
    cfg_file.write_text(json.dumps({'mpirun_path': 'mpiexec',
                                    'phyml_path': 'C:\\x\\phyml-mpi.exe'}), 'utf-8')
    paths = AppPaths(app_dir=str(tmp_path / 'app'), data_dir=str(tmp_path))
    cfg = settings.from_disk(settings.load(str(cfg_file)), paths)
    assert cfg['mpirun_path'] == 'mpirun'
    issues = PhyML().validate(dict(cfg, mpi_np='2'), paths)
    assert issues and issues[0].key == 'val_no_exe'


def test_detect_never_uses_app_dir_inside_an_appimage(tmp_path):
    """--appimage-extract-and-run unpacks into a writable temp folder; settings must
    still go to ~/.config/phymlGUI, not into that throwaway folder."""
    p = AppPaths.detect(env={'APPIMAGE': '/home/u/phymlGUI.AppImage', 'HOME': str(tmp_path)},
                        is_writable=lambda d: True, app_dir=str(tmp_path / 'squashfs-root' / 'usr' / 'bin'),
                        platform='posix')
    assert p.data_dir == str(tmp_path / '.config' / 'phymlGUI')


def test_child_env_undoes_the_pyinstaller_library_path(monkeypatch):
    """The frozen Linux bootloader puts _internal first on LD_LIBRARY_PATH; mpirun,
    phyml-mpi and xdg-open must get the user's own value back (or none)."""
    monkeypatch.setattr(utils, 'IS_WINDOWS', False)
    frozen = {'LD_LIBRARY_PATH': '/tmp/_internal:/opt/lib', 'LD_LIBRARY_PATH_ORIG': '/opt/lib', 'X': '1'}
    assert utils.child_env(frozen, frozen=True) == {'LD_LIBRARY_PATH': '/opt/lib', 'X': '1'}
    assert utils.child_env({'LD_LIBRARY_PATH': '/tmp/_internal', 'X': '1'}, frozen=True) == {'X': '1'}
    plain = {'LD_LIBRARY_PATH': '/opt/lib', 'X': '1'}
    assert utils.child_env(plain, frozen=False) == plain
    monkeypatch.setattr(utils, 'IS_WINDOWS', True)
    assert utils.child_env(frozen, frozen=True) == frozen


def test_runner_starts_programs_with_the_child_env(monkeypatch):
    import subprocess
    from phyml_core import runner
    seen = {}

    class Stop(Exception):
        pass

    def fake_popen(argv, **kwargs):
        seen.update(kwargs)
        raise Stop
    monkeypatch.setattr(utils, 'child_env', lambda: {'MARK': 'child'})
    monkeypatch.setattr(subprocess, 'Popen', fake_popen)
    r = runner.PipelineRunner.__new__(runner.PipelineRunner)
    import threading
    r._lock, r._cancelled = threading.Lock(), threading.Event()
    try:
        r._execute(['x'], 'cancel', False)
    except Stop:
        pass
    assert seen.get('env') == {'MARK': 'child'}
