from phyml_ui.log_console import LogConsole


def test_plain_text_keeps_every_entry(qtbot):
    log = LogConsole()
    qtbot.addWidget(log)
    log.append('error', 'bad')
    log.append('out', 'raw')
    assert log.toPlainText() == 'bad\nraw'
    assert not hasattr(log, '_classify'), 'the level comes from the caller, not the text'


def test_levels_drive_colors_and_filter(qtbot):
    log = LogConsole()
    qtbot.addWidget(log)
    log.set_role_colors({'error': '#ff0000', 'success': '#00ff00',
                         'system': '#0000ff', 'out': '#123456'})
    log.append('error', 'x')
    log.append('out', 'y')
    log.append('system', '[ERROR] looks like an error but is system')
    html = log.view.toHtml().lower()
    assert '#ff0000' in html and '#123456' in html
    idx = log.filter_box.findData('error')
    log.filter_box.setCurrentIndex(idx)
    shown = log.view.toPlainText()
    assert 'x' in shown.splitlines()
    assert 'y' not in shown.splitlines()
    assert '[ERROR] looks like' not in shown
    log.filter_box.setCurrentIndex(log.filter_box.findData('system'))
    assert log.view.toPlainText() == '[ERROR] looks like an error but is system'
