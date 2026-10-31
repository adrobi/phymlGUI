"""CSV/XLSX run summary (Qt-free)."""
import csv
import os
from typing import List

from .i18n import _t
from .runner import FileResult

SUMMARY_COLUMNS = ('file', 'status', 'model', 'taxa', 'lnL', 'gamma', 'tstv', 'time', 'tree')
_STATUS_TEXT = {'ok': 'OK', 'fail': 'FAIL', 'cancelled': 'CANCELLED'}
_XLSX_WIDTHS = (28, 8, 16, 8, 12, 10, 10, 12)
CSV_NAME = 'phymlgui_summary.csv'
XLSX_NAME = 'phymlgui_summary.xlsx'


def summary_rows(files: List[FileResult]) -> List[dict]:
    rows = []
    for f in files:
        row = {c: (f.stats or {}).get(c) or '' for c in SUMMARY_COLUMNS}
        row['file'] = os.path.basename(f.file)
        row['status'] = _STATUS_TEXT.get(f.status, str(f.status).upper())
        row['tree'] = f.tree or ''
        rows.append(row)
    return rows


def write_summary(rows: List[dict], out_dir: str) -> List[str]:
    """Write the CSV (and the XLSX if openpyxl is installed); return the written paths.

    OSError is propagated to the caller.
    """
    csv_path = os.path.join(out_dir, CSV_NAME)
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        wr = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS, delimiter=';', extrasaction='ignore')
        wr.writeheader()
        wr.writerows(rows)
    written = [csv_path]
    try:
        from openpyxl import Workbook
    except ImportError:
        return written
    cols = SUMMARY_COLUMNS[:-1]
    wb = Workbook()
    ws = wb.active
    ws.title = 'Summary'
    ws.append([_t('sum_col_' + c) for c in cols])
    for r in rows:
        ws.append([r.get(c) or '' for c in cols])
    for col, width in zip('ABCDEFGHI', _XLSX_WIDTHS):
        ws.column_dimensions[col].width = width
    xlsx_path = os.path.join(out_dir, XLSX_NAME)
    wb.save(xlsx_path)
    written.append(xlsx_path)
    return written
