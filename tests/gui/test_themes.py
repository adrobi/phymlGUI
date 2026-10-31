from phyml_ui.themes import resolve, build_qss, role_colors, ACCENTS, system_theme


def test_resolve_qss_and_role_colors():
    theme, accent = resolve('dark', 'blue')
    assert theme == 'dark' and accent == ACCENTS['blue']
    qss = build_qss(theme, accent)
    assert accent in qss and 'QPushButton#btn_run' in qss
    assert role_colors(theme, accent)['out'] == '#E6E8EB'
    assert system_theme() in ('light', 'dark')


def test_system_theme_without_winreg(qapp, monkeypatch):
    """Off Windows the system theme follows the lightness of the Qt palette."""
    from PySide6.QtGui import QColor, QPalette
    from phyml_ui import themes
    monkeypatch.setattr(themes, 'winreg', None)
    saved = qapp.palette()
    try:
        dark = QPalette(saved)
        dark.setColor(QPalette.Window, QColor('#202124'))
        qapp.setPalette(dark)
        assert themes.system_theme() == 'dark'
        light = QPalette(saved)
        light.setColor(QPalette.Window, QColor('#F5F5F5'))
        qapp.setPalette(light)
        assert themes.system_theme() == 'light'
    finally:
        qapp.setPalette(saved)
