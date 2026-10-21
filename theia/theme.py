from __future__ import annotations

import re
from typing import TypedDict

from PySide6.QtGui import QColor, QPalette


class Palette(TypedDict):
    bg: str
    surface: str
    surface_2: str
    border: str
    border_soft: str
    text: str
    ink_soft: str
    muted: str
    accent: str
    accent_soft: str
    accent_line: str
    hover: str
    disabled_fg: str


class Theme(TypedDict):
    label: str
    light: Palette
    dark: Palette


THEME_ORDER = ("theia", "midnight", "aurora", "ember")

THEMES: dict[str, Theme] = {
    "theia": {
        "label": "Theia",
        "light": {
            "bg": "#f3f6fb",
            "surface": "#ffffff",
            "surface_2": "#f6f8fa",
            "border": "#dce4ef",
            "border_soft": "#edf1f6",
            "text": "#132238",
            "ink_soft": "#40516a",
            "muted": "#718096",
            "accent": "#3157d5",
            "accent_soft": "#e9eeff",
            "accent_line": "#b9c7f1",
            "hover": "#eef2f6",
            "disabled_fg": "#b4c0cf",
        },
        "dark": {
            "bg": "#080b10",
            "surface": "#0f141b",
            "surface_2": "#141a23",
            "border": "#1f2733",
            "border_soft": "#171e28",
            "text": "#e6ebf2",
            "ink_soft": "#b3bdcc",
            "muted": "#7c8798",
            "accent": "#6f96ff",
            "accent_soft": "#1c263b",
            "accent_line": "#3a4e82",
            "hover": "#172031",
            "disabled_fg": "#3a4556",
        },
    },
    "midnight": {
        "label": "Midnight",
        "light": {
            "bg": "#eef2f7",
            "surface": "#ffffff",
            "surface_2": "#f6f8fb",
            "border": "#cfd7e5",
            "border_soft": "#e6ebf3",
            "text": "#172033",
            "ink_soft": "#3b4658",
            "muted": "#647084",
            "accent": "#2563eb",
            "accent_soft": "#dbeafe",
            "accent_line": "#b7cdfa",
            "hover": "#eef3fb",
            "disabled_fg": "#9aa6b8",
        },
        "dark": {
            "bg": "#0b0d10",
            "surface": "#11151a",
            "surface_2": "#171d24",
            "border": "#29313b",
            "border_soft": "#1c232c",
            "text": "#f4f7fb",
            "ink_soft": "#c9d2de",
            "muted": "#9ba8b7",
            "accent": "#4f8cff",
            "accent_soft": "#17304f",
            "accent_line": "#2c4f86",
            "hover": "#1a222c",
            "disabled_fg": "#657283",
        },
    },
    "aurora": {
        "label": "Aurora",
        "light": {
            "bg": "#f0f7f4",
            "surface": "#ffffff",
            "surface_2": "#f5fbf8",
            "border": "#c7ded4",
            "border_soft": "#e3efe9",
            "text": "#14231d",
            "ink_soft": "#34483f",
            "muted": "#60756c",
            "accent": "#0f9f6e",
            "accent_soft": "#dff7ec",
            "accent_line": "#a7dcc4",
            "hover": "#ecf6f1",
            "disabled_fg": "#91a19a",
        },
        "dark": {
            "bg": "#07110e",
            "surface": "#10201a",
            "surface_2": "#152a22",
            "border": "#244137",
            "border_soft": "#1a3029",
            "text": "#ecfff7",
            "ink_soft": "#c3dcd2",
            "muted": "#9ab8ac",
            "accent": "#0ea5e9",
            "accent_soft": "#0c3144",
            "accent_line": "#155a7c",
            "hover": "#183128",
            "disabled_fg": "#6f887c",
        },
    },
    "ember": {
        "label": "Ember",
        "light": {
            "bg": "#f7f3ef",
            "surface": "#fffdfa",
            "surface_2": "#fbf4ec",
            "border": "#e0cfc0",
            "border_soft": "#efe4d9",
            "text": "#2b211b",
            "ink_soft": "#4f4035",
            "muted": "#7c6a5b",
            "accent": "#d9480f",
            "accent_soft": "#ffe8d6",
            "accent_line": "#f4bf9c",
            "hover": "#f8efe6",
            "disabled_fg": "#a19388",
        },
        "dark": {
            "bg": "#120c09",
            "surface": "#201610",
            "surface_2": "#2b1d14",
            "border": "#473325",
            "border_soft": "#33241a",
            "text": "#fff4ec",
            "ink_soft": "#e4d2c4",
            "muted": "#c2aa99",
            "accent": "#f97316",
            "accent_soft": "#4a2412",
            "accent_line": "#7a3a16",
            "hover": "#35261b",
            "disabled_fg": "#877367",
        },
    },
}


def palette_for(theme: str, dark_mode: bool) -> Palette:
    theme_key = theme if theme in THEMES else "theia"
    mode = "dark" if dark_mode else "light"
    return THEMES[theme_key][mode]


def build_palette(theme: str, dark_mode: bool) -> QPalette:
    """The Qt palette Fusion draws check marks, arrows and placeholders from, so they follow the theme too."""
    p = palette_for(theme, dark_mode)
    palette = QPalette()
    for role, key in (
        (QPalette.Window, "bg"),
        (QPalette.WindowText, "text"),
        (QPalette.Base, "surface"),
        (QPalette.AlternateBase, "surface_2"),
        (QPalette.Text, "text"),
        (QPalette.Button, "surface"),
        (QPalette.ButtonText, "text"),
        (QPalette.Highlight, "accent"),
        (QPalette.HighlightedText, "surface"),
        (QPalette.ToolTipBase, "surface"),
        (QPalette.ToolTipText, "text"),
        (QPalette.PlaceholderText, "muted"),
        (QPalette.Light, "surface"),
        (QPalette.Midlight, "border_soft"),
        (QPalette.Mid, "border"),
        (QPalette.Dark, "border"),
    ):
        palette.setColor(role, QColor(p[key]))
    return palette


def build_stylesheet(theme: str, dark_mode: bool, zoom: int = 100) -> str:
    p = palette_for(theme, dark_mode)
    stylesheet = f"""
QMainWindow, QWidget {{
    background: {p["bg"]};
    color: {p["text"]};
    font-size: 13px;
}}
QToolTip {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    padding: 4px 6px;
}}
QFrame#app-bar {{
    background: {p["surface"]};
    border: none;
    border-bottom: 1px solid {p["border"]};
}}
QFrame#app-bar QLabel {{ background: transparent; }}
QLabel#app-brand {{ font-size: 14px; font-weight: 700; padding-right: 2px; }}
QLabel#app-title {{ font-weight: 600; }}
QLabel#app-detail {{ color: {p["muted"]}; font-size: 12px; }}
QMenuBar#app-menu {{ background: transparent; border: none; padding: 0; }}
QMenuBar#app-menu::item {{
    background: transparent;
    color: {p["ink_soft"]};
    padding: 3px 8px;
    border-radius: 6px;
}}
QMenuBar#app-menu::item:selected {{ background: {p["hover"]}; color: {p["text"]}; }}
QToolButton#bar-button, QToolButton#theme-button {{
    background: {p["surface"]};
    color: {p["ink_soft"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 12px;
}}
QToolButton#theme-button {{ font-size: 15px; padding: 0 6px; }}
QToolButton#bar-button:hover, QToolButton#theme-button:hover {{ background: {p["hover"]}; color: {p["text"]}; }}
QToolButton#bar-button:pressed, QToolButton#theme-button:pressed {{
    background: {p["accent_soft"]};
    border-color: {p["accent_line"]};
    color: {p["accent"]};
}}
QFrame#nav-pane {{
    background: {p["surface"]};
    border: none;
    border-right: 1px solid {p["border"]};
}}
QLabel#section-header {{
    background: transparent;
    color: {p["muted"]};
    font-size: 11px;
    font-weight: 700;
    padding: 0 2px;
}}
QLineEdit {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 3px 7px;
    font-size: 12px;
    selection-background-color: {p["accent"]};
    selection-color: {p["surface"]};
}}
QLineEdit:focus {{ border-color: {p["accent"]}; }}
QTreeView, QListView {{
    border: none;
    background: {p["surface"]};
    color: {p["text"]};
    padding: 2px;
    outline: 0;
}}
QTreeView::item, QListView::item {{
    padding: 3px 6px;
    border-radius: 6px;
    margin: 0 2px;
}}
QTreeView::item:hover, QListView::item:hover {{ background: {p["hover"]}; }}
QTreeView::item:selected, QListView::item:selected {{
    background: {p["accent_soft"]};
    color: {p["accent"]};
}}
QTreeView::branch {{ background: {p["surface"]}; }}
QFrame#sheet-strip {{
    background: {p["surface"]};
    border: none;
    border-bottom: 1px solid {p["border"]};
}}
QTabBar#sheet-tabs {{ background: transparent; font-size: 12px; }}
QTabBar#sheet-tabs::tab {{
    background: transparent;
    color: {p["ink_soft"]};
    border: none;
    border-radius: 6px;
    padding: 3px 9px;
}}
QTabBar#sheet-tabs::tab:hover {{ background: {p["hover"]}; color: {p["text"]}; }}
QTabBar#sheet-tabs::tab:selected {{ background: {p["text"]}; color: {p["surface"]}; }}
QTabBar QToolButton {{
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-radius: 4px;
}}
QFrame#cell-bar {{
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
}}
QLineEdit#cell-address {{ background: {p["surface_2"]}; font-weight: 600; }}
QLineEdit#cell-value {{
    background: transparent;
    border: none;
    border-left: 1px solid {p["border"]};
    border-radius: 0;
    padding: 3px 10px;
    font-size: 13px;
}}
QStackedWidget#sheet-surface {{
    background: {p["surface"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
}}
QTableView {{
    background: {p["surface"]};
    alternate-background-color: {p["surface"]};
    color: {p["text"]};
    gridline-color: {p["border_soft"]};
    border: none;
    selection-background-color: {p["accent_soft"]};
    selection-color: {p["text"]};
    font-size: 12px;
}}
QHeaderView {{ background: {p["surface"]}; }}
QHeaderView::section {{
    background: {p["surface_2"]};
    color: {p["ink_soft"]};
    padding: 2px 6px;
    border: none;
    border-right: 1px solid {p["border_soft"]};
    border-bottom: 1px solid {p["border"]};
    font-weight: 600;
    font-size: 11px;
}}
QTableCornerButton::section {{
    background: {p["surface_2"]};
    border-right: 1px solid {p["border_soft"]};
    border-bottom: 1px solid {p["border"]};
}}
QWidget#empty-state, QWidget#empty-state QLabel {{ background: {p["surface"]}; }}
QLabel#empty-heading {{ font-size: 18px; font-weight: 600; }}
QLabel#empty-description {{ color: {p["ink_soft"]}; }}
QLabel#empty-note {{ color: {p["muted"]}; font-size: 12px; }}
QPushButton {{
    background: {p["surface"]};
    color: {p["ink_soft"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {p["accent"]}; color: {p["accent"]}; }}
QPushButton:disabled {{ color: {p["disabled_fg"]}; }}
QPushButton#primary-button {{ background: {p["text"]}; border-color: {p["text"]}; color: {p["surface"]}; }}
QPushButton#primary-button:hover {{ background: {p["accent"]}; border-color: {p["accent"]}; color: {p["surface"]}; }}
QCheckBox {{ background: transparent; spacing: 6px; font-size: 12px; }}
QCheckBox::indicator {{
    width: 12px;
    height: 12px;
    border: 1px solid {p["muted"]};
    border-radius: 3px;
    background: {p["surface"]};
}}
QCheckBox::indicator:hover {{ border-color: {p["accent"]}; }}
QCheckBox::indicator:checked {{ background: {p["accent"]}; border-color: {p["accent"]}; }}
QSplitter::handle {{ background: {p["border"]}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    width: 9px;
    height: 9px;
    margin: 0;
}}
QScrollBar::handle {{
    background: {p["disabled_fg"]};
    border-radius: 4px;
    min-height: 22px;
    min-width: 22px;
}}
QScrollBar::handle:hover {{ background: {p["muted"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QProgressBar {{
    border: none;
    border-radius: 3px;
    background: {p["border_soft"]};
    min-height: 6px;
    max-height: 6px;
}}
QProgressBar::chunk {{
    background: {p["accent"]};
    border-radius: 3px;
}}
QMenu {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 5px 20px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p["hover"]}; color: {p["text"]}; }}
QMenu::separator {{ height: 1px; background: {p["border"]}; margin: 4px 0; }}
"""
    return re.sub(r"(\d+)px", lambda match: f"{max(1, round(int(match[1]) * zoom / 100))}px", stylesheet)
