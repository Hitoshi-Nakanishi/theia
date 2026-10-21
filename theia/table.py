"""Spreadsheet navigation and rendering across four views with shared freeze panes."""

import re

from PySide6.QtCore import QEvent, QItemSelection, QItemSelectionModel, QRect, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

_RANGE_RE = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$")

# ---------------------------------------------------------------------------
# Fast-delegate style constants — all lazy (need QApplication to exist).
# ---------------------------------------------------------------------------

_NORMAL_FONT: QFont | None = None
_HIDDEN_FG_COLOR = QColor("#6e7681")  # matches model._HIDDEN_FG brush color

# Populated on first delegate paint call to avoid importing model at module
# load time (model.py creates Qt objects at import, needs QApp).
_CELL_HIDDEN_BG = None
_CELL_NUM_COLOR_NEG = None
_CELL_ALIGN_RIGHT = None
_CELL_ALIGN_LEFT = None
_CELL_HIDDEN_FONT = None


def _init_cell_style_consts():
    global _CELL_HIDDEN_BG, _CELL_NUM_COLOR_NEG, _CELL_ALIGN_RIGHT, _CELL_ALIGN_LEFT, _CELL_HIDDEN_FONT
    if _CELL_HIDDEN_BG is not None:
        return
    # These shared Qt objects require an initialized QApplication.
    from theia.model import _ALIGN_LEFT, _ALIGN_RIGHT, _HIDDEN_BG, _NUM_COLOR_NEG, _hidden_font  # noqa: PLC0415

    _CELL_HIDDEN_BG = _HIDDEN_BG
    _CELL_NUM_COLOR_NEG = _NUM_COLOR_NEG
    _CELL_ALIGN_RIGHT = _ALIGN_RIGHT
    _CELL_ALIGN_LEFT = _ALIGN_LEFT
    _CELL_HIDDEN_FONT = _hidden_font


def _normal_font() -> QFont:
    global _NORMAL_FONT
    if _NORMAL_FONT is None:
        _NORMAL_FONT = QFont()
    return _NORMAL_FONT


class _FastCellDelegate(QStyledItemDelegate):
    """Paint spreadsheet cells directly from ArrowSheetModel's internal arrays.

    Bypasses Qt's 5-role-per-cell query protocol entirely for ArrowSheetModel:
    background, foreground, font, alignment, and text are all resolved in one
    Python call through the model's fast helpers.
    Falls back to QStyledItemDelegate for SheetModel or any other model type.
    """

    _SEL = QStyle.StateFlag.State_Selected
    _ALT = QStyleOptionViewItem.ViewItemFeature.Alternate
    _ready = False  # set to True after first paint warms up the constants
    _OVERFLOW_TEXT_MIN_CHARS = 24
    _OVERFLOW_MAX_COLS = 6

    def paint(self, painter, option, index):
        if not self._ready:
            _init_cell_style_consts()
            _FastCellDelegate._ready = True
        model = index.model()
        if not hasattr(model, "_display_at"):
            if self._paint_overflow_source(painter, option, index):
                return
            if self._paint_overflow_continuation(painter, option, index):
                return
            super().paint(painter, option, index)
            return

        r = index.row()
        c = index.column()
        if getattr(model, "_v_flat", None) is not None:
            text = model._v_flat[r * model._n_cols + c] or ""
        else:
            text = model._display_at(r, c)
        is_hidden = model._row_hidden[r] or model._col_hidden[c]
        selected = option.state & self._SEL
        rect = option.rect

        # ---- Background ----
        if selected:
            painter.fillRect(rect, option.palette.highlight())
        elif is_hidden:
            painter.fillRect(rect, _CELL_HIDDEN_BG)
        elif option.features & self._ALT:
            painter.fillRect(rect, option.palette.alternateBase())
        else:
            painter.fillRect(rect, option.palette.base())

        if not text:
            if self._draw_left_overflow_text(painter, option, model, r, c, selected):
                return
            return

        # ---- Font ----
        painter.setFont(_CELL_HIDDEN_FONT() if is_hidden else _normal_font())

        # ---- Text color ----
        if selected:
            painter.setPen(option.palette.highlightedText().color())
        elif is_hidden:
            painter.setPen(_HIDDEN_FG_COLOR)
        elif c in model._numeric_cols:
            if model._is_negative(r, c):
                painter.setPen(_CELL_NUM_COLOR_NEG)
            else:
                painter.setPen(option.palette.text().color())
        else:
            painter.setPen(option.palette.text().color())

        # ---- Text ----
        align = _CELL_ALIGN_RIGHT if c in model._numeric_cols else _CELL_ALIGN_LEFT
        painter.drawText(rect.adjusted(3, 1, -3, -1), align, text)

    def _paint_overflow_source(self, painter, option, index) -> bool:
        model = index.model()
        if not hasattr(model, "raw_value"):
            return False
        row, col = index.row(), index.column()
        value = model.raw_value(row, col)
        if not self._is_overflow_candidate(model, row, col, value):
            return False

        clean_option = QStyleOptionViewItem(option)
        self.initStyleOption(clean_option, index)
        clean_option.text = ""
        super().paint(painter, clean_option, index)

        text = model.data(index, Qt.DisplayRole) or ""
        self._draw_overflow_text(
            painter,
            option,
            text,
            self._overflow_rect(option, model, row, col),
            bool(option.state & self._SEL),
        )
        return True

    def _paint_overflow_continuation(self, painter, option, index) -> bool:
        model = index.model()
        if not hasattr(model, "raw_value"):
            return False
        row, col = index.row(), index.column()
        if not self._is_empty(model.raw_value(row, col)):
            return False
        source_col = self._left_overflow_source(model, row, col)
        if source_col is None:
            return False

        clean_option = QStyleOptionViewItem(option)
        self.initStyleOption(clean_option, index)
        clean_option.text = ""
        super().paint(painter, clean_option, index)

        text = model.data(model.index(row, source_col), Qt.DisplayRole) or ""
        self._draw_overflow_text(
            painter,
            option,
            text,
            self._overflow_rect(option, model, row, source_col),
            bool(option.state & self._SEL),
        )
        return True

    def _draw_left_overflow_text(self, painter, option, model, row: int, col: int, selected) -> bool:
        if not hasattr(model, "raw_value"):
            return False
        source_col = self._left_overflow_source(model, row, col)
        if source_col is None:
            return False
        if hasattr(model, "_display_at"):
            text = model._display_at(row, source_col)
        else:
            text = model.data(model.index(row, source_col), Qt.DisplayRole) or ""
        self._draw_overflow_text(
            painter,
            option,
            text,
            self._overflow_rect(option, model, row, source_col),
            bool(selected),
        )
        return True

    def _draw_overflow_text(self, painter, option, text: str, text_rect, selected: bool):
        if not text:
            return
        painter.save()
        painter.setClipRect(option.rect)
        painter.setFont(_normal_font())
        if selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
        painter.drawText(text_rect.adjusted(3, 1, -3, -1), _CELL_ALIGN_LEFT, text)
        painter.restore()

    def _left_overflow_source(self, model, row: int, col: int) -> int | None:
        start = max(0, col - self._OVERFLOW_MAX_COLS)
        for source_col in range(col - 1, start - 1, -1):
            value = model.raw_value(row, source_col)
            if self._is_empty(value):
                continue
            if self._is_overflow_candidate(model, row, source_col, value, target_col=col):
                return source_col
            return None
        return None

    def _is_overflow_candidate(self, model, row: int, source_col: int, value, *, target_col: int | None = None) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip()
        if len(text) < self._OVERFLOW_TEXT_MIN_CHARS or "\n" in text:
            return False
        end_col = target_col if target_col is not None else min(model.columnCount() - 1, source_col + 1)
        if end_col <= source_col:
            return False
        for col in range(source_col + 1, end_col + 1):
            if not self._is_empty(model.raw_value(row, col)):
                return False
        return True

    def _overflow_rect(self, option, model, row: int, source_col: int):
        view = option.widget
        if view is None:
            return option.rect
        left = view.columnViewportPosition(source_col)
        right = left + view.columnWidth(source_col)
        last_col = min(model.columnCount() - 1, source_col + self._OVERFLOW_MAX_COLS)
        for col in range(source_col + 1, last_col + 1):
            if not self._is_empty(model.raw_value(row, col)):
                break
            col_left = view.columnViewportPosition(col)
            right = max(right, col_left + view.columnWidth(col))
        return QRect(left, option.rect.top(), max(0, right - left), option.rect.height())

    @staticmethod
    def _is_empty(value) -> bool:
        return value is None or value == ""


def _col_letter_to_index(letter: str) -> int:
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _parse_excel_range(rng: str) -> tuple[int, int, int, int] | None:
    """Parse 'B1:D3' → (row=0, col=1, row_span=3, col_span=3) — 0-based."""
    m = _RANGE_RE.match(rng.strip().upper())
    if not m:
        return None
    col_a = _col_letter_to_index(m.group(1))
    row_a = int(m.group(2)) - 1
    col_b = _col_letter_to_index(m.group(3))
    row_b = int(m.group(4)) - 1
    return row_a, col_a, row_b - row_a + 1, col_b - col_a + 1


class FrozenPaneTable(QWidget):
    """Four QTableViews sharing a single model with Excel-style freeze panes.

    +----+--------+
    | TL |   TR   |   <- frozen rows
    +----+--------+
    |    |        |
    | BL |   BR   |   <- BR owns the scrollbars
    |    |        |
    +----+--------+
       ^ frozen cols
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._freeze_rows = 0
        self._freeze_cols = 0
        self._model = None
        # Source of truth for column widths — querying a view's columnWidth()
        # returns 0 for hidden columns, which breaks frozen-pane sizing.
        self._col_widths: list[int] = []
        # Excel range strings ("B1:D3") to apply via setSpan on whichever
        # sub-view contains the range. Set by setMergedCells.
        self._merged_cells: list[str] = []
        self._merged_ranges: list[tuple[int, int, int, int]] = []
        self._selection_anchor = None
        self._navigation_current = None
        # Excel outline group state: 0-based row/col indices that are hidden
        # when groups are collapsed. Managed by setGroups() / toggleGroups().
        self._group_rows: set = set()
        self._group_cols: set = set()
        self._groups_collapsed: bool = False

        # Delta-mode tracking: previous model dimensions and freeze boundaries.
        # -1 for freeze values signals "uninitialized" — forces a full pass on
        # the first call to _apply_freeze after a model is set.
        self._prev_model_rows = 0
        self._prev_model_cols = 0
        self._prev_freeze_rows = -1
        self._prev_freeze_cols = -1
        self._prev_had_groups = False

        self.br = QTableView()
        self.bl = QTableView()
        self.tr = QTableView()
        self.tl = QTableView()
        self.setFocusProxy(self.br)

        delegate = _FastCellDelegate(self)
        for v in self._views():
            v.installEventFilter(self)
            v.viewport().installEventFilter(self)
            v.setEditTriggers(QTableView.NoEditTriggers)
            v.setAlternatingRowColors(True)
            v.setShowGrid(True)
            v.setSelectionMode(QTableView.ExtendedSelection)
            v.setSelectionBehavior(QTableView.SelectItems)
            v.setCornerButtonEnabled(False)
            v.verticalHeader().setDefaultSectionSize(22)
            v.horizontalHeader().setHighlightSections(False)
            v.verticalHeader().setHighlightSections(False)
            v.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            v.setFrameShape(QFrame.NoFrame)
            v.setItemDelegate(delegate)
            # Fixed row heights avoid per-row resize work; word-wrap=False skips
            # text-flow calculation per cell.
            v.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
            v.setWordWrap(False)

        # Scroll policies: only BR has live scrollbars; frozen views are
        # driven by syncing BR's bars to theirs.
        self.tl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tr.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tr.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.bl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.bl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Sync BR's scroll position into the frozen edge views.
        self.br.horizontalScrollBar().valueChanged.connect(self.tr.horizontalScrollBar().setValue)
        self.br.verticalScrollBar().valueChanged.connect(self.bl.verticalScrollBar().setValue)

        # Bi-directional column / row resize sync between the views that share
        # the same logical columns / rows. The reentrancy flag prevents the
        # signal from looping (A resizes -> B resized -> emit signal -> A
        # resized -> emit signal -> ...).
        self._syncing_section = False

        def _link_headers(a, b):
            def a_to_b(idx, _old, new):
                if self._syncing_section:
                    return
                self._syncing_section = True
                try:
                    b.resizeSection(idx, new)
                finally:
                    self._syncing_section = False

            def b_to_a(idx, _old, new):
                if self._syncing_section:
                    return
                self._syncing_section = True
                try:
                    a.resizeSection(idx, new)
                finally:
                    self._syncing_section = False

            a.sectionResized.connect(a_to_b)
            b.sectionResized.connect(b_to_a)
            # Re-fit the frozen pane widget when a frozen column or row changes.
            a.sectionResized.connect(lambda *_: self._size_frozen_panes())
            b.sectionResized.connect(lambda *_: self._size_frozen_panes())

        # Columns shared between TR and BR (the scrollable right block).
        _link_headers(self.br.horizontalHeader(), self.tr.horizontalHeader())
        # Columns shared between TL and BL (the frozen left block).
        _link_headers(self.bl.horizontalHeader(), self.tl.horizontalHeader())
        # Rows shared between BL and BR (the scrollable bottom block).
        _link_headers(self.br.verticalHeader(), self.bl.verticalHeader())
        # Rows shared between TL and TR (the frozen top block).
        _link_headers(self.tr.verticalHeader(), self.tl.verticalHeader())

        layout = QGridLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tl, 0, 0)
        layout.addWidget(self.tr, 0, 1)
        layout.addWidget(self.bl, 1, 0)
        layout.addWidget(self.br, 1, 1)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

    def _views(self):
        return (self.tl, self.tr, self.bl, self.br)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress:
            self._selection_anchor = None
            self._navigation_current = None
        elif event.type() == QEvent.KeyPress and self._model is not None:
            directions = {
                Qt.Key_Right: (0, 1),
                Qt.Key_Left: (0, -1),
                Qt.Key_Down: (1, 0),
                Qt.Key_Up: (-1, 0),
                Qt.Key_Tab: (0, 1),
                Qt.Key_Backtab: (0, -1),
                Qt.Key_Return: (1, 0),
                Qt.Key_Enter: (1, 0),
            }
            key, modifiers = event.key(), event.modifiers()
            if key not in directions or modifiers & Qt.AltModifier:
                return super().eventFilter(watched, event)
            current = self.currentIndex()
            if not current.isValid():
                return super().eventFilter(watched, event)
            dr, dc = directions[key]
            arrow = key in (Qt.Key_Right, Qt.Key_Left, Qt.Key_Down, Qt.Key_Up)
            if not arrow and modifiers & (Qt.ControlModifier | Qt.MetaModifier):
                return super().eventFilter(watched, event)
            shift = bool(modifiers & Qt.ShiftModifier)
            if shift and key in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
                dr, dc = -dr, -dc
            cell = current.row(), current.column()
            target = self._next_cell(*cell, dr, dc)
            if arrow and modifiers & (Qt.ControlModifier | Qt.MetaModifier):
                target = self._excel_jump(cell, target, dr, dc)
            self.setCurrentIndex(self._model.index(*target), extend=arrow and shift)
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _next_cell(self, row, column, dr, dc):
        start = row, column
        for top, left, height, width in self._merged_ranges:
            if top <= row < top + height and left <= column < left + width:
                row = top + height - 1 if dr > 0 else row
                column = left + width - 1 if dc > 0 else column
                break
        row, column = row + dr, column + dc
        while 0 <= row < self._model.rowCount() and 0 <= column < self._model.columnCount():
            if self._groups_collapsed and (row in self._group_rows or column in self._group_cols):
                row, column = row + dr, column + dc
                continue
            for top, left, height, width in self._merged_ranges:
                if top <= row < top + height and left <= column < left + width:
                    return top, left
            return row, column
        return start

    def _excel_jump(self, current, target, dr, dc):
        def is_empty(cell):
            value = self._model.raw_value(*cell)
            return value is None or value == ""

        find_data = is_empty(current) or is_empty(target)
        while target != current:
            if find_data and not is_empty(target):
                break
            following = self._next_cell(*target, dr, dc)
            if following == target or (not find_data and is_empty(following)):
                break
            current, target = target, following
        return target

    def setCurrentIndex(self, index, *, extend=False):
        """Select and reveal a cell, keeping keyboard focus in its visible pane."""
        if index is None or not index.isValid() or index.model() is not self._model:
            return
        current = self.currentIndex()
        cell = current.row(), current.column()
        if not extend or self._selection_anchor is None or self._navigation_current != cell:
            self._selection_anchor = cell if extend else (index.row(), index.column())
        selection = self.br.selectionModel()
        if extend:
            row, column = self._selection_anchor
            area = QItemSelection(
                self._model.index(min(row, index.row()), min(column, index.column())),
                self._model.index(max(row, index.row()), max(column, index.column())),
            )
            selection.select(area, QItemSelectionModel.ClearAndSelect)
            selection.setCurrentIndex(index, QItemSelectionModel.NoUpdate)
        else:
            selection.setCurrentIndex(index, QItemSelectionModel.ClearAndSelect)
        self._navigation_current = index.row(), index.column()
        view = self._view_for_range(index.row(), index.column(), 1, 1, self._freeze_rows, self._freeze_cols)
        view.scrollTo(index)
        if index.row() >= self._freeze_rows:
            self.br.verticalScrollBar().setValue(view.verticalScrollBar().value())
        if index.column() >= self._freeze_cols:
            self.br.horizontalScrollBar().setValue(view.horizontalScrollBar().value())
        self.setFocusProxy(view)
        view.setFocus(Qt.OtherFocusReason)

    # ---- model & freeze API ----

    def setModel(self, model):
        self._model = model
        self._col_widths = []
        self._merged_cells = []
        self._merged_ranges = []
        self._selection_anchor = None
        self._navigation_current = None
        # Reset delta state so the next _apply_freeze does a full pass.
        self._prev_model_rows = 0
        self._prev_model_cols = 0
        self._prev_freeze_rows = -1
        self._prev_freeze_cols = -1
        for v in self._views():
            v.clearSpans()
            v.setModel(model)
        if model is not None:
            # Share a single selection model so a click in any view updates
            # selection (and current cell) globally.
            sel = self.br.selectionModel()
            for v in (self.tl, self.tr, self.bl):
                v.setSelectionModel(sel)
            # Freeze is applied by the caller via setFreeze() — avoid the
            # double _apply_freeze() that would otherwise run on every sheet switch.
        else:
            # No model: hide panes, show only BR.
            for v in (self.tl, self.tr, self.bl):
                v.setVisible(False)
            self.br.setVisible(True)
        # Qt retains replaced selection models, including header models.
        active = {
            owner.selectionModel() for view in self._views() for owner in (view, view.horizontalHeader(), view.verticalHeader())
        }
        for selection in self.findChildren(QItemSelectionModel):
            if selection not in active:
                selection.deleteLater()

    def model(self):
        return self._model

    def setGroups(self, row_indices: set, col_indices: set):
        """Store which rows/cols are in Excel outline groups. Resets to expanded."""
        self._group_rows = set(row_indices)
        self._group_cols = set(col_indices)
        self._groups_collapsed = False
        # No need to call _apply_freeze here; caller does it via setFreeze.

    def toggleGroups(self) -> bool:
        """Flip collapsed/expanded state. Returns True when now collapsed."""
        self._groups_collapsed = not self._groups_collapsed
        self._apply_freeze()
        return self._groups_collapsed

    def setFreeze(self, rows: int, cols: int):
        self._freeze_rows = max(0, rows)
        self._freeze_cols = max(0, cols)
        self._apply_freeze()
        self._apply_merges()

    def setMergedCells(self, ranges: list[str]):
        self._merged_cells = list(ranges)
        self._merged_ranges = [area for text in ranges if (area := _parse_excel_range(text)) is not None]
        self._apply_merges()

    def freezeRows(self) -> int:
        return self._freeze_rows

    def freezeCols(self) -> int:
        return self._freeze_cols

    def currentIndex(self):
        return self.br.selectionModel().currentIndex() if self._model else None

    # ---- column sizing (called by MainWindow's _autosize_columns) ----

    def setColumnWidth(self, col: int, width: int):
        while len(self._col_widths) <= col:
            self._col_widths.append(0)
        self._col_widths[col] = width
        for v in self._views():
            v.horizontalHeader().resizeSection(col, width)
        self._size_frozen_panes()

    def setColumnWidths(self, widths: list):
        """Apply all column widths in one pass; calls _size_frozen_panes once.
        Signals are blocked during bulk resize to prevent cascading sync callbacks."""
        self._col_widths = list(widths)
        all_h = [v.horizontalHeader() for v in self._views()]
        for h in all_h:
            h.blockSignals(True)
        try:
            for i, w in enumerate(widths):
                for h in all_h:
                    h.resizeSection(i, w)
        finally:
            for h in all_h:
                h.blockSignals(False)
        self._size_frozen_panes()

    def columnWidth(self, col: int) -> int:
        if col < len(self._col_widths) and self._col_widths[col] > 0:
            return self._col_widths[col]
        return self.br.horizontalHeader().sectionSize(col) or self.br.horizontalHeader().defaultSectionSize()

    def resizeColumnToContents(self, col: int):
        # BR is the canonical view; resize there, then read back the width.
        self.br.resizeColumnToContents(col)
        w = self.br.horizontalHeader().sectionSize(col)
        if w > 0:
            while len(self._col_widths) <= col:
                self._col_widths.append(0)
            self._col_widths[col] = w

    def horizontalHeader(self):
        # Exposed so external callers see the BR header (the "main" one).
        return self.br.horizontalHeader()

    # ---- internals ----

    def _apply_freeze(self):
        if self._model is None:
            for v in self._views():
                v.setVisible(v is self.br)
            return

        rows = self._model.rowCount()
        cols = self._model.columnCount()
        fr = min(self._freeze_rows, rows)
        fc = min(self._freeze_cols, cols)

        has_groups = bool(self._group_rows or self._group_cols)
        freeze_unchanged = (
            fr == self._prev_freeze_rows and fc == self._prev_freeze_cols and not has_groups and not self._prev_had_groups
        )

        all_headers = [v.verticalHeader() for v in self._views()] + [v.horizontalHeader() for v in self._views()]

        if freeze_unchanged:
            # DELTA MODE — only touch rows/cols that differ from the previous
            # model dimensions. Signals are still blocked to avoid O(n) cascades
            # from the header-sync connections established in __init__.
            prev_rows = self._prev_model_rows
            prev_cols = self._prev_model_cols

            for v in self._views():
                v.setUpdatesEnabled(False)
            for h in all_headers:
                h.blockSignals(True)

            try:
                # Rows added since last call — apply the freeze rule to them.
                for r in range(prev_rows, rows):
                    in_top = r < fr
                    self.tl.setRowHidden(r, not in_top)
                    self.tr.setRowHidden(r, not in_top)
                    self.bl.setRowHidden(r, in_top)
                    self.br.setRowHidden(r, in_top)

                # Rows removed since last call — hide in all views so Qt does
                # not try to paint stale sections.
                for r in range(rows, prev_rows):
                    for v in self._views():
                        v.setRowHidden(r, True)

                # Cols added since last call.
                for c in range(prev_cols, cols):
                    in_left = c < fc
                    self.tl.setColumnHidden(c, not in_left)
                    self.bl.setColumnHidden(c, not in_left)
                    self.tr.setColumnHidden(c, in_left)
                    self.br.setColumnHidden(c, in_left)

                # Cols removed since last call.
                for c in range(cols, prev_cols):
                    for v in self._views():
                        v.setColumnHidden(c, True)

                self._apply_groups()

                # View and header visibility follow the freeze boundaries,
                # which did not change — but update anyway in case the model
                # went from 0 rows/cols to non-zero (first population).
                self.tl.setVisible(fr > 0 and fc > 0)
                self.tr.setVisible(fr > 0)
                self.bl.setVisible(fc > 0)

                self.tl.horizontalHeader().setVisible(True)
                self.tl.verticalHeader().setVisible(True)
                self.tr.horizontalHeader().setVisible(True)
                self.tr.verticalHeader().setVisible(fc == 0)
                self.bl.verticalHeader().setVisible(True)
                self.bl.horizontalHeader().setVisible(fr == 0)
                self.br.horizontalHeader().setVisible(fr == 0)
                self.br.verticalHeader().setVisible(fc == 0)
            finally:
                for h in all_headers:
                    h.blockSignals(False)
                for v in self._views():
                    v.setUpdatesEnabled(True)

        else:
            # FULL MODE — freeze boundary changed (or first call).  Run the
            # complete combined pass exactly as before.
            for v in self._views():
                v.setUpdatesEnabled(False)
            for h in all_headers:
                h.blockSignals(True)

            try:
                # Single combined pass: reset + freeze in one loop.
                for r in range(rows):
                    in_top = r < fr
                    self.tl.setRowHidden(r, not in_top)
                    self.tr.setRowHidden(r, not in_top)
                    self.bl.setRowHidden(r, in_top)
                    self.br.setRowHidden(r, in_top)
                for c in range(cols):
                    in_left = c < fc
                    self.tl.setColumnHidden(c, not in_left)
                    self.bl.setColumnHidden(c, not in_left)
                    self.tr.setColumnHidden(c, in_left)
                    self.br.setColumnHidden(c, in_left)

                self._apply_groups()

                # Show/hide views based on whether their content range is non-empty.
                self.tl.setVisible(fr > 0 and fc > 0)
                self.tr.setVisible(fr > 0)
                self.bl.setVisible(fc > 0)

                # Headers: only the outermost view in each direction shows the header.
                self.tl.horizontalHeader().setVisible(True)
                self.tl.verticalHeader().setVisible(True)
                self.tr.horizontalHeader().setVisible(True)
                self.tr.verticalHeader().setVisible(fc == 0)
                self.bl.verticalHeader().setVisible(True)
                self.bl.horizontalHeader().setVisible(fr == 0)
                self.br.horizontalHeader().setVisible(fr == 0)
                self.br.verticalHeader().setVisible(fc == 0)
            finally:
                for h in all_headers:
                    h.blockSignals(False)
                for v in self._views():
                    v.setUpdatesEnabled(True)

        # Update delta-tracking state.
        self._prev_model_rows = rows
        self._prev_model_cols = cols
        self._prev_freeze_rows = fr
        self._prev_freeze_cols = fc
        self._prev_had_groups = has_groups

        self._size_frozen_panes()

    def _apply_groups(self):
        """Hide or show grouped rows/cols depending on _groups_collapsed."""
        if not (self._group_rows or self._group_cols):
            return
        if self._model is None:
            return
        fr = self._freeze_rows
        for r in self._group_rows:
            hide = self._groups_collapsed
            if r < fr:
                self.tl.setRowHidden(r, hide)
                self.tr.setRowHidden(r, hide)
            else:
                self.bl.setRowHidden(r, hide)
                self.br.setRowHidden(r, hide)
        fc = self._freeze_cols
        for c in self._group_cols:
            hide = self._groups_collapsed
            if c < fc:
                self.tl.setColumnHidden(c, hide)
                self.bl.setColumnHidden(c, hide)
            else:
                self.tr.setColumnHidden(c, hide)
                self.br.setColumnHidden(c, hide)

    def _apply_merges(self):
        if self._model is None:
            return
        for v in self._views():
            v.clearSpans()
        fr = self._freeze_rows
        fc = self._freeze_cols
        for rng in self._merged_cells:
            parsed = _parse_excel_range(rng)
            if parsed is None:
                continue
            row, col, rs, cs = parsed
            view = self._view_for_range(row, col, rs, cs, fr, fc)
            if view is not None:
                view.setSpan(row, col, rs, cs)

    def _view_for_range(self, row, col, rs, cs, fr, fc):
        """Pick the sub-view that fully contains the merge range; return None
        if the range straddles a freeze boundary (in which case we skip it
        rather than render it wrong)."""
        r_end = row + rs - 1
        c_end = col + cs - 1
        in_top = r_end < fr
        in_bottom = row >= fr
        in_left = c_end < fc
        in_right = col >= fc
        if in_top and in_left:
            return self.tl
        if in_top and in_right:
            return self.tr
        if in_bottom and in_left:
            return self.bl
        if in_bottom and in_right:
            return self.br
        # If no freeze at all (fr=fc=0), in_bottom and in_right are both True
        # for every range — handled above. Otherwise the range crosses a
        # boundary; skip it.
        return None

    def _size_frozen_panes(self):
        if self._model is None:
            return
        fr = min(self._freeze_rows, self._model.rowCount())
        fc = min(self._freeze_cols, self._model.columnCount())
        row_h = self.br.verticalHeader().defaultSectionSize()
        if fr > 0:
            header_h = self.tr.horizontalHeader().height() if self.tr.horizontalHeader().isVisible() else 0
            total_h = fr * row_h + header_h
            self.tl.setFixedHeight(total_h)
            self.tr.setFixedHeight(total_h)
        if fc > 0:
            frozen_w = sum(self.columnWidth(c) for c in range(fc))
            vh_w = self.bl.verticalHeader().width() if self.bl.verticalHeader().isVisible() else 0
            self.tl.setFixedWidth(frozen_w + vh_w)
            self.bl.setFixedWidth(frozen_w + vh_w)
