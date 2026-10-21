import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from openpyxl import Workbook as ExcelWorkbook
from PySide6.QtCore import QCoreApplication, QEvent, QItemSelectionModel, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from theia.app import MainWindow

APP = QApplication.instance() or QApplication([])


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        settings = QSettings(str(self.root / "settings.ini"), QSettings.IniFormat)
        patcher = patch("theia.app.QSettings", return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.window = MainWindow()
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.temporary.cleanup()

    def make_model(self, name):
        path = self.root / f"{name}.xlsx"
        workbook = ExcelWorkbook()
        sheet = workbook.active
        sheet.title = "Forecast"
        sheet.merge_cells("A1:D1")
        sheet["A1"] = "Generated company model"
        sheet["A2"] = "Revenue"
        sheet["B2"] = 125
        workbook.create_sheet("Valuation")["C3"] = 0
        workbook.save(path)
        workbook.close()
        return path

    def test_tabs_cell_navigation_and_merged_title_without_sidecars(self):
        self.assertEqual(self.window._sheet_stack.currentIndex(), 0)
        self.window.open_path(self.make_model("Company"))
        APP.processEvents()
        self.assertEqual(self.window._sheet_stack.currentIndex(), 1)
        self.assertEqual(self.window.sheet_tabs.tabText(0), "Forecast")
        self.assertEqual(self.window.table.freezeCols(), 0)
        self.assertEqual(self.window.table.tr.columnSpan(0, 0), 4)
        self.window._cell_address.setText("B2")
        self.window._go_to_cell()
        self.assertEqual(self.window._cell_value.text(), "125")
        self.window.sheet_tabs.setCurrentIndex(1)
        self.assertEqual(self.window._sheets_proxy.data(self.window.sheet_list.currentIndex()), "Valuation")
        self.window._cell_address.setText("C3")
        self.window._go_to_cell()
        self.assertEqual(self.window._cell_value.text(), "0")
        self.window.sheet_filter.setText("Forecast")
        APP.processEvents()
        self.assertEqual(self.window.sheet_tabs.count(), 1)
        self.assertEqual(self.window._sheets_proxy.data(self.window.sheet_list.currentIndex()), "Forecast")
        self.assertEqual(self.window.table.model().raw_value(0, 0), "Generated company model")
        self.window._set_sidebar_visible(False)
        self.assertFalse(self.window._nav_widgets[0].isVisible())
        self.assertTrue(self.window.sheet_tabs.isVisible())

    def test_opening_and_go_to_cell_return_keyboard_focus_to_the_grid(self):
        self.window.open_path(self.make_model("Company"))
        APP.processEvents()
        self.assertTrue(self.window.table.isAncestorOf(APP.focusWidget()))
        QTest.keyClick(APP.focusWidget(), Qt.Key_Down)
        QTest.keyClick(APP.focusWidget(), Qt.Key_Right)
        self.assertEqual(self.window._cell_address.text(), "B2")
        self.window._cell_address.setFocus()
        self.window._cell_address.setText("A1")
        QTest.keyClick(self.window._cell_address, Qt.Key_Return)
        self.assertTrue(self.window.table.isAncestorOf(APP.focusWidget()))
        QTest.keyClick(APP.focusWidget(), Qt.Key_Down)
        self.assertEqual(self.window._cell_address.text(), "A2")

    def test_clicking_a_sheet_tab_returns_keyboard_focus_to_the_grid(self):
        self.window.open_path(self.make_model("Company"))
        APP.processEvents()
        QTest.mouseClick(self.window.sheet_tabs, Qt.LeftButton, pos=self.window.sheet_tabs.tabRect(1).center())
        APP.processEvents()
        self.assertEqual(self.window.sheet_tabs.currentIndex(), 1)
        self.assertTrue(self.window.table.isAncestorOf(APP.focusWidget()))
        QTest.keyClick(APP.focusWidget(), Qt.Key_Down)
        self.assertEqual(self.window._cell_address.text(), "A2")

    def test_navigation_keeps_data_and_metadata_caches_bounded(self):
        for index in range(9):
            path = self.make_model(f"Company_{index}")
            path.with_suffix(".json").write_text(json.dumps({"sheets": {}}), encoding="utf-8")
        self.window.open_folder(self.root)
        companies = [
            item
            for item in self.window._companies_model.findItems("*", Qt.MatchWildcard | Qt.MatchRecursive)
            if item.data(Qt.UserRole) is not None
        ]
        for item in companies:
            self.window.company_tree.setCurrentIndex(self.window._companies_proxy.mapFromSource(item.index()))
            for row in range(self.window.sheet_tabs.count()):
                self.window.sheet_tabs.setCurrentIndex(row)
        self.assertLessEqual(len(self.window._workbooks), 1)
        self.assertLessEqual(len(self.window._sheet_model_cache), 4)
        self.assertLessEqual(len(self.window._sidecar_cache), 2)
        self.assertLessEqual(len(self.window._col_width_cache), 8)
        self.assertIsNone(self.window._preload_worker)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(len(self.window.table.findChildren(QItemSelectionModel)), 1)

    def test_plain_workbooks_do_not_load_arrow_runtime(self):
        path = self.make_model("Plain")
        code = (
            "import sys; from PySide6.QtWidgets import QApplication; "
            "from theia.app import MainWindow; from pathlib import Path; "
            "app=QApplication([]); window=MainWindow(); window.open_path(Path(sys.argv[1])); "
            "assert 'pyarrow' not in sys.modules; window.close()"
        )
        subprocess.run([sys.executable, "-c", code, str(path)], check=True, capture_output=True)

    def test_arrow_display_metadata_is_loaded_when_present(self):
        # Load Arrow only for the fixture that needs display sidecars.
        import pyarrow as pa  # noqa: PLC0415

        path = self.make_model("With_metadata")
        batch = pa.record_batch([pa.array(["Prepared value"])], names=["v_0"])
        batch = batch.replace_schema_metadata({b"n_rows": b"1", b"n_cols": b"1"})
        with pa.OSFile(str(path.with_suffix(".Forecast.arrow")), "wb") as stream:
            with pa.ipc.new_file(stream, batch.schema) as writer:
                writer.write(batch)
        self.window.open_path(path)
        self.assertEqual(self.window.table.model().raw_value(0, 0), "Prepared value")


if __name__ == "__main__":
    unittest.main()
