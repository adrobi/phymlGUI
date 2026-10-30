import os

import pytest

from phyml_core import report
from phyml_core.runner import FileResult


def _results():
    return [
        FileResult(file=os.path.join('some', 'dir', 'a.fasta'), status='ok', tree='a.tre',
                   stats={'model': 'GTR', 'taxa': '5', 'lnL': '-100.5', 'gamma': '0.5',
                          'tstv': '2.0', 'time': '1s'}),
        FileResult(file='b.fasta', status='fail', error='boom'),
        FileResult(file='c.fasta', status='cancelled'),
    ]


def test_rows_from_results():
    rows = report.summary_rows(_results())
    assert [r['status'] for r in rows] == ['OK', 'FAIL', 'CANCELLED']
    assert [r['file'] for r in rows] == ['a.fasta', 'b.fasta', 'c.fasta']
    assert rows[0]['model'] == 'GTR' and rows[0]['lnL'] == '-100.5'
    assert rows[0]['tree'] == 'a.tre'
    assert rows[1]['model'] == '' and rows[1]['tree'] == ''
    assert set(rows[0]) == set(report.SUMMARY_COLUMNS)


def test_csv_matches_current_format(tmp_path):
    rows = report.summary_rows(_results())
    paths = report.write_summary(rows, str(tmp_path))
    csv_path = tmp_path / 'phymlgui_summary.csv'
    assert str(csv_path) in paths
    raw = csv_path.read_bytes()
    assert raw.startswith(b'\xef\xbb\xbf')
    lines = raw.decode('utf-8-sig').splitlines()
    assert lines[0] == 'file;status;model;taxa;lnL;gamma;tstv;time;tree'
    assert lines[1].startswith('a.fasta;OK;GTR;5;')
    assert len(lines) == 4


def test_xlsx_written_when_openpyxl_available(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    rows = report.summary_rows(_results())
    paths = report.write_summary(rows, str(tmp_path))
    xlsx = tmp_path / 'phymlgui_summary.xlsx'
    assert str(xlsx) in paths
    ws = openpyxl.load_workbook(str(xlsx))['Summary']
    assert ws.max_row == len(rows) + 1
    assert ws.max_column == len(report.SUMMARY_COLUMNS) - 1
    assert ws.column_dimensions['A'].width == 28


def test_csv_only_without_openpyxl(tmp_path, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith('openpyxl'):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, '__import__', fake)
    paths = report.write_summary(report.summary_rows(_results()), str(tmp_path))
    assert paths == [str(tmp_path / 'phymlgui_summary.csv')]


def test_cyrillic_and_space_folder(tmp_path):
    out = tmp_path / 'Мои результаты 1'
    out.mkdir()
    paths = report.write_summary(report.summary_rows(_results()), str(out))
    assert paths and all(os.path.isfile(p) for p in paths)


def test_oserror_propagates(tmp_path):
    with pytest.raises(OSError):
        report.write_summary([], str(tmp_path / 'missing'))
