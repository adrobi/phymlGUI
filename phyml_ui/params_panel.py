from typing import Optional

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QComboBox, QLineEdit, QCheckBox, QGroupBox, QLabel)
from PySide6.QtCore import Signal

from phyml_core.engines.base import Engine
from phyml_core.i18n import _t

# params() keys, in the order the settings file has always listed them
_COMBOS = ('datatype', 'model', 'support_method')
_TEXTS = ('tstv', 'pinv', 'classes', 'gamma')


def set_combo_by_data(combo, data_val):
    """Select the item whose data is data_val; an unknown value leaves the combo alone."""
    idx = combo.findData(data_val)
    if idx >= 0: combo.setCurrentIndex(idx)


class ParamsPanel(QWidget):
    """The model, evolution and tree-search groups, shown as and read back from a params
    dict: the PRESET_KEYS without 'engine', plus 'use_mpi' and 'mpi_np'.

    changed is emitted once for every edit, and once for a whole set_params / set_engine.
    """

    changed = Signal()

    def __init__(self, default_np: int = 1, parent=None):
        super().__init__(parent)
        self._engine: Optional[Engine] = None
        self._quiet = 0   # > 0 while fields are filled programmatically: no changed per field
        pv = QVBoxLayout(self)
        pv.setContentsMargins(0, 0, 4, 0)
        pv.setSpacing(10)

        gb_model = QGroupBox(_t("tab_model"))
        form_basic = QFormLayout(gb_model)
        self.chk_use_mpi = QCheckBox(_t("lbl_use_mpi"))
        self.le_mpi_np = QLineEdit(str(default_np))
        self.le_mpi_np.setFixedWidth(50)
        mpi_hbox = QHBoxLayout(); mpi_hbox.addWidget(self.chk_use_mpi)
        mpi_hbox.addWidget(QLabel(_t("lbl_mpi_np"))); mpi_hbox.addWidget(self.le_mpi_np)
        mpi_hbox.addStretch()
        form_basic.addRow(_t("mode_mpi"), mpi_hbox)

        self.cb_datatype = QComboBox()
        self.cb_datatype.addItem(_t("dt_nt"), "nt")
        self.cb_datatype.addItem(_t("dt_aa"), "aa")
        form_basic.addRow(_t("lbl_dt"), self.cb_datatype)

        self.cb_model = QComboBox()
        form_basic.addRow(_t("lbl_model"), self.cb_model)

        self.cb_support_method = QComboBox()
        self.cb_support_method.addItem(_t("supp_boot"), "bootstrap")
        self.cb_support_method.addItem(_t("supp_alrt1"), "-1"); self.cb_support_method.addItem(_t("supp_alrt2"), "-2")
        self.cb_support_method.addItem(_t("supp_alrt4"), "-4"); self.cb_support_method.addItem(_t("supp_none"), "0")
        form_basic.addRow(_t("lbl_supp"), self.cb_support_method)

        self.le_bootstrap_replicates = QLineEdit("100")
        form_basic.addRow(_t("lbl_boot"), self.le_bootstrap_replicates)
        pv.addWidget(gb_model)

        gb_evo = QGroupBox(_t("tab_evo"))
        form_model = QFormLayout(gb_evo)
        self.cb_freq = QComboBox()
        self.cb_freq.addItem(_t("freq_def"), "default"); self.cb_freq.addItem(_t("freq_emp"), "e"); self.cb_freq.addItem(_t("freq_ml"), "m")
        form_model.addRow(_t("lbl_freq"), self.cb_freq)
        self.le_tstv = QLineEdit("e"); form_model.addRow(_t("lbl_tstv"), self.le_tstv)
        self.le_pinv = QLineEdit("0.0"); form_model.addRow(_t("lbl_pinv"), self.le_pinv)
        self.le_classes = QLineEdit("4"); form_model.addRow(_t("lbl_classes"), self.le_classes)
        self.le_gamma = QLineEdit("e"); form_model.addRow(_t("lbl_gamma"), self.le_gamma)
        pv.addWidget(gb_evo)

        gb_search = QGroupBox(_t("tab_search"))
        form_tree = QFormLayout(gb_search)
        self.cb_search = QComboBox()
        self.cb_search.addItem(_t("search_nni"), "NNI"); self.cb_search.addItem(_t("search_spr"), "SPR"); self.cb_search.addItem(_t("search_best"), "BEST")
        form_tree.addRow(_t("lbl_search"), self.cb_search)
        self.cb_optimize = QComboBox()
        self.cb_optimize.addItem(_t("opt_tlr"), "tlr"); self.cb_optimize.addItem(_t("opt_tl"), "tl"); self.cb_optimize.addItem(_t("opt_lr"), "lr")
        self.cb_optimize.addItem(_t("opt_l"), "l"); self.cb_optimize.addItem(_t("opt_r"), "r"); self.cb_optimize.addItem(_t("opt_n"), "n")
        form_tree.addRow(_t("lbl_opt"), self.cb_optimize)
        self.chk_parsimony = QCheckBox(_t("chk_pars"))
        form_tree.addRow(self.chk_parsimony)
        pv.addWidget(gb_search)
        pv.addStretch(1)

        self.cb_datatype.currentIndexChanged.connect(self._datatype_changed)
        self.cb_support_method.currentIndexChanged.connect(self._toggle_bootstrap_input)
        for combo in (self.cb_model, self.cb_support_method, self.cb_freq,
                      self.cb_search, self.cb_optimize):
            combo.currentIndexChanged.connect(self._field_changed)
        for edit in (self.le_mpi_np, self.le_bootstrap_replicates, self.le_tstv,
                     self.le_pinv, self.le_classes, self.le_gamma):
            edit.textChanged.connect(self._field_changed)
        for check in (self.chk_use_mpi, self.chk_parsimony):
            check.toggled.connect(self._field_changed)

    # ---------- public ----------

    def set_engine(self, engine: Engine) -> None:
        """Show the model list of engine for the current data type."""
        self._engine = engine
        self._quiet += 1
        try:
            self._refill_models()
        finally:
            self._quiet -= 1
        self.changed.emit()

    def params(self) -> dict:
        p = {key: self._combo(key).currentData() for key in _COMBOS}
        p['bootstrap_replicates'] = self.le_bootstrap_replicates.text()
        p['use_mpi'] = self.chk_use_mpi.isChecked()
        p['mpi_np'] = self.le_mpi_np.text()
        p['freq'] = self.cb_freq.currentData()
        p.update({key: self._edit(key).text() for key in _TEXTS})
        p['search'] = self.cb_search.currentData()
        p['optimize'] = self.cb_optimize.currentData()
        p['parsimony'] = self.chk_parsimony.isChecked()
        return p

    def set_params(self, params: dict) -> None:
        """Show the keys of params() that params has; changed is emitted once, at the end."""
        self._quiet += 1
        try:
            if 'datatype' in params:
                set_combo_by_data(self.cb_datatype, params['datatype'])
                self._refill_models()   # the old type's list would not hold the model
            for key in ('model', 'freq', 'support_method', 'search', 'optimize'):
                if key in params:
                    set_combo_by_data(self._combo(key), params[key])
            for key in ('bootstrap_replicates', 'mpi_np', *_TEXTS):
                if key in params:
                    self._edit(key).setText(params[key])
            if 'use_mpi' in params:
                self.chk_use_mpi.setChecked(params['use_mpi'])
            if 'parsimony' in params:
                self.chk_parsimony.setChecked(params['parsimony'])
            self._toggle_bootstrap_input()
        finally:
            self._quiet -= 1
        self.changed.emit()

    # ---------- internals ----------

    def _combo(self, key):
        return getattr(self, 'cb_' + key)

    def _edit(self, key):
        return getattr(self, 'le_' + key)

    def _refill_models(self):
        self.cb_model.clear()
        if self._engine is not None:
            for m in self._engine.models(self.cb_datatype.currentData()):
                self.cb_model.addItem(m, m)

    def _datatype_changed(self):
        self._quiet += 1
        try:
            self._refill_models()
        finally:
            self._quiet -= 1
        self._field_changed()

    def _toggle_bootstrap_input(self):
        is_bootstrap = self.cb_support_method.currentData() == "bootstrap"
        self.le_bootstrap_replicates.setEnabled(is_bootstrap)

    def _field_changed(self, *args):
        if not self._quiet:
            self.changed.emit()
