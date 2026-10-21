import json
import re
import sys
import time
from collections import OrderedDict
from math import ceil
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QSettings,
    QSignalBlocker,
    QSortFilterProxyModel,
    QStringListModel,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QKeySequence,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenuBar,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from python_calamine import CalamineWorkbook

from theia.compare import ComparisonDialog, Metric, load_preset
from theia.model import SheetModel, _col_letter
from theia.paths import models_root
from theia.table import FrozenPaneTable, _parse_excel_range
from theia.theme import THEME_ORDER, THEMES, build_palette, build_stylesheet
from theia.workbook import Source, Workbook, list_zip_xlsx

# Loaded only when a workbook has an Arrow sidecar.
ArrowSheetModel = None


_SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".xlsm", ".xlsb"}


def _setting_bool(settings: QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _setting_theme(settings: QSettings) -> str:
    value = str(settings.value("theme/name", "theia"))
    return value if value in THEMES else "theia"


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
_SHEET_MODEL_CACHE_MAXSIZE = 4

# Maximum number of paths sent to the preload worker per folder load
_PRELOAD_MAX_FILES = 0


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


def _collection_from_path(source: Path) -> str:
    """Use the containing folder as the archive collection label."""
    return source.parent.name or "(local)"


def _group_from_zip_entry(entry: str) -> str:
    """Extract the group bucket from a zip entry's path."""
    parts = entry.replace("\\", "/").strip("/").split("/")
    if len(parts) > 1:
        if parts[0].lower() in {"models", "files", "model"}:
            return parts[1] if len(parts) > 2 else parts[0]
        return parts[0]
    return "unknown"


def _collection_group_from_folder_path(p: Path, root: Path) -> tuple[str, str]:
    """Return (collection, group) inferred from a workbook's path under root.

    Conventions:
      <root>/<collection>/<group>/<file>.xlsx   ->  (collection, group)
      <root>/<group>/<file>.xlsx            ->  ("(local)", group)
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
    rest = stem[: m.start()] + stem[m.end() :]
    rest = re.sub(r"[_\-/]+", " ", rest)
    rest = _NAME_NOISE_RE.sub(" ", rest)
    rest = re.sub(r"\b\d{6,8}\b", " ", rest)
    rest = re.sub(r"[()\[\]{}.,]", " ", rest)
    name = " ".join(rest.split()).strip()
    return f"{code}  {name}" if name else code


def _is_hidden_sheet(name: str) -> bool:
    low = name.lower()
    return any(p in low for p in _HIDDEN_SHEET_PATTERNS)


def _make_pane(
    placeholder: str, title: str = ""
) -> tuple[QWidget, QLineEdit, QListView, QStringListModel, QSortFilterProxyModel]:
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


_PRELOAD_MAX_ROWS = 200_000  # skip files above this total-row count (outlier guard)


class _PreloadWorker(QThread):
    """Warm the first visible sheet of a few small workbooks."""

    file_done = Signal(str, float, int, int)  # path, ms, n_sheets, n_rows
    all_done = Signal(int, int, float)  # n_total, n_loaded, total_ms

    def __init__(self, paths: list, cache: OrderedDict, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._cache = cache

    def run(self):
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Theia")
        self.resize(1500, 900)
        self._settings = QSettings("Theia", "Theia")
        self._theme_key = _setting_theme(self._settings)
        self._dark_mode = _setting_bool(self._settings, "theme/dark", False)
        self._sidebar_visible = _setting_bool(self._settings, "view/sidebar", True)
        self._zoom_percent = 100
        self._zoom_wheel_delta = 0
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
        self._sidecar_cache: OrderedDict = OrderedDict()  # Path -> full sidecar JSON dict
        self._col_width_cache: OrderedDict = OrderedDict()  # (Path, sheet_name) -> [int, ...]

        # Sheet model cache: (Path, sheet_name) -> (model, merged_cells, group_rows_0, group_cols_0)
        # LRU OrderedDict bounded to _SHEET_MODEL_CACHE_MAXSIZE entries.
        self._sheet_model_cache: OrderedDict = OrderedDict()

        # ---- Companies pane (tree: group -> companies) ----
        self.company_filter = QLineEdit()
        self.company_filter.setPlaceholderText("Find a company…")
        self.company_filter.setClearButtonEnabled(True)

        self._companies_model = QStandardItemModel()
        self._companies_proxy = QSortFilterProxyModel()
        self._companies_proxy.setSourceModel(self._companies_model)
        self._companies_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._companies_proxy.setRecursiveFilteringEnabled(True)
        self._companies_proxy.setAutoAcceptChildRows(True)

        self.company_tree = QTreeView()
        self.company_tree.setModel(self._companies_proxy)
        self.company_tree.setHeaderHidden(True)
        self.company_tree.setEditTriggers(QTreeView.NoEditTriggers)
        self.company_tree.setUniformRowHeights(True)
        self.company_tree.setIndentation(14)
        self.company_tree.selectionModel().currentChanged.connect(self._on_company_selected)
        self.company_filter.textChanged.connect(self._on_companies_filter_changed)

        companies_pane = QFrame()
        companies_pane.setObjectName("nav-pane")
        cp_layout = QVBoxLayout(companies_pane)
        cp_layout.setContentsMargins(8, 10, 8, 8)
        cp_layout.setSpacing(6)
        cp_hdr = QLabel("MODELS")
        cp_hdr.setObjectName("section-header")
        cp_layout.addWidget(cp_hdr)
        cp_layout.addWidget(self.company_filter)
        cp_layout.addWidget(self.company_tree, 1)

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

        sheets_pane.setParent(self)
        sheets_pane.hide()

        self._document_title = QLabel("Valuation models")
        self._document_title.setObjectName("app-title")
        self._document_title.setTextFormat(Qt.PlainText)
        self._cell_address = QLineEdit()
        self._cell_address.setObjectName("cell-address")
        self._cell_address.setFixedWidth(72)
        self._cell_address.setPlaceholderText("A1")
        self._cell_address.setAccessibleName("Go to cell")
        self._cell_address.setToolTip("Type a cell address and press Enter to go there")
        self._cell_address.returnPressed.connect(self._go_to_cell)
        self._cell_value = QLineEdit()
        self._cell_value.setObjectName("cell-value")
        self._cell_value.setReadOnly(True)
        self._cell_value.setPlaceholderText("Select a cell to inspect its value")
        self._cell_value.setAccessibleName("Selected cell value")
        cell_bar = QFrame()
        cell_bar.setObjectName("cell-bar")
        cell_layout = QHBoxLayout(cell_bar)
        cell_layout.setContentsMargins(4, 4, 4, 4)
        cell_layout.setSpacing(8)
        cell_layout.addWidget(self._cell_address)
        cell_layout.addWidget(self._cell_value, 1)

        self.sheet_tabs = QTabBar()
        self.sheet_tabs.setObjectName("sheet-tabs")
        self.sheet_tabs.setExpanding(False)
        self.sheet_tabs.setDrawBase(False)
        self.sheet_tabs.setUsesScrollButtons(True)
        # Short Japanese sheet names elided to one character are unreadable, so the strip scrolls instead.
        self.sheet_tabs.setElideMode(Qt.ElideNone)
        self.sheet_tabs.setAccessibleName("Workbook sheets")
        self.sheet_tabs.currentChanged.connect(self._on_sheet_tab_changed)
        self._sheets_proxy.modelReset.connect(self._sync_sheet_tabs)
        self._sheets_proxy.rowsInserted.connect(self._sync_sheet_tabs)
        self._sheets_proxy.rowsRemoved.connect(self._sync_sheet_tabs)
        self.sheet_filter.textChanged.connect(self._sync_sheet_tabs)
        self.sheet_filter.setMaximumWidth(180)
        self.sheet_filter.setPlaceholderText("Find a sheet…")
        sheet_label = QLabel("SHEETS")
        sheet_label.setObjectName("section-header")
        sheet_strip = QFrame()
        sheet_strip.setObjectName("sheet-strip")
        sheet_layout = QHBoxLayout(sheet_strip)
        sheet_layout.setContentsMargins(12, 4, 12, 4)
        sheet_layout.setSpacing(8)
        sheet_layout.addWidget(sheet_label)
        sheet_layout.addWidget(self.sheet_tabs, 1)
        sheet_layout.addWidget(self.sheet_filter)

        self._sheet_stack = QStackedWidget()
        self._sheet_stack.setObjectName("sheet-surface")
        self._sheet_stack.addWidget(self._build_empty_state())
        self._sheet_stack.addWidget(self.table)
        # The strip and the cell bar describe a sheet, so they show only while one is open.
        self._sheet_stack.currentChanged.connect(
            lambda index: (sheet_strip.setVisible(index == 1), cell_bar.setVisible(index == 1))
        )
        sheet_strip.hide()
        cell_bar.hide()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 12)
        content_layout.setSpacing(8)
        content_layout.addWidget(cell_bar)
        content_layout.addWidget(self._sheet_stack, 1)
        workspace = QWidget()
        workspace.setObjectName("workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(sheet_strip)
        workspace_layout.addWidget(content, 1)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(companies_pane)
        splitter.addWidget(workspace)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 1210])
        splitter.setChildrenCollapsible(False)
        self._splitter = splitter
        self._nav_widgets = (companies_pane,)
        self.setCentralWidget(splitter)

        # ---- Menu ----
        open_file = QAction("Open &workbook…", self)
        open_file.setShortcut(QKeySequence.Open)
        open_file.triggered.connect(self._open_file_dialog)

        open_folder = QAction("Open f&older…", self)
        open_folder.setShortcut("Ctrl+Shift+O")
        open_folder.triggered.connect(self._open_folder_dialog)

        self._compare_action = QAction("&Compare cells…", self)
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

        menu_bar = QMenuBar()
        menu_bar.setObjectName("app-menu")
        menu_bar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(open_file)
        file_menu.addAction(open_folder)
        file_menu.addSeparator()
        file_menu.addAction(focus_company)
        file_menu.addAction(focus_sheet)
        file_menu.addSeparator()
        file_menu.addAction(quit_act)

        view_menu = menu_bar.addMenu("&View")
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
        fit_columns = QAction("Fit column &widths", self)
        fit_columns.triggered.connect(self._fit_columns)
        view_menu.addAction(fit_columns)
        self._zoom_in_action = QAction("Zoom &in", self)
        self._zoom_in_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.ZoomIn) + [QKeySequence("Ctrl+=")])
        self._zoom_in_action.triggered.connect(lambda: self._set_zoom(self._zoom_percent + 10))
        self._zoom_out_action = QAction("Zoom &out", self)
        self._zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        self._zoom_out_action.triggered.connect(lambda: self._set_zoom(self._zoom_percent - 10))
        self._zoom_reset_action = QAction("Reset zoom to &100%", self)
        self._zoom_reset_action.setShortcut("Ctrl+0")
        self._zoom_reset_action.triggered.connect(lambda: self._set_zoom(100))
        view_menu.addSeparator()
        view_menu.addActions([self._zoom_in_action, self._zoom_out_action, self._zoom_reset_action])

        compare_menu = menu_bar.addMenu("&Compare")
        compare_menu.addAction(self._compare_action)
        load_comparison = QAction("&Load Comparison Preset…", self)
        load_comparison.triggered.connect(self._load_comparison_preset)
        compare_menu.addAction(load_comparison)

        # ---- Bar: brand, menus, the open model, the latest status and the actions ----
        self._status = QLabel("Open a workbook or folder · Drag and drop supported")
        self._status.setObjectName("app-detail")
        self._status.setTextFormat(Qt.PlainText)
        self._status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        # Preload progress widget: "Loading 42%  [====    ]"
        self._cache_label = QLabel("")
        self._cache_label.setMinimumWidth(120)
        self._cache_label.setVisible(_PRELOAD_MAX_FILES > 0)
        self._preload_bar = QProgressBar()
        self._preload_bar.setTextVisible(False)
        self._preload_bar.setFixedWidth(140)
        self._preload_bar.setVisible(False)

        brand = QLabel("Theia")
        brand.setObjectName("app-brand")
        bar = QFrame()
        bar.setObjectName("app-bar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 3, 8, 3)
        bar_layout.setSpacing(10)
        bar_layout.addWidget(brand)
        bar_layout.addWidget(menu_bar)
        bar_layout.addWidget(self._document_title)
        bar_layout.addWidget(self._status, 1)
        bar_layout.addWidget(self._cache_label)
        bar_layout.addWidget(self._preload_bar)
        for action in (open_file, open_folder, self._compare_action):
            action.setToolTip(f"{action.text().replace('&', '')} ({action.shortcut().toString(QKeySequence.NativeText)})")
            button = QToolButton()
            button.setObjectName("bar-button")
            button.setDefaultAction(action)
            bar_layout.addWidget(button)
        theme_button = QToolButton()
        theme_button.setObjectName("theme-button")
        theme_button.setText("◐")
        theme_button.setToolTip("Switch between the light and dark theme")
        theme_button.setAccessibleName("Switch theme")
        theme_button.clicked.connect(lambda: self._set_dark_mode(not self._dark_mode))
        bar_layout.addWidget(theme_button)
        self.setMenuWidget(bar)

        zoom_controls = QWidget()
        zoom_controls.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        zoom_layout = QHBoxLayout(zoom_controls)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(4)
        self._zoom_label = QToolButton()
        self._zoom_label.setAccessibleName("Reset zoom to 100%")
        self._zoom_label.setToolTip("Reset zoom to 100%")
        self._zoom_label.setFocusPolicy(Qt.NoFocus)
        self._zoom_label.clicked.connect(lambda: self._set_zoom(100))
        zoom_layout.addWidget(self._zoom_label)
        for label, action in (("−", self._zoom_out_action), ("+", self._zoom_in_action)):
            button = QToolButton()
            button.setObjectName("zoom-out" if label == "−" else "zoom-in")
            button.clicked.connect(action.trigger)
            action.changed.connect(lambda action=action, button=button: button.setEnabled(action.isEnabled()))
            button.setText(label)
            button.setAccessibleName(action.text().replace("&", ""))
            button.setToolTip(action.text().replace("&", ""))
            button.setFocusPolicy(Qt.NoFocus)
            zoom_layout.addWidget(button)
            if label == "−":
                self._zoom_slider = QSlider(Qt.Horizontal)
                self._zoom_slider.setRange(50, 200)
                self._zoom_slider.setSingleStep(10)
                self._zoom_slider.setPageStep(10)
                self._zoom_slider.setFixedWidth(140)
                self._zoom_slider.setAccessibleName("Zoom")
                self._zoom_slider.setToolTip("Zoom the entire interface (50–200%) · Ctrl/⌘ + mouse wheel")
                self._zoom_slider.valueChanged.connect(self._set_zoom)
                zoom_layout.addWidget(self._zoom_slider)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addPermanentWidget(zoom_controls)

        # ---- Drag & drop ----
        self.setAcceptDrops(True)
        self._sync_theme_controls()
        self._set_sidebar_visible(self._sidebar_visible, persist=False)
        self._set_zoom(self._settings.value("view/zoom", 100))
        QApplication.instance().installEventFilter(self)

    # ---- Theme / view controls ----

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Wheel
            and isinstance(watched, QWidget)
            and (watched is self or self.isAncestorOf(watched))
            and event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier)
        ):
            self._zoom_wheel_delta += event.angleDelta().y() or event.pixelDelta().y() * 6
            steps = int(self._zoom_wheel_delta / 120)
            self._zoom_wheel_delta -= steps * 120
            if steps:
                self._set_zoom(self._zoom_percent + steps * 10)
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _set_zoom(self, percent):
        try:
            percent = max(50, min(200, int(percent)))
        except TypeError:
            percent = 100
        except ValueError:
            percent = 100
        self._zoom_percent = percent
        with QSignalBlocker(self._zoom_slider):
            self._zoom_slider.setValue(percent)
        self._zoom_label.setText(f"{percent}%")
        self._zoom_in_action.setEnabled(percent < 200)
        self._zoom_out_action.setEnabled(percent > 50)
        self._settings.setValue("view/zoom", percent)
        self._apply_theme()
        self._cell_address.setFixedWidth(round(72 * percent / 100))
        self.sheet_filter.setMaximumWidth(round(180 * percent / 100))
        self.company_tree.setIndentation(round(14 * percent / 100))
        self.table.setZoom(percent)
        for dialog in self._comparison_dialogs:
            dialog.table.verticalHeader().setDefaultSectionSize(round(24 * percent / 100))

    def _build_empty_state(self) -> QWidget:
        """The start panel: how to open models and where the default model folder is."""
        root = models_root()
        if root.is_dir():
            folder_note = f"Model folder: {root}"
        else:
            folder_note = f"Model folder {root} does not exist. Set THEIA_MODELS_PATH in .env, or open a workbook or folder."
        heading = QLabel("Open valuation models")
        heading.setObjectName("empty-heading")
        description = QLabel("Drop Excel files, a folder or a zip here, or choose one below.")
        description.setObjectName("empty-description")
        open_button = QPushButton("Open workbook…")
        open_button.setObjectName("primary-button")
        open_button.clicked.connect(self._open_file_dialog)
        folder_button = QPushButton("Open folder…")
        folder_button.clicked.connect(self._open_folder_dialog)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        buttons.addWidget(open_button)
        buttons.addWidget(folder_button)
        buttons.addStretch()
        folder = QLabel(folder_note)
        folder.setObjectName("empty-note")
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        keys = QLabel("Ctrl+O workbook · Ctrl+Shift+O folder · Ctrl+B sidebar · Ctrl+Shift+C compare selected cells")
        keys.setObjectName("empty-note")

        empty = QWidget()
        empty.setObjectName("empty-state")
        layout = QVBoxLayout(empty)
        layout.setSpacing(6)
        layout.addStretch()
        for label in (heading, description):
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
        layout.addSpacing(10)
        layout.addLayout(buttons)
        layout.addSpacing(14)
        for label in (folder, keys):
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch()
        return empty

    def _sync_sheet_tabs(self, *_):
        current = self.sheet_list.currentIndex()
        name = self._sheets_proxy.data(current, Qt.DisplayRole) if current.isValid() else None
        with QSignalBlocker(self.sheet_tabs):
            while self.sheet_tabs.count():
                self.sheet_tabs.removeTab(0)
            for row in range(self._sheets_proxy.rowCount()):
                label = str(self._sheets_proxy.data(self._sheets_proxy.index(row, 0)))
                index = self.sheet_tabs.addTab(label)
                self.sheet_tabs.setTabToolTip(index, label)
                if label == name:
                    self.sheet_tabs.setCurrentIndex(index)
        if self.sheet_tabs.count() and not self.sheet_list.currentIndex().isValid():
            self.sheet_list.setCurrentIndex(self._sheets_proxy.index(self.sheet_tabs.currentIndex(), 0))

    def _on_sheet_tab_changed(self, index):
        if index >= 0:
            self.sheet_list.setCurrentIndex(self._sheets_proxy.index(index, 0))
            self.table.setCurrentIndex(self.table.currentIndex())

    def _update_cell_value(self, current, previous=None):
        model = self.table.model()
        if model is None or not current.isValid():
            self._cell_address.clear()
            self._cell_value.clear()
            return
        self._cell_address.setText(f"{_col_letter(current.column())}{current.row() + 1}")
        self._cell_value.setText(str(model.data(current, Qt.DisplayRole) or ""))
        self._cell_value.setCursorPosition(0)

    def _go_to_cell(self):
        match = re.fullmatch(r"([A-Za-z]+)([1-9]\d*)", self._cell_address.text().strip())
        model = self.table.model()
        if not match or model is None:
            return
        column = 0
        for letter in match[1].upper():
            column = column * 26 + ord(letter) - ord("A") + 1
        row, column = int(match[2]) - 1, column - 1
        if row >= model.rowCount() or column >= model.columnCount():
            self._status.setText("That cell is outside this sheet")
            return
        index = model.index(row, column)
        self.table.setCurrentIndex(index)

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
            if len(sizes) == 2 and sizes[0] == 0:
                self._splitter.setSizes([230, max(700, sizes[1])])
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
            app.setPalette(build_palette(self._theme_key, self._dark_mode))
            app.setStyleSheet(build_stylesheet(self._theme_key, self._dark_mode, self._zoom_percent))

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
        # .zip files we find. Items become (collection, group, label, source).
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
                collection, group = _collection_group_from_folder_path(p, folder)
                items.append((collection, group, label, p))
            elif suf == ".zip":
                try:
                    for inner in list_zip_xlsx(p):
                        label = _jp_label(Path(inner).stem) or Path(inner).stem
                        if not Path(inner).name.startswith("~$"):
                            collection = _collection_from_path(p)
                            group = _group_from_zip_entry(inner) or p.stem
                            items.append((collection, group, label, (p, inner)))
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
        collection = _collection_from_path(zip_path)
        for n in inner_names:
            label = _jp_label(Path(n).stem) or Path(n).stem
            if not Path(n).name.startswith("~$"):
                group = _group_from_zip_entry(n)
                items.append((collection, group, label, (zip_path, n)))
            else:
                skipped += 1
        self._populate(items, root_label=str(zip_path), skipped=skipped)
        self.setWindowTitle(f"{zip_path.name} — Theia")

    # ---- Internals ----

    def _populate(self, items: list[tuple[str, str, str, Source]], root_label: str, skipped: int = 0):
        """items = [(collection, group, label, source), ...]. Builds the
        three-level tree model (collection -> group -> company) and resets state."""
        for worker in (self._preload_worker,):
            if worker is not None:
                worker.requestInterruption()
                worker.wait()
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
        self._sheet_stack.setCurrentIndex(0)
        self._document_title.setText("Valuation models")
        self._cell_address.clear()
        self._cell_value.clear()

        if not items:
            tail = f" ({skipped} temporary files skipped)" if skipped else ""
            self._status.setText(f"{root_label}{tail}   ·   no Excel files found")
            return

        by_collection: dict[str, dict[str, list[tuple[str, Source]]]] = {}
        for collection, group, label, source in items:
            by_collection.setdefault(collection, {}).setdefault(group, []).append((label, source))

        root = self._companies_model.invisibleRootItem()
        folder_font = QFont()
        folder_font.setWeight(QFont.DemiBold)
        for collection in sorted(by_collection):
            groups = by_collection[collection]
            collection_parent = root
            if not collection.startswith("("):
                collection_parent = QStandardItem(collection)
                collection_parent.setEditable(False)
                collection_parent.setSelectable(False)
                collection_parent.setFont(folder_font)
                root.appendRow(collection_parent)
            for group in sorted(groups):
                parent = collection_parent
                if not group.startswith("("):
                    parent = QStandardItem(group)
                    parent.setEditable(False)
                    parent.setSelectable(False)
                    parent.setFont(folder_font)
                    collection_parent.appendRow(parent)
                for label, source in sorted(groups[group], key=lambda item: item[0]):
                    item = QStandardItem(label)
                    item.setEditable(False)
                    item.setData(source, Qt.UserRole)
                    parent.appendRow(item)
        self.company_tree.expandAll()
        first = root.child(0)
        while first is not None and first.rowCount():
            first = first.child(0)
        if first is not None:
            self.company_tree.setCurrentIndex(self._companies_proxy.mapFromSource(first.index()))

        # Only warm a few first sheets; archive size must not determine RAM use.
        xlsx_paths = [src for _, _, _, src in items if isinstance(src, Path)]
        self._start_preload(xlsx_paths[:_PRELOAD_MAX_FILES])
        self.table.setCurrentIndex(self.table.currentIndex())

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
        self._cache_label.setText(f"✓  {n_loaded}/{n_total} cached  ·  {total_ms / 1000:.0f}s")

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
            # Folder (parent) node — selection model usually skips these
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
            while len(self._workbooks) > 1:
                _, old = self._workbooks.popitem(last=False)
                old.close()
        self._current_wb = wb
        self._current_label = label
        self._current_source = source
        visible = [s for s in wb.sheet_names if not _is_hidden_sheet(s)]
        self._sheets_model.setStringList(visible)
        self.sheet_filter.clear()
        if visible:
            self.sheet_list.setCurrentIndex(self._sheets_proxy.index(0, 0))
        else:
            self.table.setModel(None)
            n_hidden = len(wb.sheet_names) - len(visible)
            tail = f" (all {n_hidden} sheet{'s' if n_hidden != 1 else ''} filtered out)" if n_hidden else ""
            self._status.setText(f"{label}   ·   (no sheets){tail}")

    def _on_sheet_selected(self, current, previous):
        if not current.isValid() or self._current_wb is None:
            return
        name = self._sheets_proxy.data(current, Qt.DisplayRole)
        with QSignalBlocker(self.sheet_tabs):
            self.sheet_tabs.setCurrentIndex(current.row())
        wb_path = self._current_wb.path

        cache_key = (wb_path, name)

        # Sheet model cache hit: re-use the already-built model and metadata.
        cached_entry = _lru_get(self._sheet_model_cache, cache_key)
        if cached_entry is not None:
            model, merged_cells, group_rows_0, group_cols_0 = cached_entry
            self._apply_model_to_table(model, merged_cells, group_rows_0, group_cols_0, cache_key)
            group_note = f"   ·   {len(group_rows_0)} grouped rows" if group_rows_0 else ""
            self._status.setText(f"{model.rowCount():,} rows × {model.columnCount()} cols{group_note}")
            return

        # Try Arrow path: <parent>/<stem>.<safe_sheet_name>.arrow (mmap, pre-formatted)
        arrow_model = self._try_load_arrow(wb_path, name)
        if arrow_model is not None:
            merged_cells = arrow_model.merged_cells
            group_rows_0 = {r - 1 for r in arrow_model.row_outlines}
            group_cols_0 = {c - 1 for c in arrow_model.col_outlines}
            _lru_put(
                self._sheet_model_cache,
                cache_key,
                (arrow_model, merged_cells, group_rows_0, group_cols_0),
                _SHEET_MODEL_CACHE_MAXSIZE,
            )
            self._apply_model_to_table(arrow_model, merged_cells, group_rows_0, group_cols_0, cache_key)
            group_note = f"   ·   {len(group_rows_0)} grouped rows" if group_rows_0 else ""
            self._status.setText(f"{arrow_model.rowCount():,} rows × {arrow_model.columnCount()} cols{group_note}")
            return

        # Fallback: calamine / preload-cache path.
        file_cache = _lru_get(self._preload_cache, wb_path)
        cached_rows = file_cache.get(name) if file_cache is not None else None
        try:
            sheet = self._current_wb.load_sheet(name, cached_rows=cached_rows)
            source_formats = self._current_wb.cell_formats(name)
        except Exception as e:
            self._status.setText(f"Failed to load sheet '{name}': {e}")
            return
        rows = sheet.rows

        sc = self._sidecar_for(name)
        row_fmt = {int(k): v for k, v in sc.get("row_formats", {}).items()}
        cell_fmt = {cell: fmt for cell, fmt in source_formats.items() if cell[0] not in row_fmt}
        cell_fmt.update({tuple(int(p) for p in k.split(",")): v for k, v in sc.get("cell_formats", {}).items()})
        hidden_rows = set(sc.get("hidden_rows", []))
        hidden_cols = set(sc.get("hidden_cols", []))
        merged_cells = sc.get("merged_cells", [])
        if not merged_cells:
            merged_cells = [
                f"{_col_letter(c1)}{r1 + 1}:{_col_letter(c2)}{r2 + 1}"
                for (r1, c1), (r2, c2) in self._current_wb.sheets[name].merged_cells
            ]
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
        self._status.setText(f"{model.rowCount():,} rows × {model.columnCount()} cols{group_note}")

    _OVERFLOW_TEXT_MIN_CHARS = 16

    def _apply_model_to_table(self, model, merged_cells, group_rows_0, group_cols_0, cache_key):
        """③ Swap in a new model while suppressing intermediate viewport repaints."""
        self._sheet_stack.setCurrentIndex(1)
        self._document_title.setText(self._current_label or "Valuation model")
        self._document_title.setToolTip(str(self._current_wb.path))
        for v in self.table._views():
            v.setUpdatesEnabled(False)
        try:
            self.table.setModel(model)
            selection = self.table.br.selectionModel()
            selection.currentChanged.connect(self._update_cell_value)
            if model.rowCount() and model.columnCount():
                selection.setCurrentIndex(model.index(0, 0), QItemSelectionModel.ClearAndSelect)
            self.table.setMergedCells(merged_cells)
            self.table.setGroups(group_rows_0, group_cols_0)
            self._autosize_columns(model, cache_key)
            fr, fc = self._default_freeze
            # An automatic freeze must not split a merged title across views.
            for area in merged_cells:
                parsed = _parse_excel_range(area)
                if parsed is not None:
                    row, col, rows, cols = parsed
                    if row < fr < row + rows:
                        fr = row
                    if col < fc < col + cols:
                        fc = col
            self.table.setFreeze(min(fr, model.rowCount()), min(fc, model.columnCount()))
        finally:
            for v in self.table._views():
                v.setUpdatesEnabled(True)

    def _autosize_columns(self, model, cache_key: tuple):
        """Estimate column widths and cache per sheet.

        Fast path: read pre-baked widths from Arrow metadata (zero Python iteration).
        Slow path: measure displayed text in the current font (first 60 rows).
        Cached widths are at 100%; zoom is applied by the table."""
        cached = self._col_width_cache.get(cache_key)
        if cached is not None:
            self.table.setColumnWidths(cached)
            return
        # Fast path: Arrow model carries pre-baked widths from the sidecar writer.
        if hasattr(model, "col_widths") and model.col_widths:
            _lru_put(self._col_width_cache, cache_key, model.col_widths, 8)
            self.table.setColumnWidths(model.col_widths)
            return
        # Slow path: measure from raw_value (SheetModel fallback)
        n_rows = model.rowCount()
        n_cols = model.columnCount()
        sample_n = min(60, n_rows)
        metrics = QFontMetricsF(self.table.br.font())
        scale = self._zoom_percent / 100
        merged = self.table._merged_ranges
        widths = []
        for c in range(n_cols):
            width = _MIN_COL_W
            for r in range(sample_n):
                v = model.raw_value(r, c)
                if v is not None:
                    if self._is_repeated_merged_text(model, r, c, v):
                        continue
                    if self._is_overflow_width_candidate(model, r, c, v):
                        continue
                    if any(
                        top <= r < top + height and left <= c < left + span and span > 1 for top, left, height, span in merged
                    ):
                        continue
                    text = str(model.data(model.index(r, c), Qt.DisplayRole) or "")
                    # The cell delegate uses three-pixel margins on each side.
                    width = max(width, ceil(metrics.horizontalAdvance(text) / scale) + 12)
            widths.append(min(width, _MAX_COL_W))
        _lru_put(self._col_width_cache, cache_key, widths, 8)
        self.table.setColumnWidths(widths)

    def _fit_columns(self):
        model = self.table.model()
        if model is None or self._current_wb is None:
            return
        name = self._sheets_proxy.data(self.sheet_list.currentIndex(), Qt.DisplayRole)
        key = self._current_wb.path, name
        self._col_width_cache.pop(key, None)
        self._autosize_columns(model, key)

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
        global ArrowSheetModel
        safe = re.sub(r"[^\w\-]", "_", sheet_name)
        arrow_path = wb_path.parent / f"{wb_path.stem}.{safe}.arrow"
        if not arrow_path.exists():
            return None
        try:
            # Plain workbooks do not need the Arrow runtime.
            import pyarrow as pa  # noqa: PLC0415

            if ArrowSheetModel is None:
                from theia.arrow_model import ArrowSheetModel  # noqa: PLC0415
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
            _lru_put(self._sidecar_cache, wb_path, data, 2)
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
            for c in range(col):
                value = model.data(model.index(row, c), Qt.DisplayRole)
                if value and not str(value).replace(",", "").replace(".", "").replace("-", "").isdigit():
                    title = str(value)
                    break
            metrics.append(Metric(title, row, col))
        self._show_comparison(sheet, metrics)

    def _load_comparison_preset(self):
        if self._current_source is None:
            self._status.setText("Open Excel files before loading a comparison preset")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load comparison preset", "", "JSON (*.json)")
        if not path:
            return
        try:
            sheet, metrics, match_labels = load_preset(Path(path))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            self._status.setText(f"Cannot load comparison preset: {exc}")
            return
        self._show_comparison(sheet, metrics, match_labels)

    def _show_comparison(self, sheet, metrics, match_labels=False):
        sources = []

        def collect(parent):
            for r in range(self._companies_proxy.rowCount(parent)):
                index = self._companies_proxy.index(r, 0, parent)
                source = self._companies_proxy.data(index, Qt.UserRole)
                if source is not None:
                    sources.append((self._companies_proxy.data(index, Qt.DisplayRole), source))
                collect(index)

        collect(self._companies_proxy.index(-1, -1))
        dialog = ComparisonDialog(sources, self._current_source, sheet, metrics, self, match_labels=match_labels)
        dialog.table.verticalHeader().setDefaultSectionSize(round(24 * self._zoom_percent / 100))
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
        QApplication.instance().removeEventFilter(self)
        for dialog in self._comparison_dialogs:
            if dialog.worker is not None:
                dialog.worker.cancel()
                dialog.worker.wait()
        for worker in (self._preload_worker,):
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
    app.setStyleSheet(build_stylesheet("theia", False))

    font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    # Japanese company and sheet names need a Japanese UI face behind the Latin one.
    font.setFamilies(["Segoe UI", "Yu Gothic UI", "Meiryo UI", font.family()])
    default_size = app.font().pointSize()
    if default_size > 0:
        font.setPointSize(max(9, default_size - 1))
    app.setFont(font)

    w = MainWindow()
    w.show()
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else models_root()
    if len(sys.argv) > 1 or path.exists():
        w.open_path(path)
    sys.exit(app.exec())
