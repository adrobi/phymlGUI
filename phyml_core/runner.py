"""The analysis pipeline over FASTA files, with no Qt: MUSCLE, PHYLIP conversion, the engine.

A PipelineRunner is used once. run() goes through the files in order, reports progress via
two optional callbacks (called on the thread that runs it) and always returns a RunResult;
nothing it does raises out of it. cancel() may be called from any thread at any time: it
stops the whole process tree of the current step, and the files not finished yet end as
'cancelled'.
"""
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Literal, Mapping, Optional, Tuple

from . import alignment, utils
from .alignment import AlignmentError
from .engines import ENGINES
from .engines.base import Engine, format_issue, param_text
from .i18n import _t
from .launchers import Native
from .paths import AppPaths

try:
    import psutil
except ImportError:   # a hard dependency (requirements.txt); kill_process_tree has a fallback
    psutil = None

LEVELS = ('error', 'success', 'system', 'out')
STATUSES = ('pending', 'running', 'ok', 'fail', 'cancelled')
STAT_KEYS = ('model', 'taxa', 'lnL', 'gamma', 'tstv', 'time')
MUSCLE_BASES = ('muscle',)
KILL_TIMEOUT = 3.0   # seconds between terminate and kill

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


@dataclass
class FileResult:
    file: str   # the input path as given
    status: Literal['ok', 'fail', 'cancelled']
    tree: str = ''
    stats: dict = field(default_factory=dict)
    error: str = ''


@dataclass
class RunResult:
    files: List[FileResult]
    cancelled: bool

    @property
    def ok_count(self) -> int:
        return sum(1 for f in self.files if f.status == 'ok')

    @property
    def success(self) -> bool:
        """There were files, all of them are 'ok' and the run was not cancelled."""
        return bool(self.files) and not self.cancelled and all(f.status == 'ok' for f in self.files)


def kill_process_tree(pid: int) -> None:
    """Stop a process and every process it started: terminate, wait up to 3 s, then kill.

    The parent goes first, so it cannot start a replacement child. Processes that are
    already gone are ignored. Without psutil only the process itself is signalled.
    """
    if psutil is None:
        try:
            os.kill(pid, signal.SIGTERM)   # TerminateProcess on Windows
        except OSError:
            pass
        return
    try:
        root = psutil.Process(pid)
        procs = [root] + root.children(recursive=True)
    except psutil.Error:
        return
    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            pass
    try:
        _, alive = psutil.wait_procs(procs, timeout=KILL_TIMEOUT)
    except psutil.Error:
        alive = procs
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            pass


class _FileFailed(Exception):
    """Ends the current file as 'fail'; the argument is the localized message."""


class _Cancelled(Exception):
    """Ends the current file as 'cancelled'; the argument is the key of the log message."""


class PipelineRunner:
    def __init__(self, params: dict, files: List[str], paths: AppPaths,
                 on_log: Optional[Callable[[str, str], None]] = None,
                 on_status: Optional[Callable[[str, str], None]] = None,
                 engines: Optional[Mapping[str, Engine]] = None):
        """on_log(level, text) with a level from LEVELS; on_status(file name, status) with a
        status from STATUSES. engines replaces the registry (tests pass fakes)."""
        self._params = dict(params)
        self._files = [files] if isinstance(files, str) else list(files)
        self._paths = paths
        self._on_log = on_log
        self._on_status = on_status
        self._engines = ENGINES if engines is None else engines
        self._cancelled = threading.Event()
        # guards _proc: a process is started and published, or killed, as one step
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None

    @property
    def active_pid(self) -> Optional[int]:
        """PID of the program the current step runs (MUSCLE or the engine), else None."""
        proc = self._proc
        return proc.pid if proc is not None else None

    def cancel(self) -> None:
        """Stop the run: no new step starts, the running one loses its process tree."""
        self._cancelled.set()
        try:
            # only the snapshot is taken under the lock: the kill can take a while and the
            # caller may be the GUI thread. No process starts after this point (_execute
            # checks the flag under the lock), and holding `proc` keeps its handle open, so
            # on Windows its pid cannot be reused while we kill it.
            with self._lock:
                proc = self._proc
                running = proc is not None and proc.poll() is None
            if running:
                kill_process_tree(proc.pid)
        except Exception:
            pass

    def run(self) -> RunResult:
        results: List[FileResult] = []
        error = ''
        try:
            self._run_files(results)
        except Exception as e:   # a bug outside the per-file guard: still return a result
            error = _t('err_crit').format(e)
            self._log('error', error)
        cancelled = self._cancelled.is_set()
        for fasta in self._files[len(results):]:
            status = 'cancelled' if cancelled else 'fail'
            results.append(FileResult(fasta, status, error='' if cancelled else error.strip()))
            self._status(fasta, status)
        return RunResult(results, cancelled)

    # --- the run --------------------------------------------------------------------------

    def _run_files(self, results: List[FileResult]) -> None:
        total = len(self._files)
        batch = total > 1
        if batch:
            self._log('system', _t('batch_found').format(total))
        for fasta in self._files:
            self._status(fasta, 'pending')
        for i, fasta in enumerate(self._files, 1):
            if self._cancelled.is_set():
                return
            if batch:
                self._log('system', _t('batch_file_header').format(i, total, os.path.basename(fasta)))
            self._status(fasta, 'running')
            result = self._run_file(fasta)
            results.append(result)
            self._status(fasta, result.status)
        if batch and not self._cancelled.is_set():
            ok = sum(1 for r in results if r.status == 'ok')
            self._log('success' if ok == total else 'system', _t('batch_summary').format(ok, total))

    def _run_file(self, fasta: str) -> FileResult:
        """One file, never raising: every failure becomes a FileResult."""
        try:
            tree, stats = self._process(fasta)
            return FileResult(fasta, 'ok', tree=tree, stats=stats)
        except _Cancelled as c:
            self._log('system', _t(c.args[0]))
            return FileResult(fasta, 'cancelled')
        except Exception as e:
            # whatever a cancel itself causes arrives as _Cancelled; this is a real failure
            message = e.args[0] if isinstance(e, _FileFailed) else _t('err_crit').format(e)
            self._log('error', message)
            status = 'cancelled' if self._cancelled.is_set() else 'fail'
            return FileResult(fasta, status, error=message.strip())

    def _process(self, fasta: str) -> Tuple[str, dict]:
        key = param_text(self._params, 'engine', 'phyml')
        engine = self._engines.get(key)
        if engine is None:
            raise _FileFailed(_t('err_crit').format(f'unknown engine: {key}'))
        self._log('system', _t('init_analysis').format(fasta))
        records = alignment.read_fasta(fasta)   # AlignmentError: empty or not FASTA
        if all(len(rec.seq) == 0 for rec in records):   # headers only
            raise _FileFailed(_t('err_crit').format(_t('err_empty')))
        source = fasta
        if alignment.is_aligned(records):
            self._log('success', _t('seq_aligned'))
        else:
            self._log('system', _t('diff_len'))
            source = self._align(fasta)
            records = alignment.read_fasta(source)
        if self._cancelled.is_set():
            raise _Cancelled('cancel_analysis')
        self._log('system', _t('cleaning'))
        phylip = alignment.phylip_path(source)
        self._convert(records, phylip)
        self._log('success', _t('conv_success').format(phylip))
        return self._analyse(engine, phylip)

    def _align(self, fasta: str) -> str:
        """Run MUSCLE (version 5 syntax, then version 3); returns the aligned file."""
        muscle = self._paths.find_tool(self._params.get('muscle_path') or '', tuple(utils.exe_name(b) for b in MUSCLE_BASES))
        if not muscle or not os.path.isfile(muscle):
            raise _FileFailed(_t('err_muscle'))
        aligned = alignment.aligned_path(fasta)
        if os.path.exists(aligned):
            try:
                os.remove(aligned)
            except OSError as e:
                raise _FileFailed(_t('err_del').format(e)) from e
            self._log('system', _t('del_old'))
        launcher = Native()
        code = self._execute(launcher.wrap([muscle, '-align', fasta, '-output', aligned]),
                             'cancel_align', show_output=False)
        if code != 0:
            code = self._execute(launcher.wrap([muscle, '-in', fasta, '-out', aligned]),
                                 'cancel_align', show_output=False)
        if code != 0 or not os.path.isfile(aligned):
            raise _FileFailed(_t('err_muscle_fail'))
        self._log('success', _t('align_success').format(aligned))
        return aligned

    def _convert(self, records, phylip: str) -> None:
        collide = bool(alignment.find_collisions([rec.id for rec in records]))
        try:
            alignment.write_phylip(records, phylip)
        except AlignmentError as e:   # the collision message is complete as it is
            raise _FileFailed(str(e) if collide else _t('err_conv').format(e)) from e
        except Exception as e:   # Biopython refusing the records, a write error
            raise _FileFailed(_t('err_conv').format(e)) from e

    def _analyse(self, engine: Engine, phylip: str) -> Tuple[str, dict]:
        issues = engine.validate(self._params, self._paths)
        for issue in issues:
            if issue.level != 'error':
                self._log('system', format_issue(issue))
        errors = [format_issue(issue) for issue in issues if issue.level == 'error']
        if errors:
            raise _FileFailed('\n'.join(errors))
        params, notes = engine.normalize(self._params)
        for note in notes:
            self._log('system', format_issue(note))
        exe = engine.executable(params, self._paths)
        argv = engine.launcher(params).wrap(engine.command(exe, phylip, params))
        outputs = engine.outputs(phylip)
        self._log('system', _t('run_phyml').format(subprocess.list2cmdline(argv)))
        code = self._execute(argv, 'cancel_analysis', show_output=True)
        if code != 0:
            raise _FileFailed(_t('err_engine_exit').format(engine.name, code))
        if not os.path.isfile(outputs.tree):
            raise _FileFailed(_t('err_no_tree').format(engine.name, outputs.tree))
        self._log('success', _t('success_pipe'))
        parsed = engine.parse_stats(outputs) or {}
        stats = {key: parsed.get(key, '') for key in STAT_KEYS}
        self._log('success', _t('stats_summary').format(*(stats[k] or 'n/a' for k in STAT_KEYS)))
        return outputs.tree, stats

    def _execute(self, argv: List[str], cancel_key: str, show_output: bool) -> int:
        """Run a program to its end and return its exit code; its output goes to the log
        ('out') when show_output is set. Raises _Cancelled when the run is cancelled."""
        with self._lock:
            if self._cancelled.is_set():
                raise _Cancelled(cancel_key)
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors='replace',
                                    env=utils.child_env(),
                                    creationflags=_CREATION_FLAGS)
            self._proc = proc
        try:
            for line in proc.stdout:
                if show_output:
                    self._log('out', line.rstrip())
            proc.wait()
        finally:
            if proc.poll() is None:   # left early by an exception: do not leave it running
                kill_process_tree(proc.pid)
                try:
                    proc.wait(KILL_TIMEOUT)
                except subprocess.TimeoutExpired:
                    pass
            proc.stdout.close()
            with self._lock:
                self._proc = None
        if self._cancelled.is_set():
            raise _Cancelled(cancel_key)
        return proc.returncode

    # --- callbacks ------------------------------------------------------------------------

    def _log(self, level: str, text: str) -> None:
        if self._on_log is None:
            return
        try:
            self._on_log(level, str(text).rstrip('\r\n'))
        except Exception:
            pass

    def _status(self, fasta: str, status: str) -> None:
        if self._on_status is None:
            return
        try:
            self._on_status(os.path.basename(fasta), status)
        except Exception:
            pass
