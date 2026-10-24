import math
import os

import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection

from PySide6.QtWidgets import (QVBoxLayout, QWidget, QDialog, QHBoxLayout,
                             QToolButton, QLabel, QFileDialog, QComboBox,
                             QCheckBox, QSlider, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from Bio import Phylo
from Bio.Phylo.Consensus import majority_consensus

from phyml_core.i18n import _t
from phyml_core.utils import resource_path


# ---------- pure helpers (unit-testable) ----------

def canonical_split(clade, all_names, anchor):
    """One-sided split representation: the side NOT containing the anchor."""
    side = frozenset(t.name for t in clade.get_terminals())
    return side if anchor not in side else frozenset(all_names - side)


def tree_splits(tree):
    """All non-trivial splits of an unrooted tree, canonically represented."""
    names = {t.name for t in tree.get_terminals()}
    anchor = min(names)
    splits = set()
    for cl in tree.get_nonterminals():
        side = canonical_split(cl, names, anchor)
        if 1 < len(side) < len(names) - 1:
            splits.add(side)
    return splits


def rf_distance(tree_a, tree_b):
    """Robinson–Foulds distance and its normalized value [0..1]."""
    a, b = tree_splits(tree_a), tree_splits(tree_b)
    raw = len(a ^ b) // 2
    n = len(tree_a.get_terminals())
    norm = min(1.0, raw / (n - 3)) if n > 3 else 0.0
    return raw, norm


# --- Embeddable tree visualization widget ---
class TreeViewerWidget(QWidget):
    """Custom tree renderer with three layouts, support threshold
    highlighting, clade collapsing, outgroup rerooting, consensus and
    RF comparison. Zoom/pan tool state is visible on the buttons."""

    LAYOUTS = ('rect', 'slanted', 'circle')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure()
        self.figure.patch.set_alpha(0.0)
        self.canvas = FigureCanvas(self.figure)
        self.nav = NavigationToolbar2QT(self.canvas, self)  # hidden: drives zoom/pan
        self.nav.setVisible(False)
        self.ax = self.figure.add_subplot(111)
        self.tree = None
        self.tree_title = ""
        self.tree_path = ""
        self.layout = 'rect'
        self.show_supports = True
        self.threshold = 0          # 0 = highlighting off
        self.show_grid = True
        self.outgroup = None
        self._collapsed = set()     # frozensets of terminal names
        self._coords = None         # (tree, coords) of the last render
        self._leaf_order = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        tools = QHBoxLayout()
        self.btn_home = QToolButton(); self.btn_home.setText(_t("tree_home"))
        self.btn_zoom = QToolButton(); self.btn_zoom.setText(_t("tree_zoom"))
        self.btn_zoom.setCheckable(True)
        self.btn_pan = QToolButton(); self.btn_pan.setText(_t("tree_pan"))
        self.btn_pan.setCheckable(True)
        self.btn_save = QToolButton(); self.btn_save.setText(_t("tree_export"))
        self.mode_label = QLabel("—")
        self.mode_label.setStyleSheet('font-weight: 600;')
        self.btn_home.clicked.connect(self._home)
        self.btn_zoom.clicked.connect(lambda: (self.nav.zoom(), self._sync_tools()))
        self.btn_pan.clicked.connect(lambda: (self.nav.pan(), self._sync_tools()))
        self.btn_save.clicked.connect(self._export)
        for w in (self.btn_home, self.btn_zoom, self.btn_pan, self.btn_save):
            tools.addWidget(w)
        tools.addStretch(1)
        tools.addWidget(QLabel(_t("tree_tool_label")))
        tools.addWidget(self.mode_label)
        layout.addLayout(tools)

        opts = QHBoxLayout()
        self.layout_combo = QComboBox()
        self.layout_combo.addItem(_t("tree_layout_rect"), 'rect')
        self.layout_combo.addItem(_t("tree_layout_slant"), 'slanted')
        self.layout_combo.addItem(_t("tree_layout_circ"), 'circle')
        self.layout_combo.currentIndexChanged.connect(
            lambda _: self.set_layout(self.layout_combo.currentData()))
        self.chk_supports = QCheckBox(_t("tree_supports"))
        self.chk_supports.setChecked(True)
        self.chk_supports.toggled.connect(self._rerender)
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(0)
        self.threshold_slider.setMaximumWidth(120)
        self.threshold_slider.valueChanged.connect(self._threshold_changed)
        self.threshold_label = QLabel(_t("tree_threshold").format(0))
        self.chk_grid = QCheckBox(_t("tree_grid"))
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self._rerender)
        self.outgroup_combo = QComboBox()
        self.outgroup_combo.setMinimumWidth(110)
        self.outgroup_combo.currentIndexChanged.connect(self._outgroup_changed)
        self.btn_consensus = QToolButton(); self.btn_consensus.setText(_t("btn_consensus"))
        self.btn_consensus.clicked.connect(self._consensus)
        self.btn_compare = QToolButton(); self.btn_compare.setText(_t("btn_compare"))
        self.btn_compare.clicked.connect(self._compare)

        opts.addWidget(QLabel(_t("tree_layout")))
        opts.addWidget(self.layout_combo)
        opts.addWidget(self.chk_supports)
        opts.addWidget(self.threshold_label)
        opts.addWidget(self.threshold_slider)
        opts.addWidget(self.chk_grid)
        opts.addStretch(1)
        opts.addWidget(QLabel(_t("tree_outgroup")))
        opts.addWidget(self.outgroup_combo)
        opts.addWidget(self.btn_consensus)
        opts.addWidget(self.btn_compare)
        layout.addLayout(opts)

        layout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect('button_press_event', self._on_click)
        self._draw_empty_hint()

    # ---------- toolbar plumbing ----------

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
            self, _t("tree_export"),
            os.path.splitext(os.path.basename(self.tree_path or 'tree'))[0],
            "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not path:
            return
        ext = sel.strip('()').split('*.')[-1].rstrip(')')
        if not path.lower().endswith('.' + ext):
            path += '.' + ext
        try:
            self.figure.savefig(path, dpi=200, bbox_inches='tight',
                                facecolor='white')
        except Exception as e:
            QMessageBox.warning(self, _t("tree_export"), str(e))

    # ---------- options handlers ----------

    def set_layout(self, name):
        if name in self.LAYOUTS:
            self.layout = name
            self._rerender()

    def _threshold_changed(self, value):
        self.threshold = value
        self.threshold_label.setText(_t("tree_threshold").format(value))
        self._rerender()

    def _outgroup_changed(self):
        data = self.outgroup_combo.currentData()
        self.outgroup = data if data else None
        self._rerender()

    # ---------- data loading ----------

    def load_tree(self, tree_path):
        try:
            self.tree = Phylo.read(tree_path, "newick")
            self.tree_path = tree_path
            self.tree_title = os.path.basename(tree_path)
            self._collapsed.clear()
            self._fill_outgroup_combo()
            self._rerender()
            self._home()
        except Exception as e:
            self._draw_error(e)

    def load_tree_object(self, tree, title):
        self.tree = tree
        self.tree_path = ""
        self.tree_title = title
        self._collapsed.clear()
        self._fill_outgroup_combo()
        self._rerender()
        self._home()

    def _fill_outgroup_combo(self):
        self.outgroup_combo.blockSignals(True)
        self.outgroup_combo.clear()
        self.outgroup_combo.addItem(_t("tree_outgroup_none"), None)
        if self.tree is not None:
            for t in sorted(self.tree.get_terminals(), key=lambda x: x.name or ''):
                self.outgroup_combo.addItem(t.name, t.name)
        self.outgroup_combo.blockSignals(False)
        self.outgroup = None

    # ---------- consensus & RF ----------

    def _consensus(self):
        start_dir = os.path.dirname(self.tree_path) if self.tree_path else ""
        path, _ = QFileDialog.getOpenFileName(
            self, _t("btn_consensus"), start_dir, "Bootstrap trees (*_boot_trees.txt);;Newick (*.txt *.tree *.nwk);;All files (*.*)")
        if not path:
            return
        try:
            trees = list(Phylo.parse(path, 'newick'))
            if not trees:
                raise ValueError("no trees in file")
            cons = majority_consensus(trees)
            self.load_tree_object(cons, _t("consensus_from").format(len(trees)))
        except Exception as e:
            QMessageBox.warning(self, _t("btn_consensus"), str(e))

    def _compare(self):
        a_path, _ = QFileDialog.getOpenFileName(self, _t("tree_pick1"), "", "Newick (*.txt *.tree *.nwk);;All files (*.*)")
        if not a_path:
            return
        b_path, _ = QFileDialog.getOpenFileName(self, _t("tree_pick2"), os.path.dirname(a_path), "Newick (*.txt *.tree *.nwk);;All files (*.*)")
        if not b_path:
            return
        try:
            raw, norm = rf_distance(Phylo.read(a_path, 'newick'), Phylo.read(b_path, 'newick'))
            QMessageBox.information(self, _t("rf_title"), _t("rf_result").format(raw, int(round(norm * 100))))
        except Exception as e:
            QMessageBox.warning(self, _t("rf_title"), str(e))

    # ---------- collapsing ----------

    def collapse_clade(self, names):
        """Toggle collapse for the clade spanned exactly by these names."""
        key = frozenset(names)
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        self._rerender()

    def _on_click(self, event):
        if event.dblclick and event.inaxes == self.ax and self._coords:
            clade_names = self._clade_at(event.xdata, event.ydata)
            if clade_names and 1 < len(clade_names) < len(self._leaf_order):
                self.collapse_clade(clade_names)

    # ---------- layout computation ----------

    def _prep_tree(self):
        t = self.tree
        if self.outgroup:
            try:
                t = self.tree.copy()
                t.root_with_outgroup(self.outgroup)
            except Exception:
                t = self.tree
        return t

    def _compute_layout(self, tree):
        """Assign (x, y) or (r, angle) to every displayed node.
        Collapsed clades become single display leaves."""
        leaves = tree.get_terminals()
        n = len(leaves)

        def is_collapsed(cl):
            return frozenset(t.name for t in cl.get_terminals()) in self._collapsed

        display_leaves = []
        def walk(cl):
            if cl.is_terminal() or is_collapsed(cl):
                display_leaves.append(cl)
                return
            for c in cl.clades:
                walk(c)
        walk(tree.root)

        y_of = {}
        for i, cl in enumerate(display_leaves):
            y_of[id(cl)] = (n - 1 - i) if self.layout != 'circle' else None
        # circular: angle per display leaf
        m = len(display_leaves)
        ang_of = {id(cl): (i + 0.5) / m * 2 * 3.141592653589793
                  for i, cl in enumerate(display_leaves)}

        def depth(cl, parent_d):
            return parent_d + (cl.branch_length or 0.0)

        coords = {}      # id(clade) -> (x, y) or (r, ang)
        max_x = [0.0]

        def assign(cl, pd):
            x = depth(cl, pd)
            max_x[0] = max(max_x[0], x)
            if id(cl) in y_of or id(cl) in ang_of:
                if self.layout == 'circle':
                    coords[id(cl)] = (x, ang_of[id(cl)])
                else:
                    coords[id(cl)] = (x, y_of[id(cl)])
                return coords[id(cl)]
            child_pos = [assign(c, x) for c in cl.clades]
            if self.layout == 'circle':
                r = max(p[0] for p in child_pos)
                ang = sum(p[1] for p in child_pos) / len(child_pos)
                # average angle over the shortest arc
                angs = sorted(p[1] for p in child_pos)
                best, best_span = None, 1e9
                for i, a0 in enumerate(angs):
                    a1 = angs[(i - 1) % len(angs)]  # predecessor going backwards
                    span = (a0 - a1) % (2 * 3.141592653589793)
                    if span < best_span:
                        best_span, best = span, (a1 + span / 2) % (2 * 3.141592653589793)
                coords[id(cl)] = (r, best)
            else:
                x_c = max(p[0] for p in child_pos)
                y_c = sum(p[1] for p in child_pos) / len(child_pos)
                coords[id(cl)] = (x_c, y_c)
            return coords[id(cl)]

        assign(tree.root, 0.0)
        self._leaf_order = [cl.name or '' for cl in display_leaves]
        return coords, max_x[0], display_leaves

    # ---------- rendering ----------

    def _rerender(self):
        if self.tree is None:
            return
        try:
            self._render()
        except Exception as e:
            self._draw_error(e)

    def _render(self):
        self.ax.clear()
        self._coords = None
        tree = self._prep_tree()
        coords, max_x, display_leaves = self._compute_layout(tree)
        self._coords = (tree, coords)
        accent = '#1E9E6A'
        text = '#424242'
        faint = '#B9BEC4'

        def support_of(cl):
            if cl.confidence is not None:
                return float(cl.confidence)
            try:
                return float(cl.name)
            except (TypeError, ValueError):
                return None

        def edge_color(cl):
            s = support_of(cl)
            if self.threshold > 0 and s is not None:
                return accent if s >= self.threshold else faint
            return text

        segments, colors = [], []
        circ = self.layout == 'circle'

        def draw_edges(cl, parent_pos):
            x, a = coords[id(cl)]
            if circ:
                cx, cy = x * math.cos(a), x * math.sin(a)
                segments.append([parent_pos, (cx, cy)])
                colors.append(edge_color(cl))
                for c in cl.clades:
                    draw_edges(c, (cx, cy))
            else:
                x, y = coords[id(cl)]
                px, py = parent_pos
                if self.layout == 'rect':
                    segments.append([(px, py), (px, y)])   # elbow at parent's x
                    segments.append([(px, y), (x, y)])
                else:
                    segments.append([(px, py), (x, y)])
                colors.append(edge_color(cl))
                for c in cl.clades:
                    draw_edges(c, (x, y))

        root = tree.root
        rx, ra = coords[id(root)]
        if circ:
            cx, cy = rx * math.cos(ra), rx * math.sin(ra)
            segments.append([(0.0, 0.0), (cx, cy)])
            colors.append(edge_color(root))
            for c in root.clades:
                draw_edges(c, (cx, cy))
        elif self.layout == 'rect':
            segments.append([(0.0, ra), (rx, ra)])
            colors.append(edge_color(root))
            for c in root.clades:
                draw_edges(c, (rx, ra))
        else:  # slanted: children radiate from the origin point
            for c in root.clades:
                draw_edges(c, (0.0, ra))

        lc = LineCollection(segments, colors=colors, linewidths=1.4, zorder=2)
        self.ax.add_collection(lc)

        # leaf labels
        for cl in display_leaves:
            x, a = coords[id(cl)]
            if circ:
                lx, ly = (x + max_x * 0.02) * math.cos(a), (x + max_x * 0.02) * math.sin(a)
                ha = 'left' if math.cos(a) >= 0 else 'right'
                self.ax.text(lx, ly, cl.name or '', fontsize=8, color=text,
                             ha=ha, va='center', zorder=3)
            else:
                self.ax.text(x + max_x * 0.01, a, cl.name or '', fontsize=8,
                             color=text, va='center', zorder=3)

        # support labels on internal nodes
        if self.show_supports:
            for cl in tree.get_nonterminals():
                if id(cl) not in coords:
                    continue
                s = support_of(cl)
                if s is None:
                    continue
                x, a = coords[id(cl)]
                if circ:
                    lx, ly = x * math.cos(a), x * math.sin(a)
                else:
                    lx, ly = x, a
                color = accent if (self.threshold > 0 and s >= self.threshold) else text
                self.ax.text(lx, ly, f"{s:.0f}" if s > 1 else f"{s:.2f}",
                             fontsize=7, color=color, style='italic',
                             ha='center', va='bottom', zorder=3)

        # scale bar (rect/slanted) or subtle rings (circular)
        if circ:
            step = 10 ** (len(str(int(max_x))) - 1) if max_x >= 1 else 0.01
            ring = step
            while ring < max_x * 1.05:
                self.ax.add_patch(_ring(ring))
                ring += step
        else:
            bar = max_x * 0.15 if max_x > 0 else 0.0
            ys = [p[1] for p in coords.values()]
            y0 = min(ys) - (max(ys) - min(ys)) * 0.06 - 1
            self.ax.plot([0, bar], [y0, y0], color=text, lw=1.2, zorder=3)
            self.ax.text(bar / 2, y0 - 0.4, f"{bar:.3g}", fontsize=7,
                         color=text, ha='center', zorder=3)

        if self.show_grid and not circ:
            self.ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.3, zorder=0)
        self.ax.set_axis_off()
        if circ:
            lim = max_x * 1.3
            self.ax.set_xlim(-lim, lim); self.ax.set_ylim(-lim, lim)
            self.ax.set_aspect('equal')
        else:
            xs = [p[0] for p in coords.values()]
            ys = [p[1] for p in coords.values()]
            self.ax.set_xlim(min(xs) - 0.05, max(xs) * 1.25 + 0.1)
            self.ax.set_ylim(min(ys) - 1.5, max(ys) + 0.8)
        self.ax.set_title(self.tree_title, fontsize=10, pad=8)
        self.canvas.draw_idle()

    def _clade_at(self, x, y):
        """Innermost displayed clade whose bbox contains the point."""
        if not self._coords:
            return None
        tree, coords = self._coords
        best = None

        def to_xy(p):
            if self.layout == 'circle':
                return (p[0] * math.cos(p[1]), p[0] * math.sin(p[1]))
            return (p[0], p[1])

        def walk(cl):
            nonlocal best
            if cl.is_terminal():
                return
            xs, ys = [], []
            def collect(c):
                if id(c) in coords:
                    px, py = to_xy(coords[id(c)])
                    xs.append(px); ys.append(py)
                for c2 in c.clades:
                    collect(c2)
            collect(cl)
            if xs and min(xs) - 1e-9 <= x <= max(xs) + 1e-9 and min(ys) - 1e-9 <= y <= max(ys) + 1e-9:
                best = cl
            for c in cl.clades:
                walk(c)
        walk(tree.root)
        if best is None:
            return None
        return frozenset(t.name for t in best.get_terminals())

    # ---------- empty / error states ----------

    def _draw_empty_hint(self):
        self.ax.clear()
        self.ax.set_axis_off()
        self.ax.text(0.5, 0.5, _t("tree_empty"), ha='center', va='center',
                     fontsize=12, color='#9AA0A6', transform=self.ax.transAxes)
        self.canvas.draw_idle()

    def _draw_error(self, e):
        self.ax.clear()
        self.ax.set_axis_off()
        self.ax.text(0.5, 0.5, _t("tree_error").format(e), ha='center',
                     va='center', color='red', fontsize=12,
                     transform=self.ax.transAxes)
        self.canvas.draw_idle()


def _ring(radius):
    import matplotlib.patches as mpatches
    return mpatches.Circle((0, 0), radius, fill=False,
                           linestyle=':', linewidth=0.5, color='#B9BEC4')


# --- Kept for backward compatibility: modal dialog wrapping the widget ---
class TreeViewerDialog(QDialog):
    def __init__(self, tree_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("tree_result").format(os.path.basename(tree_path)))
        self.setWindowIcon(QIcon(resource_path('icon.png')))
        self.resize(1200, 800)
        layout = QVBoxLayout(self)
        self.viewer = TreeViewerWidget()
        self.viewer.load_tree(tree_path)
        layout.addWidget(self.viewer)
