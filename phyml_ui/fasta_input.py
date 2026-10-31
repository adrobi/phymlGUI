import os

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QFileDialog)
from PySide6.QtCore import Signal

from phyml_core import alignment
from phyml_core.i18n import _t

FASTA_SUFFIXES = ('.fasta', '.fas', '.fa')


def batch_files(folder: str) -> list:
    """The FASTA files of a batch folder, sorted, full paths. *_aligned.fasta are left out:
    those are this app's own MUSCLE outputs."""
    return [os.path.join(folder, f) for f in sorted(os.listdir(folder))
            if f.lower().endswith(FASTA_SUFFIXES) and not f.lower().endswith('_aligned.fasta')]


class FastaInput(QWidget):
    """The input field (a FASTA file or a batch folder), its two pickers and a one-line
    summary of what the field points at."""

    path_chosen = Signal(str)   # picked in a file or folder dialog

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(QLabel(_t("input_fasta")))
        self.path_edit = QLineEdit()
        btn_fasta = QPushButton(_t("btn_select_fasta"))
        btn_fasta.clicked.connect(self._browse_file)
        btn_fasta_dir = QPushButton(_t("btn_select_dir"))
        btn_fasta_dir.clicked.connect(self._browse_dir)
        row = QHBoxLayout(); row.addWidget(self.path_edit, 1)
        row.addWidget(btn_fasta); row.addWidget(btn_fasta_dir)
        v.addLayout(row)
        self.info_label = QLabel(' ')
        self.info_label.setStyleSheet('color: #9AA0A6;')
        self.path_edit.textChanged.connect(self._update_info)
        v.addWidget(self.info_label)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("file_fasta"), "", "FASTA Files (*.fasta *.fas *.fa)")
        if path:
            self.path_chosen.emit(path)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, _t("file_dir"))
        if path:
            self.path_chosen.emit(path)

    def _update_info(self, path):
        """Quick alignment summary under the field."""
        try:
            if not path or not os.path.exists(path):
                self.info_label.setText(' ')
            elif os.path.isdir(path):
                self.info_label.setText(_t('fasta_info').format(len(batch_files(path)), '—', '—', '—'))
            else:
                info = alignment.summarize(path)  # an empty or broken file raises: no label
                self.info_label.setText(_t('fasta_info').format(
                    info['n'], info['min_len'], info['max_len'], info['gap_pct']))
        except Exception:
            self.info_label.setText(' ')
