"""Palette et feuille de style globale (theme sombre)."""

from __future__ import annotations

BG = "#080d14"
BG_DEEP = "#060a10"
SIDEBAR = "#0b121c"
CARD = "#101a27"
CARD_ALT = "#0d1520"
CARD_HOVER = "#152233"
BORDER = "#1e2d42"
BORDER_SOFT = "#182538"
TEXT = "#e9f0fb"
TEXT_SOFT = "#b9c7db"
MUTED = "#8295b0"
ACCENT = "#28d17c"
ACCENT_DARK = "#0f9c5a"
ACCENT_SOFT = "rgba(40, 209, 124, 0.14)"
BLUE = "#4c8dff"
BLUE_SOFT = "rgba(76, 141, 255, 0.14)"
AMBER = "#f4b740"
AMBER_SOFT = "rgba(244, 183, 64, 0.14)"
RED = "#f26372"
RED_SOFT = "rgba(242, 99, 114, 0.14)"
PURPLE = "#a78bfa"
PURPLE_SOFT = "rgba(167, 139, 250, 0.14)"

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono, Consolas, monospace"


STYLESHEET = f"""
* {{
    font-family: "{FONT_FAMILY}";
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QWidget#appRoot {{
    background: {BG};
}}
QWidget {{
    background: transparent;
}}
QFrame#sidebar {{
    background: {SIDEBAR};
    border-right: 1px solid {BORDER_SOFT};
}}
QLabel#brandTitle {{
    font-size: 17pt;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#brandSub {{
    font-size: 7.5pt;
    font-weight: 600;
    color: {ACCENT};
    letter-spacing: 2px;
}}
QLabel#pageTitle {{
    font-size: 19pt;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#pageSubtitle {{
    font-size: 9.5pt;
    color: {MUTED};
}}
QLabel#sectionTitle {{
    font-size: 12pt;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#cardTitle {{
    font-size: 10.5pt;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#muted {{
    color: {MUTED};
}}
QLabel#small {{
    font-size: 8.5pt;
    color: {MUTED};
}}
QLabel#valueBig {{
    font-family: "{MONO_FAMILY}";
    font-size: 21pt;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#valueMedium {{
    font-family: "{MONO_FAMILY}";
    font-size: 13pt;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#mono {{
    font-family: "{MONO_FAMILY}";
}}
QFrame#card {{
    background: {CARD};
    border: 1px solid {BORDER_SOFT};
    border-radius: 14px;
}}
QFrame#card:hover {{
    border: 1px solid {BORDER};
}}
QFrame#innerCard {{
    background: {CARD_ALT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 10px;
}}
QFrame#headerBar {{
    background: {BG};
    border-bottom: 1px solid {BORDER_SOFT};
}}
QFrame#divider {{
    background: {BORDER_SOFT};
    max-height: 1px;
    min-height: 1px;
}}
QListWidget#nav {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px 10px;
}}
QListWidget#nav::item {{
    padding: 10px 12px;
    margin: 2px 4px;
    border-radius: 9px;
    color: {TEXT_SOFT};
    font-weight: 500;
}}
QListWidget#nav::item:hover {{
    background: {CARD_HOVER};
    color: {TEXT};
}}
QListWidget#nav::item:selected {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
    font-weight: 600;
}}
QPushButton {{
    background: {CARD_HOVER};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 13px;
    color: {TEXT_SOFT};
    font-weight: 600;
}}
QPushButton:hover {{
    border: 1px solid {BORDER};
    background: #1a2a3e;
    color: {TEXT};
}}
QPushButton:pressed {{
    background: #0f1a28;
}}
QPushButton:disabled {{
    color: #56657a;
    border-color: {BORDER_SOFT};
    background: {CARD_ALT};
}}
QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #062015;
}}
QPushButton#primary:hover {{
    background: #3ae08c;
    border-color: #3ae08c;
}}
QPushButton#primary:pressed {{
    background: {ACCENT_DARK};
}}
QPushButton#primary:disabled {{
    background: #174b33;
    border-color: #174b33;
    color: #6c9981;
}}
QPushButton#danger {{
    background: {RED_SOFT};
    border: 1px solid rgba(242, 99, 114, 0.35);
    color: {RED};
}}
QPushButton#danger:hover {{
    background: rgba(242, 99, 114, 0.22);
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid {BORDER_SOFT};
}}
QPushButton#link {{
    background: transparent;
    border: none;
    color: {ACCENT};
    padding: 2px 4px;
    text-align: left;
}}
QPushButton#link:hover {{
    color: #56e5a1;
    background: transparent;
}}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG_DEEP};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    color: {TEXT};
    selection-background-color: {ACCENT_DARK};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit::placeholder {{
    color: {MUTED};
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT};
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 8px;
    border-radius: 6px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 16px;
    background: {CARD_HOVER};
    border: none;
}}
QTableWidget {{
    background: {CARD};
    alternate-background-color: {CARD_ALT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
    gridline-color: transparent;
    selection-background-color: #17324a;
    selection-color: {TEXT};
    outline: none;
}}
QTableWidget::item {{
    padding: 7px 8px;
    border-bottom: 1px solid {BORDER_SOFT};
}}
QTableWidget::item:selected {{
    background: #17324a;
}}
QHeaderView::section {{
    background: {CARD_ALT};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QTableCornerButton::section {{
    background: {CARD_ALT};
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #24364d;
    min-height: 26px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: #314862;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #24364d;
    min-width: 26px;
    border-radius: 5px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
    background: {CARD};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QProgressBar {{
    background: {BG_DEEP};
    border: none;
    border-radius: 4px;
    height: 7px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}
QToolTip {{
    background: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px;
    border-radius: 6px;
}}
QMenu {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 7px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
}}
QDialog {{
    background: {BG};
}}
QMessageBox {{
    background: {BG};
}}
QCheckBox {{
    color: {TEXT_SOFT};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background: {BG_DEEP};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QStatusBar {{
    background: {SIDEBAR};
    border-top: 1px solid {BORDER_SOFT};
    color: {MUTED};
}}
QStatusBar::item {{
    border: none;
}}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px;
}}
QToolButton:hover {{
    background: {CARD_HOVER};
}}
"""
