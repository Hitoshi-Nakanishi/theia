"""ArrowSheetModel — Qt table model backed by a memory-mapped PyArrow RecordBatch.

Arrow file format used by prepared archive sidecars:
  Columns:
    v_0 .. v_N  — pre-formatted display strings (large_utf8)
    n_0 .. n_N  — is_negative bool (optional; only for numeric columns)
  Schema metadata (JSON bytes):
    hidden_rows   — list of 1-based row indices
    hidden_cols   — list of 1-based col indices
    merged_cells  — list of "A1:B2" range strings
    row_outlines  — {"row": level} mapping (1-based)
    col_outlines  — {"col": level} mapping (1-based)
    numeric_cols  — list of 0-based column indices that have numeric values
    n_rows, n_cols — int dimensions
    col_widths    — list of pre-computed pixel widths per column (optional)
"""
from __future__ import annotations

import json

import pyarrow as pa

# Cython hot-path helpers — fall back to pure Python when the extension is not built.
try:
    from theia._arrow_fast import build_v_flat as _build_v_flat, get_display as _get_display
except ImportError:
    def _build_v_flat(cols: list, n_rows: int, n_cols: int) -> list:
        return [cols[c][r] for r in range(n_rows) for c in range(n_cols)]

    def _get_display(v_flat: list, r: int, c: int, n_cols: int) -> str:
        v = v_flat[r * n_cols + c]
        return v if v else ""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from theia.model import (
    _ALIGN_LEFT,
    _ALIGN_RIGHT,
    _HIDDEN_BG,
    _HIDDEN_FG,
    _NUM_COLOR_NEG,
    _col_letter,
    _hidden_font,
)


_FLAT_CELL_LIMIT = 0


class ArrowSheetModel(QAbstractTableModel):
    """QAbstractTableModel backed by a memory-mapped PyArrow RecordBatch.

    All display values are pre-formatted strings stored in the Arrow file.
    Sheets keep Arrow arrays and read cells lazily, avoiding a full Python
    object expansion at sheet-load time. The flat-list path remains available
    for local profiling by raising _FLAT_CELL_LIMIT.
    """

    def __init__(self, batch: pa.RecordBatch):
        super().__init__()
        meta = batch.schema.metadata or {}

        def _j(key: bytes, default):
            raw = meta.get(key)
            return json.loads(raw) if raw is not None else default

        self._n_rows: int = int(meta.get(b"n_rows", batch.num_rows))
        self._n_cols: int = int(meta.get(b"n_cols", 0))
        # 1-based sets (matching sidecar convention used by SheetModel)
        self.hidden_rows: set[int] = set(_j(b"hidden_rows", []))
        self.hidden_cols: set[int] = set(_j(b"hidden_cols", []))
        self.merged_cells: list[str] = _j(b"merged_cells", [])
        # 1-based dicts
        self.row_outlines: dict[int, int] = {int(k): v for k, v in _j(b"row_outlines", {}).items()}
        self.col_outlines: dict[int, int] = {int(k): v for k, v in _j(b"col_outlines", {}).items()}
        # 0-based set of columns that contain numeric values
        self._numeric_cols: set[int] = set(_j(b"numeric_cols", []))
        # Pre-baked column widths (px), None if absent.
        col_widths_raw = _j(b"col_widths", [])
        self.col_widths: list[int] | None = col_widths_raw if col_widths_raw else None

        # Default to Arrow-backed lazy access; building a Python list for every
        # cell dominates all-model load time while the UI only needs viewport
        # cells. Raise _FLAT_CELL_LIMIT locally to profile the old flat path.
        names = set(batch.schema.names)
        n_rows, n_cols = self._n_rows, self._n_cols
        self._batch = None
        self._v_cols: list | None = None
        self._v_flat: list | None = None
        if n_rows * n_cols <= _FLAT_CELL_LIMIT:
            cols = [batch.column(f"v_{c}").to_pylist() for c in range(n_cols)]
            self._v_flat = _build_v_flat(cols, n_rows, n_cols)
        else:
            self._batch = batch
            self._v_cols = [batch.column(f"v_{c}") for c in range(n_cols)]

        # Keep per-column neg markers. Eager sheets use Python lists; lazy
        # sheets keep Arrow arrays and read only cells being painted.
        self._neg: dict[int, list] = {}
        self._neg_arrays: dict[int, pa.Array] = {}
        for ci in self._numeric_cols:
            n_name = f"n_{ci}"
            if n_name in names:
                neg_col = batch.column(n_name)
                if self._v_flat is not None:
                    self._neg[ci] = neg_col.to_pylist()
                else:
                    self._neg_arrays[ci] = neg_col

        # Pre-compute hidden bool lists so data() does list[r] not set-lookup
        self._row_hidden: list[bool] = [((r + 1) in self.hidden_rows) for r in range(n_rows)]
        self._col_hidden: list[bool] = [((c + 1) in self.hidden_cols) for c in range(n_cols)]

    def _display_at(self, r: int, c: int) -> str:
        if self._v_flat is not None:
            return _get_display(self._v_flat, r, c, self._n_cols)
        assert self._v_cols is not None
        v = self._v_cols[c][r].as_py()
        return v if v else ""

    def _is_negative(self, r: int, c: int) -> bool:
        neg_list = self._neg.get(c)
        if neg_list is not None:
            return bool(neg_list[r])
        neg_array = self._neg_arrays.get(c)
        return bool(neg_array is not None and neg_array[r].as_py())

    # ---- QAbstractTableModel interface ----

    def rowCount(self, parent=QModelIndex()) -> int:
        return self._n_rows

    def columnCount(self, parent=QModelIndex()) -> int:
        return self._n_cols

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        # Qt only calls data() with valid indices for visible cells; skip checks.
        r, c = index.row(), index.column()

        if role == Qt.DisplayRole:
            return self._display_at(r, c)

        is_hidden = self._row_hidden[r] or self._col_hidden[c]
        if role == Qt.BackgroundRole and is_hidden:
            return _HIDDEN_BG
        if role == Qt.ForegroundRole:
            if is_hidden:
                return _HIDDEN_FG
            if self._is_negative(r, c):
                return _NUM_COLOR_NEG
        if role == Qt.FontRole and is_hidden:
            return _hidden_font()
        if role == Qt.TextAlignmentRole:
            return _ALIGN_RIGHT if c in self._numeric_cols else _ALIGN_LEFT
        return None

    def raw_value(self, r: int, c: int):
        """Return the pre-formatted display string — used by _autosize_columns."""
        if 0 <= r < self._n_rows and 0 <= c < self._n_cols:
            return self._display_at(r, c)
        return None

    def headerData(self, section: int, orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return _col_letter(section)
        return str(section + 1)
