import os

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure

from PySide6.QtWidgets import QVBoxLayout, QWidget, QDialog
from PySide6.QtGui import QIcon
from Bio import Phylo

from phyml_core.i18n import _t
from phyml_core.utils import resource_path


# --- Embeddable tree visualization widget ---
class TreeViewerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self.tree_path = ""

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
