"""The Engine interface every phylogeny program implements (no Qt)."""
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple, Union

from ..i18n import _t
from ..launchers import Mpi, Native
from ..paths import AppPaths


@dataclass(frozen=True)
class Issue:
    """A problem found before a run; `key` is a localization key, `args` fill its {} slots."""
    level: Literal['error', 'warning']
    key: str
    args: tuple = ()


@dataclass(frozen=True)
class EngineOutputs:
    """Files an engine writes next to the PHYLIP input; None where it writes no such file."""
    tree: str
    stats: str
    boot_trees: Optional[str]
    log: Optional[str]


# settings key -> localization key of the label the user sees in the window
_PARAM_LABELS = {
    'bootstrap_replicates': 'lbl_boot',
    'mpi_np': 'lbl_mpi_np',
    'pinv': 'lbl_pinv',
    'classes': 'lbl_classes',
    'tstv': 'lbl_tstv',
    'gamma': 'lbl_gamma',
}


def format_issue(issue: Issue) -> str:
    """The localized message; a parameter named in val_not_number is shown by its UI label."""
    args = issue.args
    if issue.key == 'val_not_number' and args and args[0] in _PARAM_LABELS:
        label = _t(_PARAM_LABELS[args[0]]).rstrip().rstrip(':').rstrip()
        args = (label,) + tuple(args[1:])
    return _t(issue.key).format(*args)


def param_text(params: dict, key: str, default: str = '') -> str:
    """A parameter as trimmed text; a missing or None value gives the default."""
    value = params.get(key)
    return default if value is None else str(value).strip()


_DECIMAL = re.compile(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
_INTEGER = re.compile(r'[0-9]+')


def parse_decimal(value) -> Optional[float]:
    """A plain non-negative decimal ('3', '0.5', '.5', '2.', '1e-3') as a float, else None.

    Unlike float() this rejects signs, 'nan'/'inf' (and exponents that overflow to inf),
    digit separators and non-ASCII digits, i.e. everything an engine's own argument parser
    may not accept.
    """
    text = str(value).strip()
    if not _DECIMAL.fullmatch(text):
        return None
    number = float(text)
    return number if math.isfinite(number) else None


def positive_number(value) -> bool:
    """An integer or a decimal fraction greater than zero."""
    number = parse_decimal(value)
    return number is not None and number > 0


def positive_int(value) -> bool:
    """A whole number greater than zero."""
    text = str(value).strip()
    return bool(_INTEGER.fullmatch(text)) and int(text) > 0


class Engine(ABC):
    key: str          # 'phyml' | 'iqtree' | later 'raxml'
    name: str         # shown in messages: 'PhyML', 'IQ-TREE'
    label_key: str    # localization key of the name in the engine selector

    @abstractmethod
    def models(self, datatype: str) -> List[str]:
        """Substitution models offered for 'nt' or 'aa' data."""

    @abstractmethod
    def validate(self, params: dict, paths: AppPaths) -> List[Issue]:
        """Everything that would make the run fail or mislead, in one pass."""

    @abstractmethod
    def normalize(self, params: dict) -> Tuple[dict, List[Issue]]:
        """A copy of params adjusted to what the engine accepts, with a note per change."""

    @abstractmethod
    def executable(self, params: dict, paths: AppPaths) -> str:
        """The configured program, else the one shipped in bin/ (may not exist)."""

    @abstractmethod
    def command(self, exe: str, phylip: str, params: dict) -> List[str]:
        """The engine's own argv, without any launcher prefix. A pure function."""

    @abstractmethod
    def outputs(self, phylip: str) -> EngineOutputs:
        """Where the engine writes its results for this input."""

    @abstractmethod
    def parse_stats(self, outputs: EngineOutputs) -> Dict[str, str]:
        """model, taxa, lnL, gamma, tstv, time (empty strings where unknown)."""

    @abstractmethod
    def launcher(self, params: dict) -> Union[Native, Mpi]:
        """How to start the command: directly or under mpiexec."""
