from __future__ import annotations

from typing import TypedDict


class Palette(TypedDict):
    bg: str
    surface: str
    surface_2: str
    border: str
    text: str
    muted: str
    accent: str
    accent_dark: str
    accent_soft: str
    danger: str
    ok: str
    disabled_bg: str
    disabled_fg: str


class Theme(TypedDict):
    label: str
    light: Palette
    dark: Palette


THEME_ORDER = ("theia", "midnight", "aurora", "ember")

THEMES: dict[str, Theme] = {
    "midnight": {
        "label": "Midnight",
        "light": {
            "bg": "#eef2f7",
            "surface": "#ffffff",
            "surface_2": "#f6f8fb",
            "border": "#cfd7e5",
            "text": "#172033",
            "muted": "#647084",
            "accent": "#2563eb",
            "accent_dark": "#1d4ed8",
            "accent_soft": "#dbeafe",
            "danger": "#dc2626",
            "ok": "#0f9f6e",
            "disabled_bg": "#e5eaf2",
            "disabled_fg": "#9aa6b8",
        },
        "dark": {
            "bg": "#0b0d10",
            "surface": "#11151a",
            "surface_2": "#171d24",
            "border": "#29313b",
            "text": "#f4f7fb",
            "muted": "#9ba8b7",
            "accent": "#4f8cff",
            "accent_dark": "#2f6fe4",
            "accent_soft": "#17304f",
            "danger": "#fb7185",
            "ok": "#34d399",
            "disabled_bg": "#1b222b",
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
            "text": "#14231d",
            "muted": "#60756c",
            "accent": "#0f9f6e",
            "accent_dark": "#087f5b",
            "accent_soft": "#dff7ec",
            "danger": "#dc2626",
            "ok": "#16835e",
            "disabled_bg": "#e4eee9",
            "disabled_fg": "#91a19a",
        },
        "dark": {
            "bg": "#07110e",
            "surface": "#10201a",
            "surface_2": "#152a22",
            "border": "#244137",
            "text": "#ecfff7",
            "muted": "#9ab8ac",
            "accent": "#0ea5e9",
            "accent_dark": "#0284c7",
            "accent_soft": "#0c3144",
            "danger": "#fb7185",
            "ok": "#86efac",
            "disabled_bg": "#1d3028",
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
            "text": "#2b211b",
            "muted": "#7c6a5b",
            "accent": "#d9480f",
            "accent_dark": "#b83b0b",
            "accent_soft": "#ffe8d6",
            "danger": "#c92a2a",
            "ok": "#2b8a3e",
            "disabled_bg": "#eee5dd",
            "disabled_fg": "#a19388",
        },
        "dark": {
            "bg": "#120c09",
            "surface": "#201610",
            "surface_2": "#2b1d14",
            "border": "#473325",
            "text": "#fff4ec",
            "muted": "#c2aa99",
            "accent": "#f97316",
            "accent_dark": "#c2410c",
            "accent_soft": "#4a2412",
            "danger": "#fb7185",
            "ok": "#86efac",
            "disabled_bg": "#31231a",
            "disabled_fg": "#877367",
        },
    },
}

THEMES["theia"] = {
    "label": "Theia",
    "light": {
        "bg": "#fafaf9", "surface": "#ffffff", "surface_2": "#f4f4f3",
        "border": "#e5e5e3", "text": "#202123", "muted": "#6b6c70",
        "accent": "#108568", "accent_dark": "#0d7058", "accent_soft": "#e6f3ee",
        "danger": "#c83c4a", "ok": "#108568", "disabled_bg": "#f1f1ef", "disabled_fg": "#a8aaa7",
    },
    "dark": {
        "bg": "#212121", "surface": "#272727", "surface_2": "#303030",
        "border": "#3c3c3c", "text": "#ececec", "muted": "#a9a9a9",
        "accent": "#10a37f", "accent_dark": "#0d886a", "accent_soft": "#173e33",
        "danger": "#ef8088", "ok": "#5bd2ae", "disabled_bg": "#303030", "disabled_fg": "#707070",
    },
}


def palette_for(theme: str, dark_mode: bool) -> Palette:
    theme_key = theme if theme in THEMES else "theia"
    mode = "dark" if dark_mode else "light"
    return THEMES[theme_key][mode]


def build_stylesheet(theme: str, dark_mode: bool) -> str:
    p = palette_for(theme, dark_mode)
    selected_text = "#ffffff"
    selected_label = p["ok"] if dark_mode else p["accent_dark"]
    return f"""
QMainWindow, QWidget {{
    background: {p["bg"]};
    color: {p["text"]};
    font-size: 13px;
}}
QToolBar#main-toolbar {{
    background: {p["surface"]};
    border: none;
    border-bottom: 1px solid {p["border"]};
    spacing: 6px;
    padding: 8px 16px;
}}
QToolBar#main-toolbar QWidget#toolbar-spacer {{
    background: transparent;
}}
QToolBar#main-toolbar QLabel#toolbar-label {{
    background: transparent;
    color: {p["muted"]};
    font-size: 12px;
    font-weight: 500;
    padding: 0 2px 0 8px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: {p["text"]};
    padding: 6px 10px;
    font-size: 12px;
}}
QToolButton:hover {{
    background: {p["surface_2"]};
    border-color: {p["border"]};
}}
QToolButton:pressed {{
    background: {p["accent_soft"]};
    border-color: {p["accent"]};
}}
QToolButton:checked {{ background: {p["accent"]}; color: {selected_text}; border-color: {p["accent"]}; }}
QComboBox, QLineEdit {{
    padding: 7px 10px;
    border: 1px solid {p["border"]};
    border-radius: 6px;
    background: {p["surface_2"]};
    color: {p["text"]};
    selection-background-color: {p["accent"]};
    selection-color: {selected_text};
    font-size: 12px;
}}
QComboBox:focus, QLineEdit:focus {{ border-color: {p["accent"]}; }}
QComboBox::drop-down {{ width: 22px; border: none; }}
QComboBox QAbstractItemView {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    selection-background-color: {p["accent"]};
    selection-color: {selected_text};
}}
QCheckBox {{
    color: {p["text"]};
    spacing: 6px;
    background: transparent;
    font-size: 12px;
}}
QCheckBox#dark-toggle::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1px solid {p["border"]};
    background: {p["surface_2"]};
}}
QCheckBox#dark-toggle::indicator:hover {{ border-color: {p["accent"]}; }}
QCheckBox#dark-toggle::indicator:checked {{
    background: {p["accent"]};
    border-color: {p["accent"]};
}}
QSplitter::handle {{ background: {p["border"]}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QLabel#section-header {{
    background: {p["surface"]};
    color: {p["muted"]};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0;
    padding: 12px 12px 6px 12px;
    border-bottom: 1px solid {p["border"]};
}}
QWidget#nav-pane {{
    background: {p["surface"]};
    border-right: 1px solid {p["border"]};
}}
QTreeView, QListView {{
    border: none;
    background: {p["surface"]};
    color: {p["text"]};
    padding: 4px;
    font-size: 13px;
    outline: 0;
}}
QTreeView::item, QListView::item {{
    padding: 6px 10px;
    border-radius: 5px;
    margin: 1px 3px;
}}
QTreeView::item:hover, QListView::item:hover {{ background: {p["surface_2"]}; }}
QTreeView::item:selected, QListView::item:selected {{
    background: {p["accent_soft"]};
    color: {selected_label};
}}
QTreeView::branch {{ background: {p["surface"]}; }}
QTableView {{
    background: {p["surface"]};
    alternate-background-color: {p["surface_2"]};
    color: {p["text"]};
    gridline-color: {p["border"]};
    border: none;
    selection-background-color: {p["accent_soft"]};
    selection-color: {p["text"]};
    font-size: 12px;
}}
QHeaderView::section {{
    background: {p["surface_2"]};
    color: {p["muted"]};
    padding: 5px 8px;
    border: none;
    border-right: 1px solid {p["border"]};
    border-bottom: 1px solid {p["border"]};
    font-weight: 600;
    font-size: 11px;
}}
QTableCornerButton::section {{
    background: {p["surface_2"]};
    border-right: 1px solid {p["border"]};
    border-bottom: 1px solid {p["border"]};
}}
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
QScrollBar::handle:hover {{ background: {p["accent"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QProgressBar {{
    border: none;
    border-radius: 3px;
    background: {p["disabled_bg"]};
    min-height: 6px;
    max-height: 6px;
}}
QProgressBar::chunk {{
    background: {p["accent"]};
    border-radius: 3px;
}}
QStatusBar {{
    background: {p["surface"]};
    border-top: 1px solid {p["border"]};
    color: {p["muted"]};
    font-size: 11px;
    padding: 0;
}}
QStatusBar QLabel {{
    color: {p["muted"]};
    font-size: 11px;
}}
QMenuBar {{
    background: {p["surface"]};
    color: {p["text"]};
    border-bottom: 1px solid {p["border"]};
    padding: 2px 4px;
}}
QMenuBar::item {{ padding: 5px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {p["surface_2"]}; }}
QMenu {{
    background: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 4px; font-size: 13px; }}
QMenu::item:selected {{ background: {p["surface_2"]}; color: {p["text"]}; }}
QMenu::separator {{ height: 1px; background: {p["border"]}; margin: 4px 0; }}

QLabel#app-brand {{
    font-size: 18px; font-weight: 600; padding: 0 26px 0 4px; background: transparent;
}}
QWidget#workspace {{ background: {p["bg"]}; }}
QLabel#document-title {{ font-size: 20px; font-weight: 600; padding: 2px 0 4px 0; background: transparent; }}
QWidget#cell-bar, QWidget#sheet-bar {{ background: transparent; }}
QLineEdit#cell-address {{ background: {p["surface"]}; border-radius: 5px; padding: 6px 8px; }}
QLineEdit#cell-value {{ background: {p["surface"]}; border-radius: 5px; padding: 6px 10px; }}
QStackedWidget#sheet-surface {{ border: 1px solid {p["border"]}; background: {p["surface"]}; }}
QWidget#empty-state {{ background: {p["surface"]}; }}
QLabel#empty-heading {{ font-size: 25px; font-weight: 600; background: transparent; padding: 12px; }}
QLabel#empty-description {{ color: {p["muted"]}; background: transparent; }}
QPushButton#primary-button {{
    background: {p["accent"]}; color: white; border: none; border-radius: 7px; padding: 10px 20px;
}}
QPushButton#primary-button:hover {{ background: {p["accent_dark"]}; }}
QTabBar#sheet-tabs {{ background: transparent; }}
QTabBar#sheet-tabs::tab {{
    background: transparent; color: {p["muted"]}; border: none; border-bottom: 2px solid transparent;
    padding: 9px 15px; margin-right: 2px; min-width: 40px;
}}
QTabBar#sheet-tabs::tab:selected {{
    color: {selected_label}; border-bottom-color: {p["accent"]}; background: {p["accent_soft"]};
}}
QTabBar#sheet-tabs::tab:hover {{ background: {p["surface_2"]}; }}
"""
