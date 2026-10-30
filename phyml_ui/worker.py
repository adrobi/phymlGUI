"""RunWorker: a PipelineRunner on a QThread, its callbacks turned into Qt signals."""
import threading
from typing import List, Mapping, Optional

from PySide6.QtCore import QThread, Signal

from phyml_core.engines.base import Engine
from phyml_core.paths import AppPaths
from phyml_core.runner import PipelineRunner


class RunWorker(QThread):
    """Runs one PipelineRunner. The signals are emitted on the worker thread, so slots of
    objects living in the GUI thread get them queued.

    log(level, text) and status(file name, status) carry the runner's callbacks when the
    runner was built by for_run(); done(RunResult) is emitted once run() is over.
    """
    log = Signal(str, str)
    status = Signal(str, str)
    done = Signal(object)

    def __init__(self, runner: PipelineRunner):
        super().__init__()
        self._runner = runner

    @classmethod
    def for_run(cls, params: dict, files: List[str], paths: AppPaths,
                engines: Optional[Mapping[str, Engine]] = None) -> 'RunWorker':
        """A worker whose runner reports through the log and status signals."""
        worker = None

        def on_log(level: str, text: str) -> None:
            worker.log.emit(level, text)

        def on_status(name: str, status: str) -> None:
            worker.status.emit(name, status)

        runner = PipelineRunner(params, files, paths, on_log=on_log, on_status=on_status,
                                engines=engines)
        worker = cls(runner)
        return worker

    @property
    def active_pid(self) -> Optional[int]:
        """PID of the program the current step runs, else None."""
        return self._runner.active_pid

    def run(self) -> None:
        self.done.emit(self._runner.run())   # run() never raises

    def cancel(self) -> None:
        """Ask the runner to stop and return at once: killing the process tree can take
        seconds, which must not be spent on the GUI thread."""
        threading.Thread(target=self._runner.cancel, name='run-cancel', daemon=True).start()
