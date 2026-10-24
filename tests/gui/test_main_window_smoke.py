from phyml_ui.main_window import PhyMLApp


def test_window_builds(isolated_config, qtbot):
    # isolated_config goes first so it is torn down last: qtbot closes the
    # window at teardown and closeEvent still writes the (patched) config file
    w = PhyMLApp()
    qtbot.addWidget(w)
    assert w.result_tabs.count() == 4
    assert w.presets_list.count() >= 3
    assert w.cpu_timer.isActive()
