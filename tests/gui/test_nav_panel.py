"""NavPanel: recent files, presets and history lists and their signals."""
from PySide6.QtCore import Qt

from phyml_core import presets
from phyml_core.history import display_input
from phyml_core.i18n import _t
from phyml_ui.nav_panel import NavPanel


def double_click(qtbot, lst, row):
    item = lst.item(row)
    lst.scrollToItem(item)
    pos = lst.visualItemRect(item).center()
    qtbot.mouseClick(lst.viewport(), Qt.LeftButton, pos=pos)   # a view acts on the pressed row
    qtbot.mouseDClick(lst.viewport(), Qt.LeftButton, pos=pos)


def make_nav(qtbot):
    nav = NavPanel()
    qtbot.addWidget(nav)
    nav.resize(300, 600)
    nav.show()
    qtbot.waitExposed(nav)
    return nav


def test_nav_signals(qtbot):
    nav = make_nav(qtbot)
    user = {'mine': {'model': 'GTR', 'engine': 'iqtree'}}
    nav.set_presets(presets.BUILTIN, user)
    texts = [nav.presets_list.item(i).text() for i in range(nav.presets_list.count())]
    assert texts == [_t('preset_save_current'), *(_t(k) for k in presets.BUILTIN), 'mine']

    nav.setCurrentWidget(nav.presets_list)
    with qtbot.waitSignal(nav.preset_activated, timeout=1000) as sig:
        double_click(qtbot, nav.presets_list, 1)
    assert sig.args == [presets.BUILTIN[next(iter(presets.BUILTIN))]]
    assert nav.activated_preset_name == texts[1]
    with qtbot.waitSignal(nav.preset_activated, timeout=1000) as sig:
        double_click(qtbot, nav.presets_list, len(texts) - 1)
    assert sig.args == [user['mine']]
    with qtbot.waitSignal(nav.preset_save_requested, timeout=1000):
        double_click(qtbot, nav.presets_list, 0)

    records = [{'ts': '2020-01-01 10:00', 'input': 'a.fasta', 'ok': 1, 'n': 1},
               {'ts': '2020-01-02 10:00', 'input': 'b.fasta', 'ok': 0, 'n': 2}]
    nav.set_history(records)
    assert nav.history_list.item(1).text() == _t('hist_entry').format(
        '2020-01-02 10:00', display_input(records[1]), 0, 2)
    nav.setCurrentWidget(nav.history_list)
    with qtbot.waitSignal(nav.history_activated, timeout=1000) as sig:
        double_click(qtbot, nav.history_list, 0)
    assert sig.args == [0]


def test_recent_shows_names_and_emits_the_full_path(qtbot, tmp_path):
    nav = make_nav(qtbot)
    folder = tmp_path / 'batch'
    folder.mkdir()
    nav.set_recent([str(tmp_path / 'x.fasta'), str(folder)])
    assert [nav.recent_list.item(i).text() for i in range(2)] == ['x.fasta', 'batch/']
    nav.setCurrentWidget(nav.recent_list)
    with qtbot.waitSignal(nav.recent_activated, timeout=1000) as sig:
        double_click(qtbot, nav.recent_list, 1)
    assert sig.args == [str(folder)]


def test_emitted_preset_is_a_copy(qtbot):
    nav = make_nav(qtbot)
    nav.set_presets(presets.BUILTIN, {})
    got = []
    nav.preset_activated.connect(got.append)
    nav.presets_list.itemDoubleClicked.emit(nav.presets_list.item(1))
    got[0]['model'] = 'changed'
    assert presets.BUILTIN[next(iter(presets.BUILTIN))]['model'] != 'changed'
