"""Application QSS themes: light and dark with a shared accent color."""

ACCENT = '#1E9E6A'

_LIGHT = """
QWidget {{ background: {bg}; color: {text}; font-size: 13px; }}
QLineEdit, QComboBox, QTextEdit, QSpinBox {{
    background: {base}; border: 1px solid {border}; border-radius: 4px; padding: 3px 6px;
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {base}; selection-background-color: {accent}; selection-color: white; }}
QPushButton {{
    background: {button}; border: 1px solid {border}; border-radius: 4px; padding: 5px 12px;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:pressed {{ background: {border}; }}
QGroupBox {{
    font-weight: 600; border: 1px solid {border}; border-radius: 6px;
    margin-top: 10px; padding-top: 6px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {accent}; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 4px; }}
QTabBar::tab {{
    padding: 5px 14px; border: 1px solid {border};
    border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{ background: {base}; color: {accent}; font-weight: 600; }}
QTabBar::tab:!selected {{ background: {bg}; }}
QProgressBar {{ border: 1px solid {border}; border-radius: 4px; text-align: center; background: {base}; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
QStatusBar {{ background: {bg}; border-top: 1px solid {border}; }}
QSplitter::handle {{ background: {border}; width: 3px; }}
QToolBox::tab {{
    background: {button}; border-radius: 4px; padding: 4px; font-weight: 600;
}}
QToolBox::tab:selected {{ color: {accent}; }}
QListWidget {{ background: {base}; border: 1px solid {border}; border-radius: 4px; }}
QListWidget::item:selected {{ background: {accent}; color: white; }}
QListView::item:hover, QListWidget::item:hover {{ background: {hover}; }}
QScrollBar:vertical {{ background: {bg}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar:horizontal {{ background: {bg}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QTableWidget {{ background: {base}; border: 1px solid {border}; gridline-color: {border}; }}
QHeaderView::section {{ background: {button}; border: none; padding: 4px; font-weight: 600; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QToolTip {{ background: {base}; color: {text}; border: 1px solid {accent}; }}
"""

_DARK = _LIGHT  # same structure, palette swapped below

def _make(qss, **palette):
    return qss.format(**palette)

LIGHT_QSS = _make(_LIGHT,
    bg='#FAFAFA', base='#FFFFFF', text='#212121', border='#C9CDD3',
    button='#E9EBEE', hover='#E0F2EA', accent=ACCENT)

DARK_QSS = _make(_DARK,
    bg='#1E1F22', base='#26282D', text='#E6E8EB', border='#3C4048',
    button='#33363C', hover='#2C4A3E', accent='#37C894')

THEMES = {'light': LIGHT_QSS, 'dark': DARK_QSS}


def apply_theme(app, name):
    app.setStyleSheet(THEMES.get(name, LIGHT_QSS))
