"""Application themes: light/dark palettes with a dynamic accent color.

Theme can follow the Windows system setting ('system') and the accent can
either be a fixed preset or the Windows system accent; both are read from
the registry on Windows and fall back gracefully elsewhere.
"""

try:
    import winreg
except ImportError:  # non-Windows
    winreg = None

ACCENTS = {
    'green': '#1E9E6A',
    'blue': '#2D7DD2',
    'violet': '#8E6BD8',
    'orange': '#E08A3C',
    'red': '#D9534F',
}
ACCENT_DEFAULT = 'green'


def system_theme():
    """'light' or 'dark' according to the Windows apps theme."""
    if winreg is not None:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            with key:
                value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
                return 'dark' if value == 0 else 'light'
        except OSError:
            pass
        return 'light'
    return _palette_theme()


def _palette_theme():
    """'dark' when the desktop's Qt palette has a dark window colour (Linux)."""
    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return 'light'
    app = QGuiApplication.instance()
    if app is None:
        return 'light'
    return 'dark' if app.palette().window().color().lightness() < 128 else 'light'


def system_accent():
    """Windows system accent as '#RRGGBB', or None if unavailable."""
    if winreg is not None:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\DWM')
            with key:
                value, _ = winreg.QueryValueEx(key, 'AccentColor')  # 0xAABBGGRR
                r, g, b = value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
                if (r, g, b) != (0, 0, 0):
                    return f'#{r:02X}{g:02X}{b:02X}'
        except OSError:
            pass
    return None


PALETTES = {
    'light': dict(
        bg='#FAFAFA', base='#FFFFFF', text='#212121', border='#C9CDD3',
        button='#E9EBEE', hover='#E0F2EA', group='#FFFFFF', alt='#F3F6F5',
        muted='#9AA0A6',
        run_bg='#B7DFC5', run_fg='#1E4620', run_hover='#A3D5B5',
        cancel_bg='#F1BDBD', cancel_fg='#6E1B1B', cancel_hover='#EBADAD'),
    'dark': dict(
        bg='#1E1F22', base='#26282D', text='#E6E8EB', border='#3C4048',
        button='#33363C', hover='#2C4A3E', group='#232529', alt='#2B2E34',
        muted='#7C828A',
        run_bg='#2E5D45', run_fg='#CFF0DD', run_hover='#35684E',
        cancel_bg='#5D3232', cancel_fg='#F5CFCF', cancel_hover='#6A3A3A'),
}

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
QScrollBar::handle:vertical {{ background: {border}; border: none; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar:horizontal {{ background: {bg}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {border}; border: none; border-radius: 5px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
QTableWidget {{ background: {base}; border: 1px solid {border}; gridline-color: {border};
    alternate-background-color: {alt}; }}
QHeaderView::section {{ background: {button}; border: none; padding: 4px; font-weight: 600; }}
QDialog {{ background: {bg}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QToolTip {{ background: {base}; color: {text}; border: 1px solid {accent}; }}
QScrollArea {{ border: none; }}
"""


def resolve(theme_setting, accent_setting):
    """Map user settings to a concrete (palette_name, accent_hex)."""
    theme = system_theme() if theme_setting == 'system' else theme_setting
    if theme not in PALETTES:
        theme = 'light'
    accent = system_accent() if accent_setting == 'system' else None
    if not accent:
        accent = ACCENTS.get(accent_setting) or (
            accent_setting if isinstance(accent_setting, str) and accent_setting.startswith('#')
            else ACCENTS[ACCENT_DEFAULT])
    return theme, accent


def build_qss(theme, accent):
    p = dict(PALETTES[theme])
    p['accent'] = accent
    return _BASE.format(**p)


def role_colors(theme, accent):
    """Log entry colors for the given palette; 'out' must never stay black."""
    return {
        'error': '#E53935',
        'success': '#43A047',
        'system': accent,
        'out': PALETTES[theme]['text'],
    }


def apply_theme(app, theme_setting, accent_setting):
    theme, accent = resolve(theme_setting, accent_setting)
    app.setStyleSheet(build_qss(theme, accent))
    return theme, accent
