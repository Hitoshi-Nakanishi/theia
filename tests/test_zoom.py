import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QImage, QPainter, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QToolButton
from theia.app import MainWindow

APP = QApplication.instance() or QApplication([])
DEMO = Path(__file__).resolve().parents[1] / "examples/demo_models/0000.T_Demo_Model.xlsx"


class ZoomTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, self.temporary.name)
        QSettings("Theia", "Theia").clear()
        self.window = MainWindow()
        self.window.show()
        self.window.open_path(DEMO)
        APP.processEvents()

    def tearDown(self):
        self.window._set_zoom(100)
        self.window.close()
        self.temporary.cleanup()

    def test_slider_scales_all_text_and_cell_geometry_without_changing_selection(self):
        window = self.window
        table = window.table
        model, current = table.model(), table.currentIndex()
        widgets = [
            window.company_filter,
            window.company_tree,
            window.sheet_tabs,
            window._cell_value,
            window._status,
            table.br,
            table.br.horizontalHeader(),
        ]
        fonts = [widget.font().pixelSize() for widget in widgets]
        widths = [table.columnWidth(c) for c in range(model.columnCount())]
        window._zoom_slider.setValue(150)
        APP.processEvents()
        self.assertEqual(window._zoom_label.text(), "150%")
        for widget, size in zip(widgets, fonts):
            self.assertEqual(widget.font().pixelSize(), round(size * 1.5))
        view = table._view_for_range(current.row(), current.column(), 1, 1, table.freezeRows(), table.freezeCols())
        self.assertEqual(view.rowHeight(current.row()), 33)
        self.assertEqual([table.columnWidth(c) for c in range(model.columnCount())], [round(width * 1.5) for width in widths])
        self.assertIs(table.model(), model)
        self.assertEqual(table.currentIndex(), current)
        window._zoom_label.click()
        APP.processEvents()
        self.assertEqual([table.columnWidth(c) for c in range(model.columnCount())], widths)
        self.assertEqual(view.rowHeight(current.row()), 22)

    def test_zoom_survives_sheet_and_theme_changes_and_restart(self):
        window = self.window
        window._zoom_slider.setValue(150)
        window.sheet_tabs.setCurrentIndex(1)
        window._set_dark_mode(True)
        window._set_theme("aurora")
        APP.processEvents()
        self.assertEqual(window.table.br.rowHeight(1), 33)
        self.assertEqual(window.table.br.font().pixelSize(), 18)
        self.assertEqual(window._zoom_slider.value(), 150)
        restored = MainWindow()
        try:
            self.assertEqual(restored._zoom_percent, 150)
            self.assertEqual(restored._zoom_slider.value(), 150)
        finally:
            restored.close()

    def test_wheel_zoom_and_shortcuts_with_bounds_and_reset(self):
        window = self.window
        for modifiers, delta, expected in [
            (Qt.ControlModifier, 120, 110),
            (Qt.MetaModifier, -120, 100),
            (Qt.NoModifier, 120, 100),
        ]:
            event = QWheelEvent(
                QPointF(10, 10), QPointF(10, 10), QPoint(), QPoint(0, delta), Qt.NoButton, modifiers, Qt.NoScrollPhase, False
            )
            QApplication.sendEvent(window.table.br.viewport(), event)
            self.assertEqual(window._zoom_percent, expected)
        QTest.keyClick(APP.focusWidget(), Qt.Key_Equal, Qt.ControlModifier)
        self.assertEqual(window._zoom_percent, 110)
        QTest.keyClick(APP.focusWidget(), Qt.Key_Minus, Qt.ControlModifier)
        self.assertEqual(window._zoom_percent, 100)
        window._set_zoom(500)
        self.assertEqual(window._zoom_slider.value(), 200)
        self.assertFalse(window._zoom_in_action.isEnabled())
        self.assertEqual(window.findChild(QToolButton, "zoom-in").text(), "+")
        self.assertFalse(window.findChild(QToolButton, "zoom-in").isEnabled())
        window._set_zoom(1)
        self.assertEqual(window._zoom_slider.value(), 50)
        self.assertFalse(window._zoom_out_action.isEnabled())
        self.assertEqual(window.findChild(QToolButton, "zoom-out").text(), "−")
        self.assertFalse(window.findChild(QToolButton, "zoom-out").isEnabled())
        QTest.keyClick(APP.focusWidget(), Qt.Key_0, Qt.ControlModifier)
        self.assertEqual(window._zoom_percent, 100)

    def test_resized_columns_keep_their_proportions_without_zoom_drift(self):
        table = self.window.table
        table.br.horizontalHeader().resizeSection(2, 123)
        self.window._zoom_slider.setValue(150)
        self.assertEqual(table.columnWidth(2), 184)
        self.window._zoom_slider.setValue(100)
        self.assertEqual(table.columnWidth(2), 123)
        self.window._set_zoom("invalid")
        self.assertEqual(self.window._zoom_percent, 100)

    def test_arrow_cells_use_the_zoomed_font_when_painted(self):
        # Exercise the optimized renderer without loading Arrow for other fixtures.
        import pyarrow as pa  # noqa: PLC0415
        from theia.arrow_model import ArrowSheetModel  # noqa: PLC0415

        batch = pa.record_batch([pa.array(["Prepared value"])], names=["v_0"])
        batch = batch.replace_schema_metadata({b"n_rows": b"1", b"n_cols": b"1"})
        self.window.table.setModel(ArrowSheetModel(batch))
        self.window.table.setFreeze(0, 0)
        self.window.table.setColumnWidths([140])
        view = self.window.table.br
        for zoom, size in [(100, 12), (200, 24)]:
            self.window._zoom_slider.setValue(zoom)
            APP.processEvents()
            image = QImage(300, 100, QImage.Format_ARGB32)
            image.fill(Qt.white)
            painter = QPainter(image)
            try:
                option = QStyleOptionViewItem()
                view.initViewItemOption(option)
                option.rect = view.visualRect(view.model().index(0, 0))
                view.itemDelegate().paint(painter, option, view.model().index(0, 0))
                self.assertEqual(painter.font().pixelSize(), size)
            finally:
                painter.end()


if __name__ == "__main__":
    unittest.main()
