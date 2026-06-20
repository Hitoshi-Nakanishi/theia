"""Table view widgets: SheetTableView (Excel Ctrl+Arrow nav) and FrozenPaneTable
(four sub-views sharing a model, Excel-style freeze panes)."""

import re

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QHeaderView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView, QWidget


_RANGE_RE = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$")

# ---------------------------------------------------------------------------
# Fast-delegate style constants — all lazy (need QApplication to exist).
# ---------------------------------------------------------------------------

_NORMAL_FONT: QFont | None = None
_HIDDEN_FG_COLOR = QColor("#6e7681")      # matches model._HIDDEN_FG brush color

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
    from theia.model import _HIDDEN_BG, _NUM_COLOR_NEG, _ALIGN_RIGHT, _ALIGN_LEFT, _hidden_font
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
    Python call with direct list indexing — zero extra model.data() queries.
    Falls back to QStyledItemDelegate for SheetModel or any other model type.
    """

    _SEL   = QStyle.StateFlag.State_Selected
    _ALT   = QStyleOptionViewItem.ViewItemFeature.Alternate
    _ready = False   # set to True after first paint warms up the constants

    def paint(self, painter, option, index):
        if not self._ready:
            _init_cell_style_consts()
            _FastCellDelegate._ready = True
        model = index.model()
        if not hasattr(model, "_v_flat"):
            super().paint(painter, option, index)
            return

        r = index.row()
        c = index.column()
        text = model._v_flat[r * model._n_cols + c] or ""
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
            return

        # ---- Font ----
        painter.setFont(_CELL_HIDDEN_FONT() if is_hidden else _normal_font())

        # ---- Text color ----
        if selected:
            painter.setPen(option.palette.highlightedText().color())
        elif is_hidden:
            painter.setPen(_HIDDEN_FG_COLOR)
        elif c in model._numeric_cols:
            neg_list = model._neg.get(c)
            if neg_list is not None and neg_list[r]:
                painter.setPen(_CELL_NUM_COLOR_NEG)
            else:
                painter.setPen(option.palette.text().color())
        else:
            painter.setPen(option.palette.text().color())

        # ---- Text ----
        align = _CELL_ALIGN_RIGHT if c in model._numeric_cols else _CELL_ALIGN_LEFT
        painter.drawText(rect.adjusted(3, 1, -3, -1), align, text)


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


class SheetTableView(QTableView):
    """QTableView with Excel-style Ctrl+Arrow / Ctrl+Shift+Arrow navigation."""

    _ARROW_DIRS = {
        Qt.Key_Right: (0, 1),
        Qt.Key_Left: (0, -1),
        Qt.Key_Down: (1, 0),
        Qt.Key_Up: (-1, 0),
    }

    def keyPressEvent(self, event):
        mods = event.modifiers()
        if mods & Qt.ControlModifier and event.key() in self._ARROW_DIRS:
            dr, dc = self._ARROW_DIRS[event.key()]
            self._excel_jump(dr, dc, extend=bool(mods & Qt.ShiftModifier))
            event.accept()
            return
        super().keyPressEvent(event)

    def _excel_jump(self, dr: int, dc: int, *, extend: bool):
        model = self.model()
        if model is None:
            return
        rows, cols = model.rowCount(), model.columnCount()
        cur = self.currentIndex()
        if not cur.isValid():
            return
        r, c = cur.row(), cur.column()

        def is_empty(rr: int, cc: int) -> bool:
            if hasattr(model, "raw_value"):
                v = model.raw_value(rr, cc)
            else:
                v = model.data(model.index(rr, cc), Qt.DisplayRole)
            return v is None or v == ""

        nr, nc = r + dr, c + dc
        if not (0 <= nr < rows and 0 <= nc < cols):
            return

        if is_empty(r, c) or is_empty(nr, nc):
            while 0 <= nr < rows and 0 <= nc < cols and is_empty(nr, nc):
                nr += dr
                nc += dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                nr = max(0, min(rows - 1, nr - dr))
                nc = max(0, min(cols - 1, nc - dc))
        else:
            while (
                0 <= nr + dr < rows
                and 0 <= nc + dc < cols
                and not is_empty(nr + dr, nc + dc)
            ):
                nr += dr
                nc += dc

        new = model.index(nr, nc)
        if extend:
            top, left = min(r, nr), min(c, nc)
            bottom, right = max(r, nr), max(c, nc)
            sel = QItemSelection(model.index(top, left), model.index(bottom, right))
            self.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect)
            self.selectionModel().setCurrentIndex(new, QItemSelectionModel.NoUpdate)
        else:
            self.setCurrentIndex(new)


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

        self.br = SheetTableView()
        self.bl = SheetTableView()
        self.tr = SheetTableView()
        self.tl = SheetTableView()

        delegate = _FastCellDelegate(self)
        for v in self._views():
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

    # ---- model & freeze API ----

    def setModel(self, model):
        self._model = model
        self._col_widths = []
        self._merged_cells = []
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
            fr == self._prev_freeze_rows and fc == self._prev_freeze_cols
            and not has_groups and not self._prev_had_groups
        )

        all_headers = (
            [v.verticalHeader()   for v in self._views()] +
            [v.horizontalHeader() for v in self._views()]
        )

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
                    self.bl.setRowHidden(r,     in_top)
                    self.br.setRowHidden(r,     in_top)

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
                    self.tr.setColumnHidden(c,     in_left)
                    self.br.setColumnHidden(c,     in_left)

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
                    self.bl.setRowHidden(r,     in_top)
                    self.br.setRowHidden(r,     in_top)
                for c in range(cols):
                    in_left = c < fc
                    self.tl.setColumnHidden(c, not in_left)
                    self.bl.setColumnHidden(c, not in_left)
                    self.tr.setColumnHidden(c,     in_left)
                    self.br.setColumnHidden(c,     in_left)

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
