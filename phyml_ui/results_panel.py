import os

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QLabel, QListWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView, QToolButton)
from PySide6.QtCore import Signal

from phyml_core.i18n import _t
from phyml_ui.log_console import LogConsole

# queue marker per file status of the runner
_STATUS_MARKERS = {'pending': '…', 'running': '▶', 'ok': '✓', 'fail': '✗',
                   'cancelled': '⊘'}
_STATS_FIELDS = [('stats_field_model', 'model'), ('stats_field_taxa', 'taxa'),
                 ('stats_field_lnl', 'lnL'), ('stats_field_gamma', 'gamma'),
                 ('stats_field_tstv', 'tstv'), ('stats_field_time', 'time')]
_SUMMARY_COLS = ['file', 'status', 'model', 'taxa', 'lnL', 'gamma', 'tstv', 'time']


class ResultsPanel(QTabWidget):
    """The Log / Statistics / Summary / Queue tabs under the tree viewer."""

    retry_clicked = Signal()   # "retry the failed files" in the queue tab

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log_console = LogConsole()
        self.addTab(self.log_console, _t("tab_log"))

        stats_tab = QWidget()
        stats_lay = QVBoxLayout(stats_tab)
        self.stats_file_label = QLabel("—")
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.horizontalHeader().setVisible(False)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        stats_lay.addWidget(self.stats_file_label)
        stats_lay.addWidget(self.stats_table)
        self.addTab(stats_tab, _t("tab_stats"))

        self.summary_table = QTableWidget(0, 8)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setAlternatingRowColors(True)
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 8):
            self.summary_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.addTab(self.summary_table, _t("tab_summary"))

        self.queue_tab = QWidget()
        queue_lay = QVBoxLayout(self.queue_tab)
        self.queue_list = QListWidget()
        self.queue_list.setAlternatingRowColors(True)
        self.retry_btn = QToolButton()
        self.retry_btn.setText(_t("btn_retry_failed"))
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self.retry_clicked)
        queue_lay.addWidget(self.queue_list, 1)
        queue_lay.addWidget(self.retry_btn)
        self.addTab(self.queue_tab, _t("tab_queue"))

    def begin_run(self, files: list) -> None:
        """A run of files starts: empty log, a pending queue; a batch shows the queue."""
        self.log_console.clear()
        self.retry_btn.setVisible(False)
        self.setCurrentWidget(self.log_console)
        self.queue_list.clear()
        for f in files:
            self.queue_list.addItem(os.path.basename(f) + '  …')
        if len(files) > 1:
            self.setCurrentWidget(self.queue_tab)

    def set_file_status(self, name: str, status: str) -> None:
        marker = _STATUS_MARKERS.get(status, '?')
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            if item.text().split('  ')[0] == name:
                item.setText(f'{name}  {marker}')
                return

    def show_result(self, result, rows: list) -> None:
        """The statistics of the last file that finished 'ok', and the summary rows."""
        done = [f for f in result.files if f.status == 'ok']
        if done:
            last = done[-1]
            self.stats_file_label.setText(_t("stats_field_file") + ': ' + os.path.basename(last.file))
            self.stats_table.setRowCount(len(_STATS_FIELDS))
            for i, (key, col) in enumerate(_STATS_FIELDS):
                self.stats_table.setItem(i, 0, QTableWidgetItem(_t(key)))
                self.stats_table.setItem(i, 1, QTableWidgetItem((last.stats or {}).get(col) or 'n/a'))
        self.summary_table.setColumnCount(len(_SUMMARY_COLS))
        self.summary_table.setHorizontalHeaderLabels([_t("sum_col_" + c) for c in _SUMMARY_COLS])
        self.summary_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, c in enumerate(_SUMMARY_COLS):
                self.summary_table.setItem(i, j, QTableWidgetItem(r.get(c) or ''))
