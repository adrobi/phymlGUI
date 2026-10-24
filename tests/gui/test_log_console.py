from phyml_ui.main_window import LogConsole


def test_roles_and_plain_text(qtbot):
    log = LogConsole()
    qtbot.addWidget(log)
    assert log._classify('[ERROR] bad') == 'error'
    assert log._classify('[+] done') == 'success'
    assert log._classify('[*] system line') == 'system'
    assert log._classify('. PhyML raw output') == 'out'
    log.append('[ERROR] bad')
    log.append('raw')
    assert '[ERROR] bad' in log.toPlainText() and 'raw' in log.toPlainText()
