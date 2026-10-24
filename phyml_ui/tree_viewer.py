import os

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure

from PySide6.QtWidgets import (QVBoxLayout, QWidget, QDialog, QHBoxLayout,
                             QToolButton, QLabel, QFileDialog)
from PySide6.QtGui import QIcon
from Bio import Phylo

from phyml_core.i18n import _t
from phyml_core.utils import resource_path


# --- Embeddable tree visualization widget ---
class TreeViewerWidget(QWidget):
    """Tree render with an explicit tool bar: the active tool (zoom / pan)
    is a checked button plus a text indicator, instead of the stock
    matplotlib toolbar whose state is invisible."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        # hidden stock toolbar drives the actual pan/zoom/home logic
        self.nav = NavigationToolbar2QT(self.canvas, self)
        self.nav.setVisible(False)
        self.ax = self.figure.add_subplot(111)
        self.tree_path = ""

        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.btn_home = QToolButton(); self.btn_home.setText(_t("tree_home"))
        self.btn_zoom = QToolButton(); self.btn_zoom.setText(_t("tree_zoom"))
        self.btn_zoom.setCheckable(True)
        self.btn_pan = QToolButton(); self.btn_pan.setText(_t("tree_pan"))
        self.btn_pan.setCheckable(True)
        self.btn_save = QToolButton(); self.btn_save.setText(_t("tree_export"))
        self.mode_label = QLabel("—")
        self.mode_label.setStyleSheet('font-weight: 600;')

        # no QButtonGroup: matplotlib allows exactly one active mode at a
        # time, and _sync_tools() enforces that on the buttons — an exclusive
        # group would veto programmatically unchecking the pressed button
        self.btn_home.clicked.connect(self._home)
        self.btn_zoom.clicked.connect(lambda: (self.nav.zoom(), self._sync_tools()))
        self.btn_pan.clicked.connect(lambda: (self.nav.pan(), self._sync_tools()))
        self.btn_save.clicked.connect(self._export)

        bar.addWidget(self.btn_home)
        bar.addWidget(self.btn_zoom)
        bar.addWidget(self.btn_pan)
        bar.addWidget(self.btn_save)
        bar.addStretch(1)
        bar.addWidget(QLabel(_t("tree_tool_label")))
        bar.addWidget(self.mode_label)
        layout.addLayout(bar)
        layout.addWidget(self.canvas, 1)

    def _sync_tools(self):
        mode = self.nav.mode or ''
        self.btn_zoom.setChecked(mode == 'zoom rect')
        self.btn_pan.setChecked(mode == 'pan/zoom')
        if mode == 'zoom rect':
            self.mode_label.setText(_t("tree_zoom"))
        elif mode == 'pan/zoom':
            self.mode_label.setText(_t("tree_pan"))
        else:
            self.mode_label.setText('—')

    def _home(self):
        self.nav.home()
        self._sync_tools()

    def _export(self):
        path, sel = QFileDialog.getSaveFileName(
            self, _t("tree_export"), os.path.splitext(os.path.basename(self.tree_path or 'tree'))[0],
            "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not path:
            return
        ext = sel.strip('()').split('*.')[-1].rstrip(')')
        if not path.lower().endswith('.' + ext):
            path += '.' + ext
        try:
            self.figure.savefig(path, dpi=200, bbox_inches='tight',
                                facecolor=self.figure.get_facecolor())
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, _t("tree_export"), str(e))

    def load_tree(self, tree_path):
        """(Re)render the tree; on failure shows the error inside the canvas."""
        self.tree_path = tree_path
        self.ax.clear()
        try:
            tree = Phylo.read(tree_path, "newick")
            def format_label(node):
                if node.is_terminal():
                    return node.name
                else:
                    if node.name:
                        try:
                            return str(round(float(node.name)))
                        except ValueError:
                            return node.name
                    return ""

            matplotlib.rcParams.update({'font.size': 9})
            Phylo.draw(tree, axes=self.ax, do_show=False, label_func=format_label)
            self.ax.set_title(_t("ml_tree"), pad=15, fontsize=12)
            self.figure.tight_layout()
            self.canvas.draw()
            matplotlib.rcParams.update({'font.size': 10})
            self._home()
        except Exception as e:
            self.ax.text(0.5, 0.5, _t("tree_error").format(e),
                         ha="center", va="center", color="red", fontsize=12)
            self.canvas.draw()


# --- Kept for backward compatibility: modal dialog wrapping the widget ---
class TreeViewerDialog(QDialog):
    def __init__(self, tree_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("tree_result").format(os.path.basename(tree_path)))
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(1200, 800)
        layout = QVBoxLayout(self)
        self.viewer = TreeViewerWidget(self)
        self.viewer.load_tree(tree_path)
        layout.addWidget(self.viewer)
