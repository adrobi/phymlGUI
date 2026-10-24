import os
import sys

from .paths import default_app_dir

try:
    import psutil  # optional: CPU monitoring and physical core detection
except ImportError:
    psutil = None


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
