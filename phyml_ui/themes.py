"""Application QSS themes: light and dark with a shared accent color."""

ACCENT = '#1E9E6A'

_BASE = """
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
QPushButton:disabled {{ background: {bg}; color: {muted}; border-color: {border}; }}
QPushButton#btn_run {{
    background: {run_bg}; color: {run_fg}; font-weight: 600;
    border: none; border-radius: 4px; padding: 8px 18px;
}}
QPushButton#btn_run:hover {{ background: {run_hover}; }}
QPushButton#btn_run:disabled {{ background: {border}; color: {muted}; }}
QPushButton#btn_cancel {{
    background: {cancel_bg}; color: {cancel_fg}; font-weight: 600;
    border: none; border-radius: 4px; padding: 8px 18px;
}}
QPushButton#btn_cancel:hover {{ background: {cancel_hover}; }}
QPushButton#btn_cancel:disabled {{ background: {border}; color: {muted}; }}
QToolButton {{
    background: {button}; border: 1px solid {border}; border-radius: 4px; padding: 4px 10px;
}}
QToolButton:hover {{ border-color: {accent}; }}
QToolButton:pressed, QToolButton:checked {{ background: {accent}; color: white; }}
QGroupBox {{
    font-weight: 600; border: 1px solid {border}; border-radius: 6px;
    margin-top: 10px; padding-top: 6px; background: {group};
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
QStatusBar::item {{ border: none; }}
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
QTableWidget {{ background: {base}; border: 1px solid {border}; gridline-color: {border};
    alternate-background-color: {alt}; }}
QHeaderView::section {{ background: {button}; border: none; padding: 4px; font-weight: 600; }}
QDialog {{ background: {bg}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QToolTip {{ background: {base}; color: {text}; border: 1px solid {accent}; }}
QScrollArea {{ border: none; }}
"""

LIGHT_QSS = _BASE.format(
    bg='#FAFAFA', base='#FFFFFF', text='#212121', border='#C9CDD3',
    button='#E9EBEE', hover='#E0F2EA', group='#FFFFFF', alt='#F3F6F5',
    muted='#9AA0A6', accent=ACCENT,
    run_bg='#B7DFC5', run_fg='#1E4620', run_hover='#A3D5B5',
    cancel_bg='#F1BDBD', cancel_fg='#6E1B1B', cancel_hover='#EBADAD')

DARK_QSS = _BASE.format(
    bg='#1E1F22', base='#26282D', text='#E6E8EB', border='#3C4048',
    button='#33363C', hover='#2C4A3E', group='#232529', alt='#2B2E34',
    muted='#7C828A', accent='#37C894',
    run_bg='#2E5D45', run_fg='#CFF0DD', run_hover='#35684E',
    cancel_bg='#5D3232', cancel_fg='#F5CFCF', cancel_hover='#6A3A3A')

THEMES = {'light': LIGHT_QSS, 'dark': DARK_QSS}


def apply_theme(app, name):
    app.setStyleSheet(THEMES.get(name, LIGHT_QSS))
