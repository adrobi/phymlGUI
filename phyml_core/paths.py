"""Where phymlGUI keeps its program files and its user data (no Qt, no cwd dependence)."""
import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

CONFIG_NAME = 'phyml_config.json'
HISTORY_NAME = 'phyml_history.json'
DATA_DIR_ENV = 'PHYMLGUI_DATA_DIR'
APPDATA_SUBDIR = 'phymlGUI'


def default_app_dir() -> str:
    """Folder of the frozen exe, or the repository root when run from sources."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dir_is_writable(directory: str) -> bool:
    """Probe by creating and deleting a temporary file inside the folder."""
    try:
        fd, probe = tempfile.mkstemp(dir=directory, prefix='.phymlgui-')
        os.close(fd)
        os.remove(probe)
        return True
    except OSError:
        return False


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


@dataclass(frozen=True)
class AppPaths:
    app_dir: str    # program files: bin/, locales.json, the exe
    data_dir: str   # user data: config and history

    @property
    def bin_dir(self) -> str:
        return os.path.join(self.app_dir, 'bin')

    @property
    def config_file(self) -> str:
        return os.path.join(self.data_dir, CONFIG_NAME)

    @property
    def history_file(self) -> str:
        return os.path.join(self.data_dir, HISTORY_NAME)

    def resource(self, name: str) -> str:
        """A bundled resource: inside sys._MEIPASS when frozen, else next to the program."""
        bundle = getattr(sys, '_MEIPASS', None)
        if bundle:
            candidate = os.path.join(bundle, name)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(self.app_dir, name)

    def to_stored(self, path: str) -> str:
        """Relative to app_dir when the path lies inside it, otherwise unchanged.

        A relative input (a bare command name such as 'mpiexec', or an already stored
        value) has no defined location, so it is returned as is.
        """
        if not path or not os.path.isabs(path):
            return path
        target, root = _norm(path), _norm(self.app_dir)
        try:
            inside = target != root and os.path.commonpath([target, root]) == root
        except ValueError:   # different drives
            inside = False
        return os.path.relpath(os.path.abspath(path), os.path.abspath(self.app_dir)) if inside else path

    def from_stored(self, stored: str) -> str:
        """Inverse of to_stored: a relative value is resolved against app_dir."""
        if not stored or os.path.isabs(stored):
            return stored
        return os.path.join(self.app_dir, stored)

    def find_tool(self, stored: str, names: tuple) -> str:
        """The configured tool if it exists, else the first of names in bin/, else the
        configured path again (so the error message names what the user set)."""
        configured = self.from_stored(stored)
        if configured and os.path.isfile(configured):
            return configured
        for name in names:
            candidate = os.path.join(self.bin_dir, name)
            if os.path.isfile(candidate):
                return candidate
        return configured

    @classmethod
    def detect(cls, env: Optional[Mapping[str, str]] = None,
               is_writable: Optional[Callable[[str], bool]] = None,
               app_dir: Optional[str] = None) -> 'AppPaths':
        """Pick the data folder: $PHYMLGUI_DATA_DIR, then app_dir if writable, then
        %APPDATA%\\phymlGUI. The chosen folder is created."""
        env = os.environ if env is None else env
        is_writable = is_writable or _dir_is_writable
        app = default_app_dir() if app_dir is None else app_dir
        override = env.get(DATA_DIR_ENV)
        if override:
            data = override
        elif is_writable(app):
            data = app
        else:
            base = env.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
            data = os.path.join(base, APPDATA_SUBDIR)
        os.makedirs(data, exist_ok=True)
        return cls(app_dir=app, data_dir=data)
