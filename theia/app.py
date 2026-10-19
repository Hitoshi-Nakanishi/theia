import json
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QSettings, QSignalBlocker, QSortFilterProxyModel, QStringListModel, QThread, Signal, QItemSelectionModel
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from theia.compare import ComparisonDialog, Metric
from theia.model import SheetModel, _col_letter
from theia.table import FrozenPaneTable
from theia.theme import THEME_ORDER, THEMES, build_stylesheet
from theia.workbook import Source, Workbook, list_zip_xlsx

try:
    from theia.arrow_model import ArrowSheetModel
except ImportError:
    ArrowSheetModel = None


STYLE = """
/* ===== Base ===== */
QMainWindow, QWidget {
    background: #f6f8fa;
    color: #1f2328;
    font-family: "Segoe UI", system-ui, sans-serif;
}

/* ===== Splitter ===== */
QSplitter::handle { background: #d0d7de; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical   { height: 1px; }

/* ===== Pane section header ===== */
QLabel#section-header {
    background: #f6f8fa;
    color: #6e7781;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 10px 12px 5px 12px;
    border-bottom: 1px solid #eaeef2;
}

/* ===== Filter inputs ===== */
QLineEdit {
    padding: 6px 10px;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    background: #ffffff;
    color: #1f2328;
    selection-background-color: #0969da;
    selection-color: #ffffff;
    font-size: 13px;
}
QLineEdit:focus { border-color: #0969da; }

/* ===== Companies tree ===== */
QTreeView {
    border: none;
    background: #f6f8fa;
    padding: 2px;
    font-size: 13px;
    outline: 0;
    show-decoration-selected: 1;
}
QTreeView::item {
    padding: 5px 8px 5px 4px;
    border-radius: 4px;
    margin: 1px 4px 1px 0;
}
QTreeView::item:hover    { background: #eaeef2; }
QTreeView::item:selected { background: #0969da; color: #ffffff; }
QTreeView::branch        { background: #f6f8fa; }

/* ===== Sheets list ===== */
QListView {
    border: none;
    background: #f6f8fa;
    padding: 4px;
    font-size: 13px;
    outline: 0;
}
QListView::item {
    padding: 6px 10px;
    border-radius: 5px;
    margin: 1px 2px;
}
QListView::item:hover    { background: #eaeef2; }
QListView::item:selected { background: #0969da; color: #ffffff; }

/* ===== Table ===== */
QTableView {
    background: #ffffff;
    alternate-background-color: #f6f8fa;
    gridline-color: #eaeef2;
    border: none;
    selection-background-color: #ddf4ff;
    selection-color: #1f2328;
    font-size: 12px;
}
QHeaderView::section {
    background: #f6f8fa;
    color: #57606a;
    padding: 5px 8px;
    border: none;
    border-right: 1px solid #eaeef2;
    border-bottom: 1px solid #d0d7de;
    font-weight: 600;
    font-size: 11px;
}
QHeaderView::section:vertical {
    padding: 2px 8px;
    border-right: 1px solid #d0d7de;
    border-bottom: 1px solid #eaeef2;
}
QTableCornerButton::section {
    background: #f6f8fa;
    border-right: 1px solid #d0d7de;
    border-bottom: 1px solid #d0d7de;
}

/* ===== Scrollbars ===== */
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    width: 8px;
    height: 8px;
    margin: 0;
}
QScrollBar::handle { background: #c1c8cf; border-radius: 4px; min-height: 20px; min-width: 20px; }
QScrollBar::handle:hover { background: #8c959f; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ===== Preload progress bar ===== */
QProgressBar {
    border: none;
    border-radius: 3px;
    background: #eaeef2;
    min-height: 6px;
    max-height: 6px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0969da, stop:1 #218bff);
    border-radius: 3px;
}

/* ===== Status bar ===== */
QStatusBar {
    background: #f6f8fa;
    border-top: 1px solid #d0d7de;
    color: #57606a;
    font-size: 11px;
    padding: 0;
}
QStatusBar QLabel { color: #57606a; font-size: 11px; }

/* ===== Menu ===== */
QMenuBar { background: #ffffff; border-bottom: 1px solid #d0d7de; padding: 2px 4px; }
QMenuBar::item { padding: 5px 10px; border-radius: 4px; }
QMenuBar::item:selected { background: #eaeef2; }
QMenu { background: #ffffff; border: 1px solid #d0d7de; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 20px 6px 12px; border-radius: 4px; font-size: 13px; }
QMenu::item:selected { background: #eaeef2; color: #1f2328; }
QMenu::separator { height: 1px; background: #eaeef2; margin: 4px 0; }
"""

_SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".xlsm", ".xlsb"}


def _setting_bool(settings: QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _setting_theme(settings: QSettings) -> str:
    value = str(settings.value("theme/name", "midnight"))
    return value if value in THEMES else "midnight"

# Column width bounds when auto-sizing (px)
_MIN_COL_W = 60
_MAX_COL_W = 240

# A Japanese stock ticker on TSE: 4 digits followed by .T (case-insensitive)
_JP_TICKER_RE = re.compile(r"(?<![A-Za-z0-9])(\d{4})\.T(?![A-Za-z0-9])", re.IGNORECASE)

# Filename tokens to strip when distilling a company name from the stem.
_NAME_NOISE_RE = re.compile(
    r"\b(JP|JT|equity|eqty|model|matrix|valuation|v\d+)\b",
    re.IGNORECASE,
)

# Sheet-name substrings that mark non-analytical tabs we don't want to show.
# Deliberately narrow — better to leak one boring sheet than hide a useful one.
_HIDDEN_SHEET_PATTERNS = (
    "disclaim",
    "disclos",
    "important info",
    "important_info",
    "definition",
    "glossary",
    "regulatory",
    "legal notice",
)

# Maximum number of files kept in the preload cache (LRU eviction)
_PRELOAD_CACHE_MAXSIZE = 3

# Maximum number of sheet model entries kept in the sheet model cache (LRU eviction)
_SHEET_MODEL_CACHE_MAXSIZE = 12

# Maximum number of paths sent to the preload worker per folder load
_PRELOAD_MAX_FILES = 3


def _lru_get(cache: OrderedDict, key):
    """Retrieve a value from an LRU OrderedDict cache, moving it to the front
    (most-recently-used end) on hit. Returns None on miss."""
    if key not in cache:
        return None
    cache.move_to_end(key, last=True)
    return cache[key]


def _lru_put(cache: OrderedDict, key, value, maxsize: int):
    """Insert or update a value in an LRU OrderedDict cache. Evicts the
    least-recently-used (oldest / front) entry when the cache is full."""
    if key in cache:
        cache.move_to_end(key, last=True)
        cache[key] = value
        return
    cache[key] = value
    while len(cache) > maxsize:
        cache.popitem(last=False)  # evict oldest


def _broker_from_path(source: Path) -> str:
    """For a source under
    ``<DATA_PATH>/broker_models/<broker>/…`` return the broker folder
    name upper-cased; otherwise fall back to the immediate parent name."""
    parents = list(source.parents)
    for i in range(len(parents) - 1):
        if parents[i + 1].name == "broker_models":
            return parents[i].name.upper()
    if parents and parents[0].name:
        return parents[0].name.upper()
    return "(unknown)"


def _analyst_from_zip_entry(entry: str) -> str:
    """Extract the analyst bucket from a zip entry's path."""
    parts = entry.replace("\\", "/").strip("/").split("/")
    if len(parts) > 1:
        if parts[0].lower() in {"models", "files", "model"}:
            return parts[1] if len(parts) > 2 else parts[0]
        return parts[0]
    return "unknown"


def _broker_analyst_from_folder_path(p: Path, root: Path) -> tuple[str, str]:
    """Return (broker, analyst) inferred from a workbook's path under root.

    Conventions:
      <root>/<broker>/<analyst>/<file>.xlsx   ->  (broker, analyst)
      <root>/<analyst>/<file>.xlsx            ->  ("(local)", analyst)
      <root>/<file>.xlsx                      ->  ("(local)", "(root)")
    """
    try:
        rel = p.relative_to(root).parts
    except ValueError:
        return "(local)", "(root)"
    if len(rel) >= 3:
        return rel[0], rel[1]
    if len(rel) == 2:
        return "(local)", rel[0]
    return "(local)", "(root)"


def _jp_label(stem: str) -> str | None:
    """Return a display label for a JP-equity stem, or None if no XXXX.T ticker."""
    m = _JP_TICKER_RE.search(stem)
    if not m:
        return None
    code = m.group(1)
    rest = stem[: m.start()] + stem[m.end():]
    rest = re.sub(r"[_\-/]+", " ", rest)
    rest = _NAME_NOISE_RE.sub(" ", rest)
    rest = re.sub(r"\b\d{6,8}\b", " ", rest)
    rest = re.sub(r"[()\[\]{}.,]", " ", rest)
    name = " ".join(rest.split()).strip()
    return f"{code}  {name}" if name else code


def _is_hidden_sheet(name: str) -> bool:
    low = name.lower()
    return any(p in low for p in _HIDDEN_SHEET_PATTERNS)


def _make_pane(placeholder: str, title: str = "") -> tuple[QWidget, QLineEdit, QListView, QStringListModel, QSortFilterProxyModel]:
    """Helper: build a titled (filter + list) pane and return its widgets/models."""
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setClearButtonEnabled(True)

    src_model = QStringListModel()
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(src_model)
    proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
    proxy.setDynamicSortFilter(True)

    view = QListView()
    view.setEditTriggers(QListView.NoEditTriggers)
    view.setUniformItemSizes(True)
    view.setModel(proxy)

    edit.textChanged.connect(proxy.setFilterFixedString)

    container = QWidget()
    outer = QVBoxLayout(container)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    if title:
        hdr = QLabel(title.upper())
        hdr.setObjectName("section-header")
        outer.addWidget(hdr)
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    layout.addWidget(edit)
    layout.addWidget(view, 1)
    outer.addWidget(inner, 1)
    return container, edit, view, src_model, proxy


_PRELOAD_MAX_ROWS = 200_000   # skip files above this total-row count (outlier guard)


class _PreloadWorker(QThread):
    """Warm the first visible sheet of a few small workbooks."""

    file_done = Signal(str, float, int, int)  # path, ms, n_sheets, n_rows
    all_done  = Signal(int, int, float)        # n_total, n_loaded, total_ms

    def __init__(self, paths: list, cache: OrderedDict, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._cache = cache

    def run(self):
        from python_calamine import CalamineWorkbook
        t_all = time.perf_counter()
        n_loaded = 0
        for path in self._paths:
            if self.isInterruptionRequested():
                break
            t0 = time.perf_counter()
            try:
                sheet_data: dict = {}
                n_rows = 0
                with CalamineWorkbook.from_path(str(path)) as cal:
                    for name in cal.sheet_names:
                        if _is_hidden_sheet(name):
                            continue
                        sheet = cal.get_sheet_by_name(name)
                        if sheet.height * sheet.width > 200_000:
                            break
                        rows = sheet.to_python(skip_empty_area=False)
                        sheet_data[name] = rows
                        n_rows += len(rows)
                        break
                if n_rows > _PRELOAD_MAX_ROWS:
                    # Too large to cache — will be loaded on demand.
                    elapsed = (time.perf_counter() - t0) * 1000
                    self.file_done.emit(str(path), elapsed, 0, n_rows)
                    continue
                # Use LRU put so the shared cache stays bounded.
                _lru_put(self._cache, path, sheet_data, _PRELOAD_CACHE_MAXSIZE)
                n_loaded += 1
                elapsed = (time.perf_counter() - t0) * 1000
                self.file_done.emit(str(path), elapsed, len(sheet_data), n_rows)
            except Exception:
                pass
        total_ms = (time.perf_counter() - t_all) * 1000
        self.all_done.emit(len(self._paths), n_loaded, total_ms)


class _SheetWarmer(QThread):
    """Background thread: pre-load all Arrow sheet models for one workbook
    into the shared sheet model cache so subsequent sheet selections are
    instant cache hits."""

    sheet_done = Signal(str)

    def __init__(
        self,
        wb_path: Path,
        sheet_names: list,
        cache: OrderedDict,
        maxsize: int,
        parent=None,
    ):
        super().__init__(parent)
        self._wb_path = wb_path
        self._sheet_names = sheet_names
        self._cache = cache
        self._maxsize = maxsize

    def run(self):
        if ArrowSheetModel is None:
            return
        try:
            import pyarrow as pa
            import pyarrow.ipc as pa_ipc
        except ImportError:
            return
        for name in self._sheet_names:
            if self.isInterruptionRequested():
                break
            cache_key = (self._wb_path, name)
            if _lru_get(self._cache, cache_key) is not None:
                continue
            safe = re.sub(r"[^\w\-]", "_", name)
            arrow_path = self._wb_path.parent / f"{self._wb_path.stem}.{safe}.arrow"
            if not arrow_path.exists():
                continue
            try:
                mmap = pa.memory_map(str(arrow_path), "r")
                reader = pa_ipc.open_file(mmap)
                batch = reader.get_batch(0)
                model = ArrowSheetModel(batch)
                merged_cells = model.merged_cells
                group_rows_0 = {r - 1 for r in model.row_outlines}
                group_cols_0 = {c - 1 for c in model.col_outlines}
                _lru_put(
                    self._cache,
                    cache_key,
                    (model, merged_cells, group_rows_0, group_cols_0),
                    self._maxsize,
                )
                self.sheet_done.emit(name)
            except Exception:
                pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Theia")
        self.resize(1500, 900)
        self._settings = QSettings("Theia", "Theia")
        self._theme_key = _setting_theme(self._settings)
        self._dark_mode = _setting_bool(self._settings, "theme/dark", True)
        self._sidebar_visible = _setting_bool(self._settings, "view/sidebar", True)
        self._theme_combo: QComboBox | None = None
        self._dark_toggle: QCheckBox | None = None
        self._theme_actions: dict[str, QAction] = {}
        self._nav_widgets: tuple[QWidget, QWidget] | None = None
        self._splitter: QSplitter | None = None

        # State
        self._workbooks: OrderedDict[Source, Workbook] = OrderedDict()
        self._current_wb: Workbook | None = None
        self._current_label: str | None = None
        self._current_source: Source | None = None
        self._comparison_dialogs: list[ComparisonDialog] = []

        # Preload cache: Path -> {sheet_name -> list[list]} populated by _PreloadWorker.
        # LRU OrderedDict bounded to _PRELOAD_CACHE_MAXSIZE files.
        self._preload_cache: OrderedDict = OrderedDict()
        self._preload_worker: _PreloadWorker | None = None
        self._preload_done = 0
        self._preload_total = 0

        # Per-session caches cleared on folder reload
        self._sidecar_cache: dict = {}    # Path -> full sidecar JSON dict
        self._col_width_cache: dict = {}  # (Path, sheet_name) -> [int, ...]

        # Sheet model cache: (Path, sheet_name) -> (model, merged_cells, group_rows_0, group_cols_0)
        # LRU OrderedDict bounded to _SHEET_MODEL_CACHE_MAXSIZE entries.
        self._sheet_model_cache: OrderedDict = OrderedDict()
        self._warmer: _SheetWarmer | None = None

        # ---- Companies pane (tree: analyst -> companies) ----
        self.company_filter = QLineEdit()
        self.company_filter.setPlaceholderText("Filter companies…")
        self.company_filter.setClearButtonEnabled(True)

        self._companies_model = QStandardItemModel()
        self._companies_proxy = QSortFilterProxyModel()
        self._companies_proxy.setSourceModel(self._companies_model)
        self._companies_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._companies_proxy.setRecursiveFilteringEnabled(True)

        self.company_tree = QTreeView()
        self.company_tree.setModel(self._companies_proxy)
        self.company_tree.setHeaderHidden(True)
        self.company_tree.setEditTriggers(QTreeView.NoEditTriggers)
        self.company_tree.setUniformRowHeights(True)
        self.company_tree.setIndentation(14)
        self.company_tree.selectionModel().currentChanged.connect(self._on_company_selected)
        self.company_filter.textChanged.connect(self._on_companies_filter_changed)

        companies_pane = QWidget()
        companies_pane.setObjectName("nav-pane")
        cp_outer = QVBoxLayout(companies_pane)
        cp_outer.setContentsMargins(0, 0, 0, 0)
        cp_outer.setSpacing(0)
        cp_hdr = QLabel("COMPANIES")
        cp_hdr.setObjectName("section-header")
        cp_outer.addWidget(cp_hdr)
        cp_inner = QWidget()
        cp_layout = QVBoxLayout(cp_inner)
        cp_layout.setContentsMargins(8, 8, 8, 8)
        cp_layout.setSpacing(6)
        cp_layout.addWidget(self.company_filter)
        cp_layout.addWidget(self.company_tree, 1)
        cp_outer.addWidget(cp_inner, 1)

        # ---- Sheets pane ----
        (
            sheets_pane,
            self.sheet_filter,
            self.sheet_list,
            self._sheets_model,
            self._sheets_proxy,
        ) = _make_pane("Filter sheets…", title="Sheets")
        sheets_pane.setObjectName("nav-pane")
        self.sheet_list.selectionModel().currentChanged.connect(self._on_sheet_selected)

        # ---- Table ---- (4-view composite with Excel-style freeze panes)
        self.table = FrozenPaneTable()
        self._default_freeze = (1, 1)  # header row + label column

        # ---- Splitter ----
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(companies_pane)
        splitter.addWidget(sheets_pane)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([260, 200, 1040])
        splitter.setChildrenCollapsible(False)
        self._splitter = splitter
        self._nav_widgets = (companies_pane, sheets_pane)
        self.setCentralWidget(splitter)

        # ---- Menu ----
        open_file = QAction("Open &File…", self)
        open_file.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        open_file.setShortcut(QKeySequence.Open)
        open_file.triggered.connect(self._open_file_dialog)

        open_folder = QAction("Open F&older…", self)
        open_folder.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        open_folder.setShortcut("Ctrl+Shift+O")
        open_folder.triggered.connect(self._open_folder_dialog)

        self._compare_action = QAction("&Compare Selected Cells…", self)
        self._compare_action.setShortcut("Ctrl+Shift+C")
        self._compare_action.triggered.connect(self._compare_selected)

        focus_company = QAction("Focus &Companies Filter", self)
        focus_company.setShortcut("Ctrl+L")
        focus_company.triggered.connect(lambda: (self.company_filter.setFocus(), self.company_filter.selectAll()))

        focus_sheet = QAction("Focus &Sheets Filter", self)
        focus_sheet.setShortcut("Ctrl+Shift+L")
        focus_sheet.triggered.connect(lambda: (self.sheet_filter.setFocus(), self.sheet_filter.selectAll()))

        freeze_at = QAction("&Freeze at Selection", self)
        freeze_at.setShortcut("Ctrl+Shift+F")
        freeze_at.triggered.connect(self._freeze_at_selection)

        unfreeze = QAction("&Unfreeze Panes", self)
        unfreeze.setShortcut("Ctrl+Shift+U")
        unfreeze.triggered.connect(lambda: self.table.setFreeze(0, 0))

        self._toggle_groups_act = QAction("Toggle &Groups", self)
        self._toggle_groups_act.setShortcut("Ctrl+Shift+G")
        self._toggle_groups_act.triggered.connect(self._toggle_groups)

        self._sidebar_action = QAction("&Sidebar", self)
        self._sidebar_action.setCheckable(True)
        self._sidebar_action.setChecked(self._sidebar_visible)
        self._sidebar_action.setShortcut("Ctrl+B")
        self._sidebar_action.toggled.connect(self._set_sidebar_visible)

        self._dark_action = QAction("&Dark Mode", self)
        self._dark_action.setCheckable(True)
        self._dark_action.setChecked(self._dark_mode)
        self._dark_action.triggered.connect(self._set_dark_mode)

        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for key in THEME_ORDER:
            act = QAction(THEMES[key]["label"], self)
            act.setCheckable(True)
            act.setChecked(key == self._theme_key)
            act.triggered.connect(lambda checked=False, theme_key=key: self._set_theme(theme_key))
            theme_group.addAction(act)
            self._theme_actions[key] = act

        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.Quit)
        quit_act.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(open_file)
        file_menu.addAction(open_folder)
        file_menu.addSeparator()
        file_menu.addAction(focus_company)
        file_menu.addAction(focus_sheet)
        file_menu.addSeparator()
        file_menu.addAction(quit_act)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self._sidebar_action)
        view_menu.addAction(self._dark_action)
        theme_menu = view_menu.addMenu("&Theme")
        for key in THEME_ORDER:
            theme_menu.addAction(self._theme_actions[key])
        view_menu.addSeparator()
        view_menu.addAction(freeze_at)
        view_menu.addAction(unfreeze)
        view_menu.addSeparator()
        view_menu.addAction(self._toggle_groups_act)

        compare_menu = self.menuBar().addMenu("&Compare")
        compare_menu.addAction(self._compare_action)

        self._build_toolbar(open_file, open_folder)

        # ---- Status bar ----
        self._status = QLabel(
            "No file loaded — open a folder (Ctrl+Shift+O), a .zip of models, or a single .xlsx (Ctrl+O); drag & drop also works"
        )
        self.statusBar().addWidget(self._status, 1)  # stretch=1 takes all left space

        # Preload progress widget: "Loading 42%  [====    ]"
        self._cache_label = QLabel("")
        self._cache_label.setMinimumWidth(120)
        self._preload_bar = QProgressBar()
        self._preload_bar.setTextVisible(False)
        self._preload_bar.setFixedWidth(140)
        self._preload_bar.setVisible(False)

        _pw = QWidget()
        _pw_lay = QHBoxLayout(_pw)
        _pw_lay.setContentsMargins(0, 0, 8, 0)
        _pw_lay.setSpacing(8)
        _pw_lay.addWidget(self._cache_label)
        _pw_lay.addWidget(self._preload_bar)
        self.statusBar().addPermanentWidget(_pw)

        # ---- Drag & drop ----
        self.setAcceptDrops(True)
        self._sync_theme_controls()
        self._set_sidebar_visible(self._sidebar_visible, persist=False)
        self._apply_theme()

    # ---- Theme / view controls ----

    def _build_toolbar(self, open_file: QAction, open_folder: QAction):
        toolbar = QToolBar("Controls", self)
        toolbar.setObjectName("main-toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.addAction(open_file)
        toolbar.addAction(open_folder)
        toolbar.addAction(self._compare_action)

        spacer = QWidget()
        spacer.setObjectName("toolbar-spacer")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        theme_label = QLabel("Theme")
        theme_label.setObjectName("toolbar-label")
        self._theme_combo = QComboBox()
        self._theme_combo.setMinimumWidth(132)
        self._theme_combo.setObjectName("theme-combo")
        for key in THEME_ORDER:
            self._theme_combo.addItem(THEMES[key]["label"], key)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)

        self._dark_toggle = QCheckBox("Dark")
        self._dark_toggle.setObjectName("dark-toggle")
        self._dark_toggle.toggled.connect(self._set_dark_mode)

        toolbar.addWidget(theme_label)
        toolbar.addWidget(self._theme_combo)
        toolbar.addWidget(self._dark_toggle)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

    def _on_theme_combo_changed(self, index: int):
        if self._theme_combo is None:
            return
        key = self._theme_combo.itemData(index)
        if key:
            self._set_theme(str(key))

    def _set_theme(self, key: str):
        if key not in THEMES:
            key = "midnight"
        if self._theme_key == key:
            self._sync_theme_controls()
            return
        self._theme_key = key
        self._settings.setValue("theme/name", key)
        self._sync_theme_controls()
        self._apply_theme()

    def _set_dark_mode(self, enabled: bool):
        enabled = bool(enabled)
        if self._dark_mode == enabled:
            self._sync_theme_controls()
            return
        self._dark_mode = enabled
        self._settings.setValue("theme/dark", enabled)
        self._sync_theme_controls()
        self._apply_theme()

    def _set_sidebar_visible(self, visible: bool, persist: bool = True):
        self._sidebar_visible = bool(visible)
        if persist:
            self._settings.setValue("view/sidebar", self._sidebar_visible)
        if self._nav_widgets is not None:
            for widget in self._nav_widgets:
                widget.setVisible(self._sidebar_visible)
        if self._splitter is not None and self._sidebar_visible:
            sizes = self._splitter.sizes()
            if len(sizes) >= 3 and sizes[0] == 0 and sizes[1] == 0:
                self._splitter.setSizes([260, 200, max(700, sizes[2])])
        if hasattr(self, "_sidebar_action"):
            with QSignalBlocker(self._sidebar_action):
                self._sidebar_action.setChecked(self._sidebar_visible)

    def _sync_theme_controls(self):
        if self._theme_combo is not None:
            idx = self._theme_combo.findData(self._theme_key)
            with QSignalBlocker(self._theme_combo):
                self._theme_combo.setCurrentIndex(max(idx, 0))
        if self._dark_toggle is not None:
            with QSignalBlocker(self._dark_toggle):
                self._dark_toggle.setChecked(self._dark_mode)
        if hasattr(self, "_dark_action"):
            with QSignalBlocker(self._dark_action):
                self._dark_action.setChecked(self._dark_mode)
        for key, action in self._theme_actions.items():
            with QSignalBlocker(action):
                action.setChecked(key == self._theme_key)

    def _apply_theme(self):
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self._theme_key, self._dark_mode))

    # ---- Public open API ----

    def open_path(self, path: Path):
        """Open a file, folder, or zip, auto-detecting which."""
        path = Path(path)
        if path.is_dir():
            self.open_folder(path)
        elif path.suffix.lower() == ".zip":
            self.open_zip(path)
        else:
            self.open_file(path)

    def open_file(self, path: Path):
        self.open_files([path])

    def open_files(self, paths: list[Path]):
        if not paths:
            return
        items = []
        errors = []
        for path in paths:
            if path.suffix.lower() == ".zip":
                try:
                    for inner in list_zip_xlsx(path):
                        if not Path(inner).name.startswith("~$"):
                            label = _jp_label(Path(inner).stem) or Path(inner).stem
                            items.append(("(local)", path.stem, label, (path, inner)))
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
            elif path.suffix.lower() in _SUPPORTED_SUFFIXES and not path.name.startswith("~$"):
                items.append(("(local)", "(files)", _jp_label(path.stem) or path.stem, path))
        self._populate(items, root_label=f"{len(paths)} selected files")
        if errors:
            self._status.setText("Failed to open archives: " + "; ".join(errors))
        self.setWindowTitle(f"{paths[0].name if len(paths) == 1 else str(len(paths)) + ' files'} — Theia")

    def open_folder(self, folder: Path):
        # Recurse so models in subfolders are picked up. Also look inside any
        # .zip files we find. Items become (broker, analyst, label, source).
        items: list[tuple[str, str, str, Source]] = []
        skipped = 0
        for p in folder.rglob("*"):
            if not p.is_file():
                continue
            suf = p.suffix.lower()
            if suf in _SUPPORTED_SUFFIXES:
                if p.name.startswith("~$"):
                    skipped += 1
                    continue
                label = _jp_label(p.stem) or p.stem
                broker, analyst = _broker_analyst_from_folder_path(p, folder)
                items.append((broker, analyst, label, p))
            elif suf == ".zip":
                try:
                    for inner in list_zip_xlsx(p):
                        label = _jp_label(Path(inner).stem) or Path(inner).stem
                        if not Path(inner).name.startswith("~$"):
                            broker = _broker_from_path(p)
                            analyst = _analyst_from_zip_entry(inner) or p.stem
                            items.append((broker, analyst, label, (p, inner)))
                        else:
                            skipped += 1
                except Exception:
                    continue
        self._populate(items, root_label=str(folder), skipped=skipped)
        self.setWindowTitle(f"{folder.name} — Theia")

    def open_zip(self, zip_path: Path):
        try:
            inner_names = list_zip_xlsx(zip_path)
        except Exception as e:
            self._status.setText(f"Failed to open {zip_path.name}: {e}")
            return
        items: list[tuple[str, str, str, Source]] = []
        skipped = 0
        broker = _broker_from_path(zip_path)
        for n in inner_names:
            label = _jp_label(Path(n).stem) or Path(n).stem
            if not Path(n).name.startswith("~$"):
                analyst = _analyst_from_zip_entry(n)
                items.append((broker, analyst, label, (zip_path, n)))
            else:
                skipped += 1
        self._populate(items, root_label=str(zip_path), skipped=skipped)
        self.setWindowTitle(f"{zip_path.name} — Theia")

    # ---- Internals ----

    def _populate(self, items: list[tuple[str, str, str, Source]], root_label: str, skipped: int = 0):
        """items = [(broker, analyst, label, source), ...]. Builds the
        three-level tree model (broker -> analyst -> company) and resets state."""
        for worker in (self._preload_worker, self._warmer):
            if worker is not None:
                worker.requestInterruption()
                worker.wait()
        if self._warmer is not None:
            self._warmer.deleteLater()
        self._warmer = None
        self._start_preload([])
        for wb in self._workbooks.values():
            wb.close()
        self._workbooks.clear()
        self._current_wb = None
        self._current_label = None
        self._current_source = None
        self._sidecar_cache.clear()
        self._col_width_cache.clear()
        self._sheet_model_cache.clear()
        self._companies_model.clear()
        self._sheets_model.setStringList([])
        self.table.setModel(None)

        if not items:
            tail = f" ({skipped} temporary files skipped)" if skipped else ""
            self._status.setText(f"{root_label}{tail}   ·   no Excel files found")
            return

        by_broker: dict[str, dict[str, list[tuple[str, Source]]]] = {}
        for broker, analyst, label, source in items:
            by_broker.setdefault(broker, {}).setdefault(analyst, []).append((label, source))

        root = self._companies_model.invisibleRootItem()
        for broker in sorted(by_broker):
            analysts = by_broker[broker]
            n_in_broker = sum(len(v) for v in analysts.values())
            b_item = QStandardItem(f"{broker}   ({n_in_broker})")
            b_item.setEditable(False)
            b_item.setSelectable(False)
            bf = b_item.font(); bf.setBold(True); bf.setPointSize(bf.pointSize() + 1)
            b_item.setFont(bf)
            root.appendRow(b_item)

            for analyst in sorted(analysts):
                companies = sorted(analysts[analyst], key=lambda x: x[0])
                a_item = QStandardItem(f"{analyst}   ({len(companies)})")
                a_item.setEditable(False)
                a_item.setSelectable(False)
                af = a_item.font(); af.setBold(True)
                a_item.setFont(af)
                a_item.setForeground(QColor("#57606a"))
                b_item.appendRow(a_item)

                for label, source in companies:
                    c_item = QStandardItem(label)
                    c_item.setEditable(False)
                    c_item.setData(source, Qt.UserRole)
                    a_item.appendRow(c_item)

        self.company_tree.expandAll()

        n_analysts = sum(len(v) for v in by_broker.values())
        note = f" ({skipped} temporary files skipped)" if skipped else ""
        self._status.setText(
            f"{root_label}{note}   ·   {len(items)} file{'s' if len(items) != 1 else ''}"
            f" across {n_analysts} analyst{'s' if n_analysts != 1 else ''}"
            f" / {len(by_broker)} broker{'s' if len(by_broker) != 1 else ''}"
        )

        # Auto-select the first company (broker[0] -> analyst[0] -> company[0])
        b_idx = self._companies_proxy.index(0, 0)
        if b_idx.isValid():
            a_idx = self._companies_proxy.index(0, 0, b_idx)
            if a_idx.isValid():
                c_idx = self._companies_proxy.index(0, 0, a_idx)
                if c_idx.isValid():
                    self.company_tree.setCurrentIndex(c_idx)

        # Only warm a few first sheets; archive size must not determine RAM use.
        xlsx_paths = [src for _, _, _, src in items if isinstance(src, Path)]
        self._start_preload(xlsx_paths[:_PRELOAD_MAX_FILES])

    # ---- Preload ----

    def _start_preload(self, paths: list):
        if self._preload_worker is not None:
            self._preload_worker.requestInterruption()
            self._preload_worker.wait()
            self._preload_worker.deleteLater()
            self._preload_worker = None
        self._preload_cache.clear()
        self._preload_done = 0
        self._preload_total = len(paths)
        if not paths:
            self._cache_label.setText("")
            self._preload_bar.setVisible(False)
            return
        self._preload_bar.setRange(0, self._preload_total)
        self._preload_bar.setValue(0)
        self._preload_bar.setVisible(True)
        self._cache_label.setText("Loading…  0%")
        worker = _PreloadWorker(paths, self._preload_cache, self)
        worker.file_done.connect(self._on_preload_file)
        worker.all_done.connect(self._on_preload_done)
        self._preload_worker = worker
        worker.start()

    def _on_preload_file(self, _path: str, elapsed_ms: float, n_sheets: int, n_rows: int):
        if self.sender() is not self._preload_worker:
            return
        self._preload_done += 1
        self._preload_bar.setValue(self._preload_done)
        pct = int(100 * self._preload_done / self._preload_total) if self._preload_total else 0
        self._cache_label.setText(f"Loading…  {pct}%")

    def _on_preload_done(self, n_total: int, n_loaded: int, total_ms: float):
        if self.sender() is not self._preload_worker:
            return
        self._preload_bar.setVisible(False)
        self._cache_label.setText(
            f"✓  {n_loaded}/{n_total} cached  ·  {total_ms / 1000:.0f}s"
        )

    # ---- Company / sheet selection ----

    def _on_companies_filter_changed(self, text: str):
        self._companies_proxy.setFilterFixedString(text)
        # When filtering, expand everything so matches are visible
        self.company_tree.expandAll()

    def _open_file_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Excel file or zip",
            "",
            "Excel & zip (*.xlsx *.xls *.xlsm *.xlsb *.zip);;Excel files (*.xlsx *.xls *.xlsm *.xlsb);;Zip archives (*.zip);;All files (*.*)",
        )
        if len(paths) == 1:
            self.open_path(Path(paths[0]))
        elif paths:
            self.open_files([Path(p) for p in paths])

    def _open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Open folder of Excel files")
        if folder:
            self.open_folder(Path(folder))

    def _on_company_selected(self, current, previous):
        if not current.isValid():
            return
        src_idx = self._companies_proxy.mapToSource(current)
        item = self._companies_model.itemFromIndex(src_idx)
        if item is None:
            return
        source = item.data(Qt.UserRole)
        if source is None:
            # Analyst (parent) node — selection model usually skips these
            # because setSelectable(False), but defend just in case.
            return
        label = item.text()
        wb = _lru_get(self._workbooks, source)
        if wb is None:
            try:
                wb = Workbook(source)
            except Exception as e:
                self._status.setText(f"Failed to open {label}: {e}")
                self._sheets_model.setStringList([])
                self.table.setModel(None)
                self._current_wb = None
                self._current_source = None
                return
            self._workbooks[source] = wb
            while len(self._workbooks) > 3:
                _, old = self._workbooks.popitem(last=False)
                old.close()
        self._current_wb = wb
        self._current_label = label
        self._current_source = source
        visible = [s for s in wb.sheet_names if not _is_hidden_sheet(s)]
        self._sheets_model.setStringList(visible)
        if visible:
            self.sheet_list.setCurrentIndex(self._sheets_proxy.index(0, 0))
            # ② Start background warmer to pre-load Arrow models for all sheets
            self._start_sheet_warmer(wb.path, visible)
        else:
            self.table.setModel(None)
            n_hidden = len(wb.sheet_names) - len(visible)
            tail = f" (all {n_hidden} sheet{'s' if n_hidden != 1 else ''} filtered out)" if n_hidden else ""
            self._status.setText(f"{label}   ·   (no sheets){tail}")

    def _on_sheet_selected(self, current, previous):
        if not current.isValid() or self._current_wb is None:
            return
        name = self._sheets_proxy.data(current, Qt.DisplayRole)
        wb_path = self._current_wb.path
        t0 = time.perf_counter()

        cache_key = (wb_path, name)

        # Sheet model cache hit: re-use the already-built model and metadata.
        cached_entry = _lru_get(self._sheet_model_cache, cache_key)
        if cached_entry is not None:
            model, merged_cells, group_rows_0, group_cols_0 = cached_entry
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._apply_model_to_table(model, merged_cells, group_rows_0, group_cols_0, cache_key)
            group_note = f"   ·   {len(group_rows_0)} grouped rows" if group_rows_0 else ""
            self._status.setText(
                f"{wb_path.name}   ·   {name}   ·   "
                f"{model.rowCount():,} rows × {model.columnCount()} cols"
                f"{group_note}   ·   {elapsed_ms:.1f} ms (model-cache)"
            )
            return

        # Try Arrow path: <parent>/<stem>.<safe_sheet_name>.arrow (mmap, pre-formatted)
        arrow_model = self._try_load_arrow(wb_path, name)
        if arrow_model is not None:
            merged_cells = arrow_model.merged_cells
            group_rows_0 = {r - 1 for r in arrow_model.row_outlines}
            group_cols_0 = {c - 1 for c in arrow_model.col_outlines}
            elapsed_ms = (time.perf_counter() - t0) * 1000
            _lru_put(
                self._sheet_model_cache,
                cache_key,
                (arrow_model, merged_cells, group_rows_0, group_cols_0),
                _SHEET_MODEL_CACHE_MAXSIZE,
            )
            self._apply_model_to_table(arrow_model, merged_cells, group_rows_0, group_cols_0, cache_key)
            group_note = f"   ·   {len(group_rows_0)} grouped rows" if group_rows_0 else ""
            self._status.setText(
                f"{wb_path.name}   ·   {name}   ·   "
                f"{arrow_model.rowCount():,} rows × {arrow_model.columnCount()} cols"
                f"{group_note}   ·   {elapsed_ms:.1f} ms (arrow)"
            )
            return

        # Fallback: calamine / preload-cache path.
        file_cache = _lru_get(self._preload_cache, wb_path)
        cached_rows = file_cache.get(name) if file_cache is not None else None
        if cached_rows is not None:
            rows = cached_rows
            load_src = "cache"
        else:
            try:
                sheet = self._current_wb.load_sheet(name)
            except Exception as e:
                self._status.setText(f"Failed to load sheet '{name}': {e}")
                return
            rows = sheet.rows
            load_src = "disk"

        elapsed_ms = (time.perf_counter() - t0) * 1000
        sc = self._sidecar_for(name)
        row_fmt = {int(k): v for k, v in sc.get("row_formats", {}).items()}
        cell_fmt = {
            tuple(int(p) for p in k.split(",")): v
            for k, v in sc.get("cell_formats", {}).items()
        }
        hidden_rows = set(sc.get("hidden_rows", []))
        hidden_cols = set(sc.get("hidden_cols", []))
        merged_cells = sc.get("merged_cells", [])
        row_outlines = {int(k): v for k, v in sc.get("row_outlines", {}).items()}
        col_outlines = {int(k): v for k, v in sc.get("col_outlines", {}).items()}
        group_rows_0 = {r - 1 for r in row_outlines}
        group_cols_0 = {c - 1 for c in col_outlines}

        model = SheetModel(
            rows,
            row_formats=row_fmt,
            cell_formats=cell_fmt,
            hidden_rows=hidden_rows,
            hidden_cols=hidden_cols,
        )

        _lru_put(
            self._sheet_model_cache,
            cache_key,
            (model, merged_cells, group_rows_0, group_cols_0),
            _SHEET_MODEL_CACHE_MAXSIZE,
        )

        self._apply_model_to_table(model, merged_cells, group_rows_0, group_cols_0, cache_key)
        group_note = f"   ·   {len(group_rows_0)} grouped rows" if group_rows_0 else ""
        self._status.setText(
            f"{wb_path.name}   ·   {name}   ·   "
            f"{model.rowCount():,} rows × {model.columnCount()} cols"
            f"{group_note}   ·   {elapsed_ms:.1f} ms ({load_src})"
        )

    _CHAR_PX = 7  # approx px per character at 12-13px Segoe UI
    _OVERFLOW_TEXT_MIN_CHARS = 24

    def _apply_model_to_table(self, model, merged_cells, group_rows_0, group_cols_0, cache_key):
        """③ Swap in a new model while suppressing intermediate viewport repaints."""
        for v in self.table._views():
            v.setUpdatesEnabled(False)
        try:
            self.table.setModel(model)
            self.table.setMergedCells(merged_cells)
            self.table.setGroups(group_rows_0, group_cols_0)
            self._autosize_columns(model, cache_key)
            fr, fc = self._default_freeze
            self.table.setFreeze(min(fr, model.rowCount()), min(fc, model.columnCount()))
        finally:
            for v in self.table._views():
                v.setUpdatesEnabled(True)

    def _start_sheet_warmer(self, wb_path: Path, sheet_names: list):
        """② Start background thread to pre-load Arrow models for all sheets."""
        if self._warmer is not None:
            self._warmer.requestInterruption()
            self._warmer.wait()
            self._warmer.deleteLater()
            self._warmer = None
        if ArrowSheetModel is None or not sheet_names:
            return
        warmer = _SheetWarmer(
            wb_path, sheet_names, self._sheet_model_cache, _SHEET_MODEL_CACHE_MAXSIZE, self
        )
        self._warmer = warmer
        warmer.start()

    def _autosize_columns(self, model, cache_key: tuple):
        """Estimate column widths and cache per sheet.

        Fast path: read pre-baked widths from Arrow metadata (zero Python iteration).
        Slow path: measure from data via raw_value() (first 60 rows)."""
        cached = self._col_width_cache.get(cache_key)
        if cached is not None:
            self.table.setColumnWidths(cached)
            return
        # Fast path: Arrow model carries pre-baked widths from the sidecar writer.
        if hasattr(model, "col_widths") and model.col_widths:
            self._col_width_cache[cache_key] = model.col_widths
            self.table.setColumnWidths(model.col_widths)
            return
        # Slow path: measure from raw_value (SheetModel fallback)
        n_rows = model.rowCount()
        n_cols = model.columnCount()
        sample_n = min(60, n_rows)
        widths = []
        for c in range(n_cols):
            max_len = 0
            for r in range(sample_n):
                v = model.raw_value(r, c)
                if v is not None:
                    if self._is_repeated_merged_text(model, r, c, v):
                        continue
                    if self._is_overflow_width_candidate(model, r, c, v):
                        continue
                    s = v if isinstance(v, str) else str(v)
                    if s:
                        max_len = max(max_len, len(s))
            w = min(max(max_len * self._CHAR_PX + 8, _MIN_COL_W), _MAX_COL_W)
            widths.append(w)
        self._col_width_cache[cache_key] = widths
        self.table.setColumnWidths(widths)

    def _is_overflow_width_candidate(self, model, row: int, col: int, value) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip()
        if len(text) < self._OVERFLOW_TEXT_MIN_CHARS or "\n" in text:
            return False
        if col + 1 >= model.columnCount():
            return False
        right = model.raw_value(row, col + 1)
        return right is None or right == ""

    def _is_repeated_merged_text(self, model, row: int, col: int, value) -> bool:
        if col <= 0 or not isinstance(value, str) or value == "":
            return False
        return model.raw_value(row, col - 1) == value

    def _try_load_arrow(self, wb_path: Path, sheet_name: str):
        """Open a pre-formatted .arrow sidecar for the given sheet, or return None.

        The safe name formula must match the sidecar writer:
        re.sub(r'[^\\w\\-]', '_', sheet_name)."""
        if ArrowSheetModel is None:
            return None
        safe = re.sub(r"[^\w\-]", "_", sheet_name)
        arrow_path = wb_path.parent / f"{wb_path.stem}.{safe}.arrow"
        if not arrow_path.exists():
            return None
        try:
            import pyarrow as pa
            mmap = pa.memory_map(str(arrow_path), "r")
            reader = pa.ipc.open_file(mmap)
            batch = reader.get_batch(0)
            return ArrowSheetModel(batch)
        except Exception:
            return None

    def _sidecar_for(self, sheet_name: str) -> dict:
        """Return the sidecar JSON's per-sheet metadata dict, or {} if none.
        The full sidecar JSON is cached per file path to avoid re-reading
        on every sheet switch within the same workbook."""
        if self._current_wb is None:
            return {}
        wb_path = self._current_wb.path
        if wb_path not in self._sidecar_cache:
            sidecar = wb_path.with_suffix(".json")
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
            except Exception:
                data = {}
            self._sidecar_cache[wb_path] = data
        return self._sidecar_cache[wb_path].get("sheets", {}).get(sheet_name, {})

    def _freeze_at_selection(self):
        cur = self.table.currentIndex()
        if cur is None or not cur.isValid():
            return
        self.table.setFreeze(cur.row(), cur.column())

    def _toggle_groups(self):
        if not self.table._group_rows and not self.table._group_cols:
            self._status.setText("No outline groups in this sheet")
            return
        collapsed = self.table.toggleGroups()
        state = "collapsed" if collapsed else "expanded"
        parts = []
        if self.table._group_rows:
            n = len(self.table._group_rows)
            parts.append(f"{n} row{'s' if n != 1 else ''}")
        if self.table._group_cols:
            n = len(self.table._group_cols)
            parts.append(f"{n} col{'s' if n != 1 else ''}")
        self._status.setText(f"Groups {state}: {', '.join(parts)}  (Ctrl+Shift+G to toggle)")

    # ---- Drag & drop ----

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if not urls:
            return
        first = Path(urls[0].toLocalFile())
        if len(urls) == 1 and (first.is_dir() or first.suffix.lower() == ".zip"):
            self.open_path(first)
            return
        paths = [Path(url.toLocalFile()) for url in urls]
        paths = [p for p in paths if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES | {".zip"}]
        if paths:
            self.open_files(paths)

    def _compare_selected(self):
        if self._current_wb is None or self._current_source is None:
            self._status.setText("Open a folder or multiple Excel files, then select cells to compare")
            return
        selection = self.table.br.selectionModel()
        ranges = selection.selection()
        if sum(r.width() * r.height() for r in ranges) > 64:
            self._status.setText("Select up to 64 cells for comparison")
            return
        indices = sorted(selection.selectedIndexes(), key=lambda i: (i.row(), i.column()))
        if not indices:
            self._status.setText("Select cells in the sheet, then choose Compare Selected Cells")
            return
        sheet = self._sheets_proxy.data(self.sheet_list.currentIndex(), Qt.DisplayRole)
        if not sheet:
            return
        metrics = []
        model = self.table.model()
        for index in indices:
            row, col = index.row(), index.column()
            title = f"{sheet}!{_col_letter(col)}{row + 1}"
            for c in range(col - 1, -1, -1):
                value = model.data(model.index(row, c), Qt.DisplayRole)
                if value and not str(value).replace(",", "").replace(".", "").replace("-", "").isdigit():
                    title = str(value)
                    break
            metrics.append(Metric(title, row, col))
        sources = []

        def collect(parent):
            for r in range(self._companies_proxy.rowCount(parent)):
                index = self._companies_proxy.index(r, 0, parent)
                source = self._companies_proxy.data(index, Qt.UserRole)
                if source is not None:
                    sources.append((self._companies_proxy.data(index, Qt.DisplayRole), source))
                collect(index)

        collect(self._companies_proxy.index(-1, -1))
        dialog = ComparisonDialog(sources, self._current_source, sheet, metrics, self)
        dialog.open_source.connect(self._open_comparison_source)
        self._comparison_dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self._comparison_dialogs.remove(dialog))
        dialog.show()

    def _open_comparison_source(self, source, sheet, row, col):
        self.company_filter.clear()
        self.sheet_filter.clear()
        for item in self._companies_model.findItems("*", Qt.MatchWildcard | Qt.MatchRecursive):
            if item.data(Qt.UserRole) != source:
                continue
            self.company_tree.setCurrentIndex(self._companies_proxy.mapFromSource(item.index()))
            names = self._sheets_model.stringList()
            if sheet not in names:
                self._status.setText(f"Missing sheet: {sheet}")
                return
            self.sheet_list.setCurrentIndex(self._sheets_proxy.mapFromSource(self._sheets_model.index(names.index(sheet))))
            model = self.table.model()
            if model is not None:
                index = model.index(row, col)
                self.table.br.selectionModel().setCurrentIndex(index, QItemSelectionModel.ClearAndSelect)
                self.table.br.scrollTo(index)
            self.raise_()
            return
        self._status.setText("This file is no longer in the current folder or file list")

    def closeEvent(self, event):
        for dialog in self._comparison_dialogs:
            if dialog.worker is not None:
                dialog.worker.cancel()
                dialog.worker.wait()
        for worker in (self._preload_worker, self._warmer):
            if worker is not None:
                worker.requestInterruption()
                worker.wait()
        for wb in self._workbooks.values():
            wb.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Theia")
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet("midnight", True))

    font: QFont = QFont("Arial")
    default_size = app.font().pointSize()
    if default_size > 0:
        font.setPointSize(max(9, default_size - 1))
    app.setFont(font)

    w = MainWindow()
    w.show()
    if len(sys.argv) > 1:
        w.open_path(Path(sys.argv[1]))
    sys.exit(app.exec())
