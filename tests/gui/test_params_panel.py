"""ParamsPanel: the parameter groups <-> a params dict."""
from phyml_core.engines import ENGINES
from phyml_ui.params_panel import ParamsPanel

FULL = {'datatype': 'aa', 'model': 'WAG', 'support_method': '-2',
        'bootstrap_replicates': '250', 'use_mpi': True, 'mpi_np': '3',
        'freq': 'm', 'tstv': '2.5', 'pinv': 'e', 'classes': '6', 'gamma': '0.7',
        'search': 'SPR', 'optimize': 'tl', 'parsimony': True}


def make_panel(qtbot, engine='phyml'):
    panel = ParamsPanel()
    qtbot.addWidget(panel)
    panel.set_engine(ENGINES[engine])
    return panel


def test_params_roundtrip(qtbot):
    panel = make_panel(qtbot)
    panel.set_params(FULL)
    assert panel.params() == FULL
    assert not panel.le_bootstrap_replicates.isEnabled(), 'aLRT: no replicates field'


def test_set_params_emits_changed_once(qtbot):
    panel = make_panel(qtbot)
    count = []
    panel.changed.connect(lambda: count.append(1))
    with qtbot.waitSignal(panel.changed, timeout=1000):
        panel.set_params(FULL)
    assert len(count) == 1


def test_set_engine_refills_models(qtbot):
    panel = make_panel(qtbot)
    assert panel.cb_model.itemData(0) == ENGINES['phyml'].models('nt')[0]
    panel.set_engine(ENGINES['iqtree'])
    models = [panel.cb_model.itemData(i) for i in range(panel.cb_model.count())]
    assert models == ENGINES['iqtree'].models('nt')
    assert panel.cb_model.currentData() == 'MFP'


def test_editing_a_field_emits_changed(qtbot):
    panel = make_panel(qtbot)
    with qtbot.waitSignal(panel.changed, timeout=1000):
        panel.le_tstv.setText('3')
    with qtbot.waitSignal(panel.changed, timeout=1000):
        panel.chk_use_mpi.toggle()
