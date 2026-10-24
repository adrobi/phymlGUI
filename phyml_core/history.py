"""Run history: a JSON list of run records, newest first (no Qt).

Two record shapes live in the same file. Records written by older versions are flat:
{'ts', 'input', 'ok', 'n', 'time', 'model', 'engine', 'tree'}. Records made by new_record carry
the full run: inputs, parameters and a result entry per file. display_input and best_tree read
both shapes, so a history file never needs converting.
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
        told. A file that exists but cannot be read raises its OSError: returning [] there
        would let the next append replace the user's real history.
        """
        try:
            with open(self.path, 'rb') as f:
                raw = f.read()
        except FileNotFoundError:
            return []
        try:
            data = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(data, list):
                raise ValueError('history must be a JSON list')
        except ValueError:   # includes JSONDecodeError and UnicodeDecodeError
            try:
                with open(self.path + '.broken', 'wb') as f:
                    f.write(raw)
            except OSError:
                pass
            if on_error:
                on_error(_t('err_history_broken').format(self.path))
            return []
        return data

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


def _name(path: str) -> str:
    """Last component of path, ignoring a trailing separator (a drive root stays whole)."""
    path = os.path.normpath(path)
    return os.path.basename(path) or path


def display_input(rec: dict) -> str:
    """Short text for what the run processed.

    A file shows its name, a folder its name plus '/', several files the name of the folder
    they share plus '/'. Old records just hold the name in 'input'.
    """
    if 'inputs' not in rec:
        return rec.get('input', '')
    inputs = rec['inputs']
    if not inputs:
        return ''
    if len(inputs) == 1:
        return _name(inputs[0]) + ('/' if os.path.isdir(inputs[0]) else '')
    try:
        common = os.path.commonpath([os.path.dirname(os.path.normpath(p)) for p in inputs])
    except ValueError:   # different drives, or absolute mixed with relative
        common = ''
    return _name(common) + '/' if common else _name(inputs[0])


def best_tree(rec: dict) -> str:
    """The tree of the last file that finished with status 'ok', '' if there is none.
    Old records hold a single path in 'tree'."""
    if 'files' not in rec:
        return rec.get('tree') or ''
    for entry in reversed(rec['files']):
        if entry.get('status') == 'ok':
            return entry.get('tree') or ''
    return ''
