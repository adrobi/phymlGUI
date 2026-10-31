"""The IQ-TREE engine: argv, validation, outputs and the stats parser (no Qt)."""
import os
import re
from typing import Dict, List, Tuple, Union

from ..launchers import Mpi, Native
from ..paths import AppPaths
from ..utils import exe_name
from .base import Engine, EngineOutputs, Issue, param_text, positive_int

NT_MODELS = ("MFP", "GTR+F+G4", "HKY+F+G4", "TIM2+F+G4", "TVM+F+G4")
AA_MODELS = ("MFP", "LG+G4", "WAG+G4", "JTT+G4", "mtREV+G4")

EXECUTABLE_BASES = ('iqtree2',)

UFBOOT_MIN_REPLICATES = 1000


def parse_iqtree_stats(stats_path: str) -> dict:
    """Parse key values from an IQ-TREE .iqtree report into a dict."""
    try:
        with open(stats_path, encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return {}
    def grab(pattern):
        m = re.search(pattern, content)
        return m.group(1) if m else ""
    return {
        'model': grab(r'Best-fit model according to \w+:\s*(\S+)') or grab(r'Model of substitution:\s*(\S+)'),
        'taxa': grab(r'Input data:\s*(\d+) sequences'),
        'lnL': grab(r'Log-likelihood of the tree:\s*(-?[\d.]+)'),
        'gamma': grab(r'Gamma shape alpha:\s*([\d.]+)'),
        'tstv': '',
        'time': (grab(r'Total wall-clock time used:\s*([\d.]+)') + ' s').strip(),
    }


def ufboot_replicates(value) -> str:
    """IQ-TREE -B value: UFBoot refuses fewer than 1000 replicates."""
    try:
        n = int(str(value).strip())
    except ValueError:
        n = 0
    return str(max(n, UFBOOT_MIN_REPLICATES))


def _prefix(phylip: str) -> str:
    """IQ-TREE --prefix: every output file is this plus an extension."""
    return phylip.rsplit('.', 1)[0] + '_iqtree'


class IqTree(Engine):
    key = 'iqtree'
    name = 'IQ-TREE'
    label_key = 'engine_iqtree'

    def models(self, datatype: str) -> List[str]:
        return list(NT_MODELS if datatype == 'nt' else AA_MODELS)

    def validate(self, params: dict, paths: AppPaths) -> List[Issue]:
        issues: List[Issue] = []
        exe = self.executable(params, paths)
        if not exe or not os.path.isfile(exe):
            issues.append(Issue('error', 'val_no_exe', (self.name, exe)))

        def check(name: str, value: str, ok: bool) -> None:
            if not ok:
                issues.append(Issue('error', 'val_not_number', (name, value)))

        if param_text(params, 'support_method', 'bootstrap') == 'bootstrap':
            # below 1000 is valid input: normalize() raises it
            value = param_text(params, 'bootstrap_replicates', '1000')
            check('bootstrap_replicates', value, positive_int(value))
        # IQ-TREE has no MPI mode: mpi_np is its thread count (-T), whatever use_mpi says
        value = param_text(params, 'mpi_np', '2')
        check('mpi_np', value, positive_int(value))
        return issues

    def normalize(self, params: dict) -> Tuple[dict, List[Issue]]:
        normalized, notes = dict(params), []
        if param_text(params, 'support_method', 'bootstrap') == 'bootstrap':
            requested = param_text(params, 'bootstrap_replicates', '1000')
            replicates = ufboot_replicates(requested)
            if replicates != requested:
                normalized['bootstrap_replicates'] = replicates
                notes.append(Issue('warning', 'iqtree_ufboot_min', (replicates, requested)))
        return normalized, notes

    def executable(self, params: dict, paths: AppPaths) -> str:
        return paths.find_tool(params.get('iqtree_path', ''), tuple(exe_name(b) for b in EXECUTABLE_BASES))

    def command(self, exe: str, phylip: str, params: dict) -> List[str]:
        argv = [exe, '-s', phylip, '--prefix', _prefix(phylip), '-redo',
                '-m', param_text(params, 'model', 'MFP'),
                '-T', param_text(params, 'mpi_np', '2')]
        support = param_text(params, 'support_method', 'bootstrap')
        if support == 'bootstrap':
            # normalize() reports a raised count; this keeps the argv valid even without it
            argv += ['-B', ufboot_replicates(param_text(params, 'bootstrap_replicates', '1000'))]
        elif support.startswith('-'):
            argv += ['--alrt', '1000']  # aLRT branch support
        return argv

    def outputs(self, phylip: str) -> EngineOutputs:
        prefix = _prefix(phylip)
        return EngineOutputs(tree=prefix + '.treefile',
                             stats=prefix + '.iqtree',
                             boot_trees=None,
                             log=prefix + '.log')

    def parse_stats(self, outputs: EngineOutputs) -> Dict[str, str]:
        return parse_iqtree_stats(outputs.stats)

    def launcher(self, params: dict) -> Union[Native, Mpi]:
        return Native()
