import re
from datetime import date, datetime, time

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont


_NUM_COLOR_NEG = QColor("#cf222e")
_ALIGN_RIGHT = int(Qt.AlignRight | Qt.AlignVCenter)
_ALIGN_LEFT = int(Qt.AlignLeft | Qt.AlignVCenter)
_ALIGN_CENTER = int(Qt.AlignHCenter | Qt.AlignVCenter)


def _col_letter(n: int) -> str:
    """Excel-style column letters: 0->A, 25->Z, 26->AA."""
    s = ""
    n += 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


_NUMBER_RE = re.compile(
    r"(?P<sign>-?)(?P<open>\()?(?P<number>#,##0|0)(?:\.(?P<decimals>0+))?(?P<percent>%)?(?P<close>\))?"
)


def apply_excel_format(value, fmt: str | None) -> str | None:
    """Best-effort interpretation of an Excel number_format string. Returns
    a formatted string when the format applies, or None when the caller
    should fall back to default formatting (date/string/unhandled patterns)."""
    if fmt is None or value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (date, datetime, time)):
        return None  # let _format_cell render dates
    if not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and value != value:  # NaN
        return ""
    if re.search(r"\[[<>=]", fmt):
        return None

    sections = [""]
    for token in re.findall(r'"[^"]*"|\\.|[^"\\;]+|;', fmt):
        if token == ";":
            sections.append("")
        else:
            sections[-1] += token
    index = 2 if value == 0 and len(sections) >= 3 else 1 if value < 0 and len(sections) >= 2 else 0
    section = re.sub(r"\[(?:Black|Blue|Cyan|Green|Magenta|Red|White|Yellow|Color\d+)\]", "", sections[index], flags=re.I)
    if not section:
        return ""
    if section == "-":
        return section
    if re.fullmatch(r'"[^"]*"', section):
        return section[1:-1]
    match = _NUMBER_RE.fullmatch(section)
    if match is None or bool(match["open"]) != bool(match["close"]):
        return None
    number = abs(value) if index == 1 else value
    if match["percent"]:
        number *= 100
    decimals = len(match["decimals"] or "")
    shown = f"{number:,.{decimals}f}" if match["number"].startswith("#") or match["percent"] else f"{number:.{decimals}f}"
    return f"{match['sign']}{match['open'] or ''}{shown}{match['percent'] or ''}{match['close'] or ''}"


def _format_cell(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value != value:
            return ""
        if value.is_integer() and abs(value) < 1e15:
            return f"{int(value):,}"
        if abs(value) >= 1000:
            return f"{value:,.2f}"
        if abs(value) >= 1:
            return f"{value:,.4f}".rstrip("0").rstrip(".")
        return f"{value:.4g}"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, datetime):
        if value.hour or value.minute or value.second:
            return value.strftime("%Y-%m-%d %H:%M")
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return str(value)


_HIDDEN_BG = QBrush(QColor("#dde2e6"))   # noticeably darker than alternating row
_HIDDEN_FG = QBrush(QColor("#6e7681"))   # muted text for hidden cells
_HIDDEN_FONT: QFont | None = None         # built lazily because QFont needs QApp


def _hidden_font() -> QFont:
    global _HIDDEN_FONT
    if _HIDDEN_FONT is None:
        f = QFont()
        f.setItalic(True)
        _HIDDEN_FONT = f
    return _HIDDEN_FONT


class SheetModel(QAbstractTableModel):
    def __init__(
        self,
        rows: list[list],
        row_formats: dict[int, str] | None = None,
        cell_formats: dict[tuple[int, int], str] | None = None,
        hidden_rows: set[int] | None = None,
        hidden_cols: set[int] | None = None,
    ):
        super().__init__()
        self._rows = rows
        self._row_count = len(rows)
        self._col_count = max((len(r) for r in rows), default=0)
        # Excel format strings keyed 1-based to match the sidecar JSON. Our
        # internal indices are 0-based — convert at lookup time.
        self._row_formats = row_formats or {}
        self._cell_formats = cell_formats or {}
        # Rows / cols that were hidden in the source workbook. We keep them
        # rendered (per maintainer's request) but flag them with a gray cell
        # background. Sets are 1-based to match the sidecar JSON.
        self._hidden_rows = set(hidden_rows or ())
        self._hidden_cols = set(hidden_cols or ())

    def rowCount(self, parent=QModelIndex()) -> int:
        return self._row_count

    def columnCount(self, parent=QModelIndex()) -> int:
        return self._col_count

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if r >= self._row_count:
            return None
        row = self._rows[r]
        value = row[c] if c < len(row) else None

        if role == Qt.DisplayRole:
            # 1-based lookup in sidecar dicts
            fmt = self._cell_formats.get((r + 1, c + 1)) or self._row_formats.get(r + 1)
            if fmt is not None:
                formatted = apply_excel_format(value, fmt)
                if formatted is not None:
                    return formatted
            return _format_cell(value)
        if role == Qt.TextAlignmentRole:
            if isinstance(value, bool):
                return _ALIGN_CENTER
            if isinstance(value, (int, float)):
                return _ALIGN_RIGHT
            if isinstance(value, (date, datetime, time)):
                return _ALIGN_CENTER
            return _ALIGN_LEFT
        is_hidden = (r + 1) in self._hidden_rows or (c + 1) in self._hidden_cols
        if role == Qt.BackgroundRole and is_hidden:
            return _HIDDEN_BG
        if role == Qt.ForegroundRole:
            if is_hidden:
                return _HIDDEN_FG
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if value < 0:
                    return _NUM_COLOR_NEG
        if role == Qt.FontRole and is_hidden:
            return _hidden_font()
        return None

    def raw_value(self, r: int, c: int):
        """Fast accessor for navigation/emptiness checks — bypasses formatting."""
        if r < 0 or r >= self._row_count or c < 0 or c >= self._col_count:
            return None
        row = self._rows[r]
        return row[c] if c < len(row) else None

    def headerData(self, section: int, orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return _col_letter(section)
        return str(section + 1)
