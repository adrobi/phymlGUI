import os
import sys

from .paths import default_app_dir

try:
    import psutil  # optional: CPU monitoring and physical core detection
except ImportError:
    psutil = None


IS_WINDOWS = os.name == 'nt'


def exe_name(base):
    """Platform file name of a tool: 'muscle' -> 'muscle.exe' on Windows."""
    return base + '.exe' if IS_WINDOWS else base


def default_mpirun():
    """The MPI launcher looked up through PATH: MS-MPI's mpiexec or OpenMPI's mpirun."""
    return 'mpiexec' if IS_WINDOWS else 'mpirun'


def child_env(environ=None, frozen=None):
    """Environment for programs started by the app. A frozen Linux build's bootloader
    puts its _internal folder first on LD_LIBRARY_PATH (the user's value is kept in
    LD_LIBRARY_PATH_ORIG); child programs must not load those bundled libraries."""
    env = dict(os.environ if environ is None else environ)
    if frozen is None:
        frozen = getattr(sys, 'frozen', False)
    if frozen and not IS_WINDOWS:
        original = env.pop('LD_LIBRARY_PATH_ORIG', None)
        if original is None:
            env.pop('LD_LIBRARY_PATH', None)
        else:
            env['LD_LIBRARY_PATH'] = original
    return env


def resource_path(relative_path):
    """Absolute path to a bundled resource: inside the PyInstaller bundle when frozen,
    otherwise next to the program (never relative to the current working folder)."""
    base_path = getattr(sys, '_MEIPASS', None) or default_app_dir()
    return os.path.join(base_path, relative_path)


def detect_cores():
    """Physical and logical CPU counts (psutil preferred, os fallback)."""
    phys = logi = None
    if psutil is not None:
        phys = psutil.cpu_count(logical=False)
        logi = psutil.cpu_count(logical=True)
    phys = phys or os.cpu_count() or 2
    logi = logi or os.cpu_count() or phys
    return phys, logi


def is_mpi_binary(path):
    """Heuristic: PhyML MPI builds are named phyml-mpi / phyml_mpi etc."""
    return 'mpi' in os.path.basename(path or '').lower()
