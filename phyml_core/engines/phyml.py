"""The PhyML engine: argv, validation, outputs and the stats parser (no Qt)."""
import os
import re
import shutil
from typing import Dict, List, Tuple, Union

from ..launchers import Mpi, Native
from ..paths import AppPaths
from ..utils import is_mpi_binary
from .base import (Engine, EngineOutputs, Issue, param_text, parse_decimal, positive_int,
                   positive_number)

NT_MODELS = ("HKY85", "JC69", "K80", "F81", "F84", "TN93", "GTR", "custom")
AA_MODELS = ("LG", "WAG", "JTT", "MtREV", "Dayhoff", "DCMut", "RtREV", "CPREV", "VT", "Blosum62",
             "MtMam", "MtArt", "HIVw", "HIVb", "custom")

EXECUTABLE_NAMES = ('phyml-mpi.exe', 'phyml.exe')


def parse_phyml_stats(stats_path: str) -> dict:
    """Parse key values from a PhyML 3.3 stats file into a dict."""
    try:
        with open(stats_path, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return {}
    def grab(pattern):
        m = re.search(pattern, content)
        return m.group(1) if m else ""
    return {
        'model': grab(r'Model of \w+ substitution:\s*(\S+)'),
        'taxa': grab(r'Number of taxa:\s*(\d+)'),
        'lnL': grab(r'Log-likelihood:\s*(-?[\d.]+)'),
        'gamma': grab(r'Gamma shape parameter:\s*(-?[\d.]+)'),
        'tstv': grab(r'transition/transversion ratio:\s*(-?[\d.]+)'),
        'time': grab(r'Time used:\s*(\S+)'),
    }


def _estimate_or_positive(value: str) -> bool:
    return value == 'e' or positive_number(value)


def _estimate_or_fraction(value: str) -> bool:
    """PhyML -v: 'e' (estimate) or a proportion of invariable sites in [0, 1)."""
    if value == 'e':
        return True
    number = parse_decimal(value)
    return number is not None and number < 1


def _mpiexec_found(mpiexec: str) -> bool:
    return bool(mpiexec) and (os.path.isfile(mpiexec) or shutil.which(mpiexec) is not None)


class PhyML(Engine):
    key = 'phyml'
    name = 'PhyML'
    label_key = 'engine_phyml'

    def models(self, datatype: str) -> List[str]:
        return list(NT_MODELS if datatype == 'nt' else AA_MODELS)

    def validate(self, params: dict, paths: AppPaths) -> List[Issue]:
        issues: List[Issue] = []
        use_mpi = bool(params.get('use_mpi', False))
        bootstrap = param_text(params, 'support_method', 'bootstrap') == 'bootstrap'

        exe = self.executable(params, paths)
        if not exe or not os.path.isfile(exe):
            issues.append(Issue('error', 'val_no_exe', (self.name, exe)))
        elif is_mpi_binary(exe) and not use_mpi and bootstrap:
            issues.append(Issue('error', 'mpi_boot_msg'))

        if use_mpi:
            mpiexec = param_text(params, 'mpirun_path', 'mpiexec')
            if not _mpiexec_found(mpiexec):
                issues.append(Issue('error', 'val_no_mpiexec', (mpiexec,)))

        def check(name: str, value: str, ok: bool) -> None:
            if not ok:
                issues.append(Issue('error', 'val_not_number', (name, value)))

        if bootstrap:
            value = param_text(params, 'bootstrap_replicates', '100')
            check('bootstrap_replicates', value, positive_int(value))
        # empty tstv / pinv / classes / gamma are legal: they are left out of the argv
        value = param_text(params, 'tstv')
        check('tstv', value, not value or _estimate_or_positive(value))
        value = param_text(params, 'pinv')
        check('pinv', value, not value or _estimate_or_fraction(value))
        value = param_text(params, 'classes')
        check('classes', value, not value or positive_int(value))
        value = param_text(params, 'gamma')
        check('gamma', value, not value or _estimate_or_positive(value))
        if use_mpi:
            value = param_text(params, 'mpi_np', '2')
            check('mpi_np', value, positive_int(value))
        return issues

    def normalize(self, params: dict) -> Tuple[dict, List[Issue]]:
        return dict(params), []

    def executable(self, params: dict, paths: AppPaths) -> str:
        return paths.find_tool(params.get('phyml_path', ''), EXECUTABLE_NAMES)

    def command(self, exe: str, phylip: str, params: dict) -> List[str]:
        argv = [exe, '-i', phylip,
                '-d', param_text(params, 'datatype', 'nt'),
                '-m', param_text(params, 'model', 'HKY85')]
        support = param_text(params, 'support_method', 'bootstrap')
        argv += ['-b', param_text(params, 'bootstrap_replicates', '100') if support == 'bootstrap' else support]
        freq = param_text(params, 'freq')
        if freq and freq != 'default':
            argv += ['-f', freq]
        for flag, key in (('-t', 'tstv'), ('-v', 'pinv'), ('-c', 'classes'), ('-a', 'gamma')):
            value = param_text(params, key)
            if value:
                argv += [flag, value]
        argv += ['-s', param_text(params, 'search', 'NNI'), '-o', param_text(params, 'optimize', 'tlr')]
        if params.get('parsimony'):
            argv.append('-p')
        return argv

    def outputs(self, phylip: str) -> EngineOutputs:
        return EngineOutputs(tree=phylip + '_phyml_tree.txt',
                             stats=phylip + '_phyml_stats.txt',
                             boot_trees=phylip + '_phyml_boot_trees.txt',
                             log=None)

    def parse_stats(self, outputs: EngineOutputs) -> Dict[str, str]:
        return parse_phyml_stats(outputs.stats)

    def launcher(self, params: dict) -> Union[Native, Mpi]:
        """Call validate() first: a bad mpi_np raises ValueError here."""
        if not params.get('use_mpi', False):
            return Native()
        mpiexec = param_text(params, 'mpirun_path', 'mpiexec')
        return Mpi((mpiexec and shutil.which(mpiexec)) or mpiexec, int(param_text(params, 'mpi_np', '2')))
