"""Run history: a JSON list of run records, newest first (no Qt).

Two record shapes live in the same file. Records written by older versions are flat:
{'ts', 'input', 'ok', 'n', 'time', 'model', 'engine', 'tree'}. Records made by new_record carry
the full run: inputs, parameters and a result entry per file. display_input and best_tree read
both shapes, so a history file never needs converting. Both helpers also survive records
whose fields have the wrong type (a hand-edited or damaged file) and always return a str.
"""
import copy
import json
import os
from datetime import datetime
from typing import Callable, List, Optional

from .i18n import _t
from .settings import write_json_atomic

HISTORY_LIMIT = 200
_TS_FORMAT = '%Y-%m-%d %H:%M'


class HistoryStore:
    """The history file at path, newest record first, at most `limit` records."""

    def __init__(self, path: str, limit: int = HISTORY_LIMIT):
        self.path = path
        self.limit = limit

    def load(self, on_error: Optional[Callable[[str], None]] = None) -> List[dict]:
        """All records, newest first.

        A missing file yields []. A file with damaged content (not JSON, not a list, not
        UTF-8) yields [] too, after its bytes are copied to path + '.broken' and on_error is
        told. A list that holds entries other than objects keeps its dict entries and is
        reported the same way, so one stray value neither hides the real history nor crashes
        whoever shows it. A file that exists but cannot be read raises its OSError: returning
        [] there would let the next append replace the user's real history.
        """
        try:
            with open(self.path, 'rb') as f:
                raw = f.read()
        except FileNotFoundError:
            return []
        try:
            data = json.loads(raw.decode('utf-8-sig'))
        except ValueError:   # includes JSONDecodeError and UnicodeDecodeError
            data = None
        if not isinstance(data, list):
            self._report_broken(raw, on_error)
            return []
        records = [entry for entry in data if isinstance(entry, dict)]
        if len(records) != len(data):
            self._report_broken(raw, on_error)
        return records

    def _report_broken(self, raw: bytes, on_error: Optional[Callable[[str], None]]) -> None:
        """Keep the unusable bytes next to the history file and tell the caller."""
        try:
            with open(self.path + '.broken', 'wb') as f:
                f.write(raw)
        except OSError:
            pass
        if on_error:
            on_error(_t('err_history_broken').format(self.path))

    def append(self, record: dict) -> None:
        """Put record first, cut the list to `limit` and write the file atomically.
        A damaged file is kept as path + '.broken' before it is replaced. OSError is passed on."""
        records = self.load()
        records.insert(0, record)
        write_json_atomic(self.path, records[:self.limit], indent=2)

    def get(self, index: int) -> Optional[dict]:
        """The record at index (0 is the newest), or None when there is none."""
        records = self.load()
        if 0 <= index < len(records):
            return records[index]
        return None


def new_record(*, inputs: List[str], engine: str, params: dict, files: List[dict],
               duration_s: float, ts: Optional[datetime] = None) -> dict:
    """A history record for a finished run.

    files holds one entry per processed file: {'file', 'status', 'tree', 'stats', 'error'}.
    'ok' counts the entries whose status is 'ok', 'n' all of them.
    """
    ts = ts or datetime.now()
    return {
        'ts': ts.strftime(_TS_FORMAT),
        'inputs': list(inputs),
        'engine': engine,
        'params': copy.deepcopy(params),
        'files': copy.deepcopy(files),
        'ok': sum(1 for f in files if f.get('status') == 'ok'),
        'n': len(files),
        'duration_s': duration_s,
    }


def _text(value) -> str:
    """value if it is a str, else ''; a malformed field must not leak a non-str to the caller."""
    return value if isinstance(value, str) else ''


def _name(path: str) -> str:
    """Last component of path, ignoring a trailing separator (a drive root stays whole)."""
    path = os.path.normpath(path)
    return os.path.basename(path) or path


def _same_path(entry_file: str, input_path: str) -> bool:
    """Whether a file entry names the input itself; a bare file name matches by its name."""
    a = os.path.normcase(os.path.normpath(entry_file))
    b = os.path.normcase(os.path.normpath(input_path))
    return a == b or (not os.path.dirname(a) and a == os.path.basename(b))


def _file_entries(rec: dict) -> List[dict]:
    """The dict entries of rec['files'] (none when it is missing or not a list)."""
    files = rec.get('files')
    return [e for e in files if isinstance(e, dict)] if isinstance(files, list) else []


def display_input(rec: dict) -> str:
    """Short text for what the run processed, derived from the record alone (the files may
    be gone, or sit on a share that no longer answers).

    A single input that is the path of its only file entry shows its name. A single input
    with other paths in 'files' is a folder: its name plus '/'. With no file entries there
    is nothing to tell it by, so the plain name is shown. Several inputs show the name of
    the folder they share plus '/'. Old records just hold the name in 'input'.
    """
    inputs = rec.get('inputs')
    inputs = [p for p in inputs if isinstance(p, str) and p] if isinstance(inputs, list) else []
    if not inputs:
        return _text(rec.get('input'))
    if len(inputs) == 1:
        entries = [e['file'] for e in _file_entries(rec) if isinstance(e.get('file'), str)]
        is_folder = bool(entries) and not any(_same_path(f, inputs[0]) for f in entries)
        return _name(inputs[0]) + ('/' if is_folder else '')
    try:
        common = os.path.commonpath([os.path.dirname(os.path.normpath(p)) for p in inputs])
    except ValueError:   # different drives, or absolute mixed with relative
        common = ''
    return _name(common) + '/' if common else _name(inputs[0])


def best_tree(rec: dict) -> str:
    """The tree of the last file that finished with status 'ok', '' if there is none.
    Old records hold a single path in 'tree'."""
    if not isinstance(rec.get('files'), list):
        return _text(rec.get('tree'))
    for entry in reversed(_file_entries(rec)):
        if entry.get('status') == 'ok':
            return _text(entry.get('tree'))
    return ''
