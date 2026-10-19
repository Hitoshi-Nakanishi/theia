"""Extract the same cells across local workbooks without retaining the sheets."""

import csv
import json
from dataclasses import asdict, dataclass, field
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
    locator: "CellLocator | None" = None

    @property
    def address(self):
        return f"{_col_letter(self.col)}{self.row + 1}"


@dataclass
class ComparisonRow:
    label: str
    source: Source
    values: list
    status: str
    coordinates: list = field(default_factory=list)
    locations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CellLocator:
    label_col: int
    label: str
    header_row: int
    header_label: tuple[int, str] | None
    header: str
    occurrence: int
    units: list[tuple[int, str]]


def text_at(rows, r, c):
    value = cell_value(rows, r, c)
    return value.strip() if isinstance(value, str) else ""


def cell_locator(rows, metric):
    labels = [(c, text_at(rows, metric.row, c)) for c in range(metric.col)]
    labels = [(c, value) for c, value in labels if value]
    if not labels:
        raise ValueError(f"{metric.address}: no item label to locate")
    above = [(r, text_at(rows, r, metric.col)) for r in range(metric.row - 1, -1, -1)]
    header_row, header = next(((r, value) for r, value in above if value), (-1, ""))
    if not header:
        raise ValueError(f"{metric.address}: no text column header to locate")
    header_label = next(((c, text_at(rows, header_row, c)) for c in range(metric.col)
                         if text_at(rows, header_row, c)), None)
    matching = [c for c in range(len(rows[header_row])) if text_at(rows, header_row, c) == header]
    return CellLocator(labels[0][0], labels[0][1], header_row, header_label,
                       header, matching.index(metric.col), labels[1:])


def locate_cell(rows, locator):
    matches = [r for r in range(len(rows)) if text_at(rows, r, locator.label_col) == locator.label]
    if len(matches) != 1:
        raise ValueError("missing or ambiguous item label")
    row = matches[0]
    header_row = locator.header_row
    if locator.header_label:
        label_col, label = locator.header_label
        matches = [r for r in range(len(rows)) if text_at(rows, r, label_col) == label]
        if len(matches) != 1:
            raise ValueError("missing or ambiguous header row")
        header_row = matches[0]
    if header_row >= len(rows):
        raise ValueError("missing header row")
    columns = [c for c in range(len(rows[header_row])) if text_at(rows, header_row, c) == locator.header]
    if len(columns) <= locator.occurrence:
        raise ValueError("missing column header or occurrence")
    if any(text_at(rows, row, c) != unit for c, unit in locator.units):
        raise ValueError("item unit/label mismatch")
    return row, columns[locator.occurrence], header_row


def load_preset(path: Path):
    if path.stat().st_size > 1_000_000:
        raise ValueError("Comparison preset is too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("sheet"), str) or not data["sheet"]:
        raise ValueError("Invalid comparison preset")
    entries = data.get("metrics", [])
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError("A preset needs 1 to 64 metrics")
    metrics = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("title"), str):
            raise ValueError("Invalid metric")
        if any(type(entry.get(key)) is not int or not 0 <= entry[key] < limit
               for key, limit in (("row", 1_048_576), ("col", 16_384))):
            raise ValueError("Invalid cell address")
        locator = entry.get("locator")
        if locator is not None:
            locator = CellLocator(**locator)
            if (type(locator.label_col) is not int or not 0 <= locator.label_col < 16_384
                    or type(locator.header_row) is not int or not 0 <= locator.header_row < 1_048_576
                    or type(locator.occurrence) is not int or not 0 <= locator.occurrence < 16_384
                    or not isinstance(locator.label, str) or not isinstance(locator.header, str)):
                raise ValueError("Invalid label locator")
            anchors = list(locator.units)
            if locator.header_label is not None:
                anchors.append(locator.header_label)
            if any(len(anchor) != 2 or type(anchor[0]) is not int or not 0 <= anchor[0] < 16_384
                   or not isinstance(anchor[1], str) for anchor in anchors):
                raise ValueError("Invalid label anchor")
        metrics.append(Metric(entry["title"], entry["row"], entry["col"], locator))
    return data["sheet"], metrics, bool(data.get("match_labels", False))


def source_text(source: Source) -> str:
    if isinstance(source, tuple):
        return f"{source[0]} / {source[1]}"
    return str(source)


def cell_value(rows: list[list], row: int, col: int):
    if 0 <= row < len(rows) and 0 <= col < len(rows[row]):
        return rows[row][col]
    return None


def metric_guards(rows: list[list], metric: Metric) -> list[tuple[int, int, str]]:
    """Check text labels/units to the left and the nearest header above."""
    guards = []
    for r, c in ((metric.row, c) for c in range(metric.col)):
        value = cell_value(rows, r, c)
        if isinstance(value, str) and value.strip():
            guards.append((r, c, value.strip()))
    for r in range(metric.row - 1, -1, -1):
        value = cell_value(rows, r, metric.col)
        if isinstance(value, str) and value.strip():
            guards.append((r, metric.col, value.strip()))
            break
    return guards


class ComparisonWorker(QThread):
    row_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, sources, reference, sheet_name, metrics, check_labels, parent=None, match_labels=False):
        super().__init__(parent)
        self.sources = sources
        self.reference = reference
        self.sheet_name = sheet_name
        self.metrics = metrics
        self.check_labels = check_labels
        self.match_labels = match_labels
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
        locators = []
        if self.check_labels or self.match_labels:
            try:
                with Workbook(self.reference) as wb:
                    rows = wb.load_sheet(self.sheet_name).rows
                    guards = [metric_guards(rows, m) for m in self.metrics]
                    if self.match_labels:
                        locators = [m.locator or cell_locator(rows, m) for m in self.metrics]
                    del rows
            except Exception as exc:
                self.failed.emit(f"Cannot read reference sheet: {exc}")
                return
        for label, source in self.sources:
            if self.is_cancelled():
                return
            values = [None] * len(self.metrics)
            coordinates = [None] * len(self.metrics)
            locations = [""] * len(self.metrics)
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
                            row, col = metric.row, metric.col
                            if self.match_labels:
                                try:
                                    row, col, header_row = locate_cell(rows, locators[i])
                                except ValueError as exc:
                                    issues.append(f"{metric.address}: {exc}")
                                    continue
                                context = [cell_value(rows, r, col) for r in (header_row - 1, header_row)]
                                context = " / ".join(str(v) for v in context if v is not None and v != "")
                                locations[i] = f"{self.sheet_name}!{_col_letter(col)}{row + 1} ({context})"
                            elif any(
                                str(cell_value(rows, r, c)).strip() != expected
                                for r, c, expected in guards[i]
                            ):
                                issues.append(f"{metric.address}: label/header mismatch")
                                continue
                            coordinates[i] = (row, col)
                            if not locations[i]:
                                locations[i] = f"{self.sheet_name}!{metric.address}"
                            value = cell_value(rows, row, col)
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
            self.row_ready.emit(ComparisonRow(label, source, values, "; ".join(issues), coordinates, locations))


class ComparisonModel(QAbstractTableModel):
    def __init__(self, metrics, parent=None, sheet_name=""):
        super().__init__(parent)
        self.metrics = metrics
        self.sheet_name = sheet_name
        self.rows: list[ComparisonRow] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.metrics) + 4

    def raw_value(self, row, col):
        item = self.rows[row]
        if col == 0:
            return item.label
        if col <= len(self.metrics):
            return item.values[col - 1]
        if col == len(self.metrics) + 1:
            return item.status
        if col == len(self.metrics) + 2:
            return source_text(item.source)
        return "; ".join(item.locations)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self.raw_value(index.row(), index.column())
        if role == Qt.DisplayRole:
            return _format_cell(value)
        if role == Qt.ToolTipRole:
            item = self.rows[index.row()]
            metric_index = index.column() - 1
            if 0 <= metric_index < len(item.locations):
                return f"{value}\n{item.locations[metric_index]}\n{item.status}"
            return str(value) if value is not None else "No value; see Status"
        if role == Qt.TextAlignmentRole and isinstance(value, (int, float)):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        if orientation == Qt.Vertical:
            return str(section + 1)
        prefix = f"{self.sheet_name}!" if self.sheet_name else ""
        if role == Qt.ToolTipRole and 1 <= section <= len(self.metrics):
            metric = self.metrics[section - 1]
            return f"{metric.title} [reference: {prefix}{metric.address}]"
        headers = ["Company"] + [m.title for m in self.metrics] + ["Status", "Source", "Extracted cells / headers"]
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
        writer.writerow([csv_value(model.headerData(c, Qt.Horizontal, Qt.ToolTipRole)) for c in range(model.columnCount())])
        for r in range(proxy.rowCount()):
            source_row = proxy.mapToSource(proxy.index(r, 0)).row()
            writer.writerow([csv_value(model.raw_value(source_row, c)) for c in range(model.columnCount())])


class ComparisonDialog(QDialog):
    open_source = Signal(object, str, int, int)

    def __init__(self, sources, reference, sheet_name, metrics, parent=None, match_labels=False):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"Compare — {sheet_name}")
        self.resize(1500, 720)
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
        self.match_labels = QCheckBox("Locate cells by item labels and header occurrence (allow different history lengths)")
        self.match_labels.setChecked(match_labels)
        layout.addWidget(self.match_labels)

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
        self.preset_button = QPushButton("Save comparison preset…")
        self.preset_button.clicked.connect(self.save_preset)
        layout.addWidget(self.preset_button)

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
        self.table.horizontalHeader().setDefaultSectionSize(140)
        self.table.setColumnWidth(0, 260)
        for col in range(len(metrics) + 1, len(metrics) + 4):
            self.table.setColumnWidth(col, 260)
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
        self.match_labels.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        worker = ComparisonWorker(self.sources, self.reference, self.sheet_name,
                                  self.metrics, self.check_labels.isChecked(), self,
                                  match_labels=self.match_labels.isChecked())
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
        self.match_labels.setEnabled(True)
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
        coordinate = row.coordinates[metric_index] if row.coordinates else (metric.row, metric.col)
        if coordinate is not None:
            self.open_source.emit(row.source, self.sheet_name, *coordinate)

    def save_preset(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save comparison preset", "comparison.json", "JSON (*.json)")
        if not path:
            return
        try:
            metrics = self.metrics
            if self.match_labels.isChecked():
                with Workbook(self.reference) as wb:
                    rows = wb.load_sheet(self.sheet_name).rows
                    metrics = [Metric(m.title, m.row, m.col, m.locator or cell_locator(rows, m)) for m in metrics]
            payload = {"version": 1, "sheet": self.sheet_name, "match_labels": self.match_labels.isChecked(),
                       "metrics": [asdict(m) for m in metrics]}
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.setText("Comparison preset saved")
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, "Cannot save preset", str(exc))

    def closeEvent(self, event):
        if self.worker is not None:
            self._closing = True
            self.cancel()
            event.ignore()
        else:
            event.accept()
