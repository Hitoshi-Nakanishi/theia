"""Extract the same cells across local workbooks without retaining the sheets."""

import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QTableView, QVBoxLayout,
)

from theia.model import _col_letter, _format_cell
from theia.workbook import Source, Workbook


@dataclass(frozen=True)
class Metric:
    title: str
    row: int
    col: int

    @property
    def address(self):
        return f"{_col_letter(self.col)}{self.row + 1}"


@dataclass
class ComparisonRow:
    label: str
    source: Source
    values: list
    status: str


def source_text(source: Source) -> str:
    if isinstance(source, tuple):
        return f"{source[0]} / {source[1]}"
    return str(source)


def cell_value(rows: list[list], row: int, col: int):
    if row < len(rows) and col < len(rows[row]):
        return rows[row][col]
    return None


def metric_guards(rows: list[list], metric: Metric) -> list[tuple[int, int, str]]:
    """Check the nearest text to the left and above the reference cell."""
    guards = []
    for r, c in ((metric.row, c) for c in range(metric.col - 1, -1, -1)):
        value = cell_value(rows, r, c)
        if isinstance(value, str) and value.strip():
            guards.append((r, c, value.strip()))
            break
    for r in range(metric.row - 1, -1, -1):
        value = cell_value(rows, r, metric.col)
        if isinstance(value, str) and value.strip():
            guards.append((r, metric.col, value.strip()))
            break
    return guards


class ComparisonWorker(QThread):
    row_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, sources, reference, sheet_name, metrics, check_labels, parent=None):
        super().__init__(parent)
        self.sources = sources
        self.reference = reference
        self.sheet_name = sheet_name
        self.metrics = metrics
        self.check_labels = check_labels
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True
        self.requestInterruption()

    def is_cancelled(self):
        return self._cancel_requested or self.isInterruptionRequested()

    def run(self):
        if self.is_cancelled():
            return
        guards = [[] for _ in self.metrics]
        if self.check_labels:
            try:
                with Workbook(self.reference) as wb:
                    rows = wb.load_sheet(self.sheet_name).rows
                    guards = [metric_guards(rows, m) for m in self.metrics]
                    del rows
            except Exception as exc:
                self.failed.emit(f"Cannot read reference sheet: {exc}")
                return
        for label, source in self.sources:
            if self.is_cancelled():
                return
            values = [None] * len(self.metrics)
            issues = []
            try:
                with Workbook(source) as wb:
                    if self.sheet_name not in wb.sheets:
                        issues.append("Missing sheet")
                    else:
                        rows = wb.load_sheet(self.sheet_name).rows
                        for i, metric in enumerate(self.metrics):
                            if self.is_cancelled():
                                return
                            if any(
                                str(cell_value(rows, r, c)).strip() != expected
                                for r, c, expected in guards[i]
                            ):
                                issues.append(f"{metric.address}: label/header mismatch")
                                continue
                            value = cell_value(rows, metric.row, metric.col)
                            if value is None or value == "":
                                issues.append(f"{metric.address}: blank or no cached value")
                            elif isinstance(value, str) and value.startswith("#"):
                                issues.append(f"{metric.address}: {value}")
                            else:
                                values[i] = value
                        del rows
            except Exception as exc:
                issues.append(f"Read error: {exc}")
            if not issues:
                issues.append("OK" if all(guards) else "OK (address only for unchecked cells)")
            self.row_ready.emit(ComparisonRow(label, source, values, "; ".join(issues)))


class ComparisonModel(QAbstractTableModel):
    def __init__(self, metrics, parent=None, sheet_name=""):
        super().__init__(parent)
        self.metrics = metrics
        self.sheet_name = sheet_name
        self.rows: list[ComparisonRow] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.metrics) + 3

    def raw_value(self, row, col):
        item = self.rows[row]
        if col == 0:
            return item.label
        if col <= len(self.metrics):
            return item.values[col - 1]
        if col == len(self.metrics) + 1:
            return item.status
        return source_text(item.source)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self.raw_value(index.row(), index.column())
        if role == Qt.DisplayRole:
            return _format_cell(value)
        if role == Qt.ToolTipRole:
            return str(value) if value is not None else "No value; see Status"
        if role == Qt.TextAlignmentRole and isinstance(value, (int, float)):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Vertical:
            return str(section + 1)
        prefix = f"{self.sheet_name}!" if self.sheet_name else ""
        headers = ["Company"] + [f"{m.title} [{prefix}{m.address}]" for m in self.metrics] + ["Status", "Source"]
        return headers[section]

    def append(self, row):
        pos = len(self.rows)
        self.beginInsertRows(QModelIndex(), pos, pos)
        self.rows.append(row)
        self.endInsertRows()


def sort_key(value):
    if value is None or value == "":
        return (3, "")
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, (date, datetime, time)):
        return (1, value.isoformat())
    return (2, str(value).casefold())


class ComparisonProxy(QSortFilterProxyModel):
    def lessThan(self, left, right):
        model = self.sourceModel()
        return sort_key(model.raw_value(left.row(), left.column())) < sort_key(model.raw_value(right.row(), right.column()))


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(path: Path, proxy: ComparisonProxy):
    model = proxy.sourceModel()
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([csv_value(model.headerData(c, Qt.Horizontal)) for c in range(model.columnCount())])
        for r in range(proxy.rowCount()):
            source_row = proxy.mapToSource(proxy.index(r, 0)).row()
            writer.writerow([csv_value(model.raw_value(source_row, c)) for c in range(model.columnCount())])


class ComparisonDialog(QDialog):
    open_source = Signal(object, str, int, int)

    def __init__(self, sources, reference, sheet_name, metrics, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"Compare — {sheet_name}")
        self.resize(1100, 680)
        self.sources = sources
        self.reference = reference
        self.sheet_name = sheet_name
        self.metrics = metrics
        self.worker = None
        self._closing = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{len(sources)} files · {sheet_name} · {len(metrics)} selected cells"))
        note = QLabel("Compare the selected cells at the same addresses. Double-click a result to open its sheet.\n"
                      "Values come from saved workbooks; formulas are not recalculated here.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.check_labels = QCheckBox("Check nearby item labels and column headers against the current workbook")
        self.check_labels.setChecked(True)
        layout.addWidget(self.check_labels)

        controls = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter comparison results…")
        self.filter.setClearButtonEnabled(True)
        controls.addWidget(self.filter, 1)
        self.run_button = QPushButton("Extract / refresh")
        self.run_button.clicked.connect(self.start)
        controls.addWidget(self.run_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        controls.addWidget(self.cancel_button)
        self.export_button = QPushButton("Export visible rows to CSV…")
        self.export_button.clicked.connect(self.export)
        controls.addWidget(self.export_button)
        layout.addLayout(controls)

        self.model = ComparisonModel(metrics, self, sheet_name=sheet_name)
        self.proxy = ComparisonProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.filter.textChanged.connect(self.proxy.setFilterFixedString)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setDefaultSectionSize(190)
        self.table.doubleClicked.connect(self.navigate)
        layout.addWidget(self.table, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(sources))
        layout.addWidget(self.progress)
        self.status = QLabel("Ready")
        layout.addWidget(self.status)
        self.start()

    def start(self):
        if self.worker is not None:
            return
        self.model.beginResetModel()
        self.model.rows.clear()
        self.model.endResetModel()
        self.progress.setValue(0)
        self.status.setText("Reading saved values…")
        self.run_button.setEnabled(False)
        self.check_labels.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        worker = ComparisonWorker(self.sources, self.reference, self.sheet_name,
                                  self.metrics, self.check_labels.isChecked(), self)
        worker.row_ready.connect(self.add_row)
        worker.failed.connect(self.status.setText)
        worker.finished.connect(self.finished_reading)
        self.worker = worker
        worker.start()

    def add_row(self, row):
        self.model.append(row)
        self.progress.setValue(len(self.model.rows))
        self.status.setText(f"Read {len(self.model.rows)} / {len(self.sources)} files")

    def finished_reading(self):
        cancelled = self.worker.is_cancelled()
        self.worker.deleteLater()
        self.worker = None
        self.run_button.setEnabled(True)
        self.check_labels.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(bool(self.model.rows))
        if self.model.rows:
            count = sum(not row.status.startswith("OK") for row in self.model.rows)
            state = "Cancelled" if cancelled else "Complete"
            self.status.setText(f"{state}: {len(self.model.rows)} / {len(self.sources)} files · {count} with missing values or issues")
        elif cancelled:
            self.status.setText("Cancelled: no results")
        if self._closing:
            self.close()

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            self.status.setText("Cancelling after the current file…")

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export comparison", "comparison.csv", "CSV (*.csv)")
        if path:
            try:
                export_csv(Path(path), self.proxy)
                self.status.setText(f"Exported {self.proxy.rowCount()} visible rows")
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def navigate(self, index):
        source_index = self.proxy.mapToSource(index)
        row = self.model.rows[source_index.row()]
        metric_index = max(0, min(source_index.column() - 1, len(self.metrics) - 1))
        metric = self.metrics[metric_index]
        self.open_source.emit(row.source, self.sheet_name, metric.row, metric.col)

    def closeEvent(self, event):
        if self.worker is not None:
            self._closing = True
            self.cancel()
            event.ignore()
        else:
            event.accept()
