"""Load, validate, atomically save and migrate the user settings (no Qt)."""
import copy
import json
import os
import shutil
import tempfile
from typing import Callable, List, Optional

from .i18n import _t
from .paths import CONFIG_NAME, HISTORY_NAME, AppPaths

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
