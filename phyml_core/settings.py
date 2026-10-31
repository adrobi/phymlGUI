"""Load, validate, atomically save and migrate the user settings (no Qt)."""
import copy
import json
import os
import shutil
import tempfile
from typing import Callable, List, Optional

from .i18n import _t
from .paths import CONFIG_NAME, HISTORY_NAME, AppPaths
from .utils import detect_cores

SCHEMA_VERSION = 2

DEFAULTS = {
    'engine': 'phyml',
    'iqtree_path': '',
    'phyml_path': '',
    'mpirun_path': 'mpiexec',
    'muscle_path': '',
    'datatype': 'nt',
    'model': 'HKY85',
    'support_method': 'bootstrap',
    'bootstrap_replicates': '100',
    'use_mpi': False,
    'mpi_np': '',
    'freq': 'default',
    'tstv': 'e',
    'pinv': '0.0',
    'classes': '4',
    'gamma': 'e',
    'search': 'NNI',
    'optimize': 'tlr',
    'parsimony': False,
    'show_tree': True,
    'theme': 'system',
    'accent': 'green',
    'recent': [],
    'presets': {},
    'window': {},
    'schema_version': SCHEMA_VERSION,
}

# settings holding a path to a tool; stored relative to app_dir when they lie inside it
PATH_KEYS = ('phyml_path', 'iqtree_path', 'muscle_path', 'mpirun_path')


def _coerce(value, default):
    """Bring a value read from disk to the type of its default; fall back to the default."""
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, str):
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return copy.deepcopy(default)
    if isinstance(value, type(default)) and not isinstance(value, bool):
        return value
    return copy.deepcopy(default)


def load(path: str, on_error: Optional[Callable[[str], None]] = None) -> dict:
    """Settings from path over DEFAULTS.

    A missing file yields the defaults. A file with damaged content (not JSON, not an
    object, not UTF-8) yields the defaults too, after its bytes are copied to
    path + '.broken' and on_error is told. A file that exists but cannot be read raises
    its OSError: returning defaults there would let a later save overwrite the user's
    real settings after a transient lock or permission error.
    """
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except FileNotFoundError:
        return copy.deepcopy(DEFAULTS)
    try:
        data = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError('settings must be a JSON object')
    except ValueError:   # includes JSONDecodeError and UnicodeDecodeError
        broken = path + '.broken'
        try:
            with open(broken, 'wb') as f:
                f.write(raw)
        except OSError:
            pass
        if on_error:
            on_error(_t('err_settings_broken').format(broken))
        return copy.deepcopy(DEFAULTS)

    cfg = {}
    for key, default in DEFAULTS.items():
        cfg[key] = _coerce(data[key], default) if key in data else copy.deepcopy(default)
    for key, value in data.items():
        if key not in DEFAULTS:
            cfg[key] = value
    cfg['schema_version'] = SCHEMA_VERSION
    return cfg


def write_json_atomic(path: str, obj, indent: int = 4) -> None:
    """Write obj as UTF-8 JSON through a temporary file in the same folder and os.replace.
    OSError is passed on to the caller; no temporary file is left behind."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, indent=indent, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save(path: str, cfg: dict) -> None:
    """Write cfg atomically (see write_json_atomic), indented by 4."""
    write_json_atomic(path, cfg, indent=4)


def _is_command_name(value: str) -> bool:
    """A bare name without a folder part, e.g. 'mpiexec' (looked up through PATH)."""
    return bool(value) and not os.path.isabs(value) and os.path.basename(value) == value


def to_disk(cfg: dict, paths: AppPaths) -> dict:
    """A copy of cfg for saving: tool paths and recent files inside app_dir become relative."""
    out = dict(cfg)
    for key in PATH_KEYS:
        if isinstance(out.get(key), str):
            out[key] = paths.to_stored(out[key])
    if isinstance(out.get('recent'), list):
        out['recent'] = [paths.to_stored(p) if isinstance(p, str) else p for p in out['recent']]
    return out


def from_disk(cfg: dict, paths: AppPaths) -> dict:
    """A copy of cfg with stored relative paths resolved against app_dir.

    A bare command name that is not a file in app_dir (the default 'mpiexec') is left
    alone, so it keeps being resolved through PATH instead of becoming app_dir/mpiexec.
    """
    out = dict(cfg)
    for key in PATH_KEYS:
        value = out.get(key)
        if not isinstance(value, str):
            continue
        if _is_command_name(value) and not os.path.exists(os.path.join(paths.app_dir, value)):
            continue
        out[key] = paths.from_stored(value)
    if isinstance(out.get('recent'), list):
        out['recent'] = [paths.from_stored(p) if isinstance(p, str) else p for p in out['recent']]
    return out


def resolve_cores(cfg: dict) -> dict:
    """A copy of cfg where an empty mpi_np ('' = "not chosen yet") becomes the number of
    physical cores. The window and the CLI both call this before using the settings."""
    out = dict(cfg)
    if not str(out.get('mpi_np') or '').strip():
        out['mpi_np'] = str(detect_cores()[0])
    return out


def migrate_legacy(paths: AppPaths, cwd: str) -> List[str]:
    """Copy config/history from the old location (the working folder) into data_dir.

    Runs only while data_dir has no config yet and cwd is a different folder. A file that
    already exists in data_dir is never overwritten, so a repeated call (history-only
    legacy folder, config deleted to reset settings, crash before the first save) copies
    nothing new. The history goes first and the config last: the config is what closes
    the gate, so a failed history copy leaves the migration to be retried. The originals
    stay in place. Returns the names of the files copied.
    """
    if os.path.realpath(cwd) == os.path.realpath(paths.data_dir):
        return []
    if os.path.exists(paths.config_file):
        return []
    pending = [n for n in (HISTORY_NAME, CONFIG_NAME)
               if os.path.isfile(os.path.join(cwd, n))
               and not os.path.exists(os.path.join(paths.data_dir, n))]
    if pending:
        os.makedirs(paths.data_dir, exist_ok=True)
    for name in pending:
        shutil.copy2(os.path.join(cwd, name), os.path.join(paths.data_dir, name))
    return pending


class SettingsStore:
    """The settings file as an application keeps it: one legacy migration, a load that
    survives a damaged file, saves that keep the keys this version does not know.

    A file that exists but cannot be read (or a failed migration with no config yet)
    blocks saving for the session, so defaults never replace the user's real settings
    and the migration gate stays open. Messages go to log(level, text).
    """

    def __init__(self, paths: AppPaths, log: Callable[[str, str], None]):
        self.paths = paths
        self._log = log
        self.blocked = False      # never save: the file could not be read
        self._save_failed = False  # the last save failed (the error is logged once)
        self._extra = {}          # keys of the file this version does not know

    def load(self, cwd: Optional[str] = None) -> tuple:
        """Migrate from cwd (default: the working folder) once, then read the file.
        Returns (settings as on disk, filled with defaults; whether they read cleanly)."""
        self._migrate(cwd)
        problems = []
        try:
            raw = load(self.paths.config_file, on_error=problems.append)
        except OSError as e:
            self.blocked = True
            problems.append(_t('err_load').format(e))
            raw = copy.deepcopy(DEFAULTS)
        for message in problems:
            self._log('error', message)
        self._extra = {k: v for k, v in raw.items() if k not in DEFAULTS}
        return raw, not problems

    def _migrate(self, cwd: Optional[str]) -> None:
        try:
            cwd = os.getcwd() if cwd is None else cwd   # getcwd fails for a deleted folder
            copied = migrate_legacy(self.paths, cwd)
        except OSError as e:
            self._log('error', _t('err_load').format(e))
            if not os.path.exists(self.paths.config_file):
                # Saving the defaults now would create the config that closes the migration
                # gate, and the legacy settings would never be copied.
                self.blocked = True
            return
        for name in copied:
            self._log('system', _t('settings_migrated').format(
                os.path.join(cwd, name), os.path.join(self.paths.data_dir, name)))

    def save(self, cfg: dict) -> None:
        """Save cfg (the form of from_disk) with the unknown keys; failures are logged once."""
        if self.blocked:
            return
        data = dict(self._extra)
        data.update(to_disk(cfg, self.paths))
        data['schema_version'] = SCHEMA_VERSION
        try:
            save(self.paths.config_file, data)
            self._save_failed = False
        except OSError as e:
            if not self._save_failed:   # every field change saves: report a failure once
                self._log('error', _t('err_settings_save').format(e))
            self._save_failed = True
