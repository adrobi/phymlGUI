from phyml_ui.themes import resolve, build_qss, role_colors, ACCENTS, system_theme


def test_resolve_qss_and_role_colors():
    theme, accent = resolve('dark', 'blue')
    assert theme == 'dark' and accent == ACCENTS['blue']
    qss = build_qss(theme, accent)
    assert accent in qss and 'QPushButton#btn_run' in qss
    assert role_colors(theme, accent)['out'] == '#E6E8EB'
    assert system_theme() in ('light', 'dark')
