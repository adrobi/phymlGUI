from html import escape

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                             QLineEdit, QTextEdit)
from PySide6.QtGui import QFont

from phyml_core.i18n import _t


class LogConsole(QWidget):
    """Structured log: colored levels, severity filter, substring search.

    Every entry carries a level from phyml_core.runner.LEVELS ('error', 'success',
    'system', 'out'), given by whoever writes it. Entries are always stored in full;
    filtering only affects what is displayed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []  # (role, text)
        self._role_colors = {'error': '#E53935', 'success': '#43A047',
                             'system': '#1E9E6A', 'out': '#212121'}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        self.filter_box = QComboBox()
        self.filter_box.addItem(_t("log_filter_all"), "all")
        self.filter_box.addItem(_t("log_filter_error"), "error")
        self.filter_box.addItem(_t("log_filter_success"), "success")
        self.filter_box.addItem(_t("log_filter_system"), "system")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(_t("log_search"))
        self.filter_box.currentIndexChanged.connect(self._render)
        self.search_edit.textChanged.connect(self._render)
        bar.addWidget(self.filter_box)
        bar.addWidget(self.search_edit)
        layout.addLayout(bar)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont('Consolas', 9))
        layout.addWidget(self.view)

    def append(self, level: str, text: str) -> None:
        """Add an entry; a level this console has no color for is shown as 'out'."""
        if level not in self._role_colors:
            level = 'out'
        self._entries.append((level, text))
        if self._passes(level, text):
            self._append_html(text, level)

    def clear(self):
        self._entries.clear()
        self.view.clear()

    def toPlainText(self):
        return '\n'.join(t for _, t in self._entries)

    def _passes(self, role, text):
        flt = self.filter_box.currentData()
        if flt != 'all' and role != flt:
            return False
        needle = self.search_edit.text().strip().lower()
        return not needle or needle in text.lower()

    def set_role_colors(self, colors):
        self._role_colors = dict(colors)
        self._render()

    def _append_html(self, text, role):
        prefix = self._role_colors[role]
        weight = '600' if role == 'system' else '400'
        self.view.append(f'<span style="color:{prefix};font-weight:{weight}">'
                         f'{escape(text)}</span>')
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _render(self):
        self.view.clear()
        for role, text in self._entries:
            if self._passes(role, text):
                self._append_html(text, role)
