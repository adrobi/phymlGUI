def test_window_builds(window):
    assert window.result_tabs.count() == 4
    assert window.presets_list.count() >= 3
    assert window.cpu_timer.isActive()
