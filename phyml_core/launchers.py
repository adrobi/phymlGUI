"""How an engine command is started: directly, or under mpiexec (no Qt)."""
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Native:
    """Run the command as it is."""

    def wrap(self, argv: List[str]) -> List[str]:
        return list(argv)


@dataclass(frozen=True)
class Mpi:
    """Run the command under `mpiexec -np <np>`."""
    mpiexec: str
    np: int

    def wrap(self, argv: List[str]) -> List[str]:
        return [self.mpiexec, '-np', str(self.np), *argv]
