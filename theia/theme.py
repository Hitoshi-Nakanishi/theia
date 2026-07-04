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


THEME_ORDER = ("midnight", "aurora", "ember")

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
            "bg": "#070b12",
            "surface": "#101724",
            "surface_2": "#151f31",
            "border": "#243349",
            "text": "#edf4ff",
            "muted": "#91a0b8",
            "accent": "#3b82f6",
            "accent_dark": "#2563eb",
            "accent_soft": "#172554",
            "danger": "#fb7185",
            "ok": "#34d399",
            "disabled_bg": "#1b2535",
            "disabled_fg": "#66758c",
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

THEME_LABELS = {value["label"]: key for key, value in THEMES.items()}


def palette_for(theme: str, dark_mode: bool) -> Palette:
    theme_key = theme if theme in THEMES else "midnight"
    mode = "dark" if dark_mode else "light"
    return THEMES[theme_key][mode]


def build_stylesheet(theme: str, dark_mode: bool) -> str:
    p = palette_for(theme, dark_mode)
    selected_text = "#ffffff" if dark_mode else "#ffffff"
    return f"""
QMainWindow, QWidget {{
    background: {p["bg"]};
    color: {p["text"]};
    font-family: Arial;
}}
QToolBar {{
    background: {p["surface"]};
    border: none;
    border-bottom: 1px solid {p["border"]};
    spacing: 8px;
    padding: 7px 10px;
}}
QToolBar QLabel {{
    background: transparent;
    color: {p["muted"]};
    font-size: 11px;
    font-weight: 600;
}}
QToolButton {{
    background: {p["surface_2"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    color: {p["text"]};
    padding: 5px 9px;
}}
QToolButton:hover {{ border-color: {p["accent"]}; color: {p["accent"]}; }}
QToolButton:checked {{ background: {p["accent"]}; color: {selected_text}; border-color: {p["accent"]}; }}
QComboBox, QLineEdit {{
    padding: 6px 10px;
    border: 1px solid {p["border"]};
    border-radius: 6px;
    background: {p["surface"]};
    color: {p["text"]};
    selection-background-color: {p["accent"]};
    selection-color: {selected_text};
    font-size: 13px;
}}
QComboBox:focus, QLineEdit:focus {{ border-color: {p["accent"]}; }}
QComboBox::drop-down {{ width: 20px; border: none; }}
QCheckBox {{
    color: {p["text"]};
    spacing: 6px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 34px;
    height: 18px;
    border-radius: 9px;
    border: 1px solid {p["border"]};
    background: {p["surface_2"]};
}}
QCheckBox::indicator:checked {{
    background: {p["accent"]};
    border-color: {p["accent"]};
}}
QSplitter::handle {{ background: {p["border"]}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QLabel#section-header {{
    background: {p["bg"]};
    color: {p["muted"]};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0;
    padding: 10px 12px 5px 12px;
    border-bottom: 1px solid {p["border"]};
}}
QTreeView, QListView {{
    border: none;
    background: {p["bg"]};
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
    background: {p["accent"]};
    color: {selected_text};
}}
QTreeView::branch {{ background: {p["bg"]}; }}
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
"""
