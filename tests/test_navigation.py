import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from theia.model import SheetModel
from theia.table import FrozenPaneTable

APP = QApplication.instance() or QApplication([])


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.table = FrozenPaneTable()
        self.table.resize(600, 320)
        self.table.setModel(SheetModel([[r * 10 + c for c in range(8)] for r in range(12)]))
        self.table.setFreeze(2, 2)
        self.table.show()
        APP.processEvents()

    def tearDown(self):
        self.table.close()

    def click_cell(self, row, column):
        view = self.table._view_for_range(row, column, 1, 1, 2, 2)
        index = self.table.model().index(row, column)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center())
        self.assert_cell(row, column)

    def press(self, key, modifiers=Qt.NoModifier):
        QTest.keyClick(APP.focusWidget(), key, modifiers)

    def assert_cell(self, row, column):
        index = self.table.currentIndex()
        self.assertEqual((index.row(), index.column()), (row, column))

    def selected_cells(self):
        return {(i.row(), i.column()) for i in self.table.br.selectionModel().selectedIndexes()}

    def test_arrows_cross_each_frozen_boundary_in_both_directions(self):
        self.click_cell(1, 1)
        for key, cell in [
            (Qt.Key_Right, (1, 2)),
            (Qt.Key_Down, (2, 2)),
            (Qt.Key_Left, (2, 1)),
            (Qt.Key_Up, (1, 1)),
            (Qt.Key_Down, (2, 1)),
            (Qt.Key_Right, (2, 2)),
            (Qt.Key_Up, (1, 2)),
            (Qt.Key_Left, (1, 1)),
        ]:
            with self.subTest(key=key):
                self.press(key)
                self.assert_cell(*cell)
                self.assertEqual(self.selected_cells(), {cell})
                view = self.table._view_for_range(*cell, 1, 1, 2, 2)
                self.assertTrue(view.hasFocus())

    def test_enter_tab_and_shift_reverse_stay_in_the_grid(self):
        self.click_cell(1, 1)
        for key, modifiers, cell in [
            (Qt.Key_Tab, Qt.NoModifier, (1, 2)),
            (Qt.Key_Return, Qt.NoModifier, (2, 2)),
            (Qt.Key_Return, Qt.ShiftModifier, (1, 2)),
            (Qt.Key_Backtab, Qt.ShiftModifier, (1, 1)),
        ]:
            with self.subTest(key=key, modifiers=modifiers):
                self.press(key, modifiers)
                self.assert_cell(*cell)
                self.assertEqual(self.selected_cells(), {cell})

    def test_shift_arrows_keep_the_anchor_when_crossing_and_shrinking(self):
        self.click_cell(1, 1)
        self.press(Qt.Key_Right, Qt.ShiftModifier)
        self.press(Qt.Key_Right, Qt.ShiftModifier)
        self.press(Qt.Key_Down, Qt.ShiftModifier)
        self.assertEqual(self.selected_cells(), {(r, c) for r in (1, 2) for c in (1, 2, 3)})
        self.press(Qt.Key_Left, Qt.ShiftModifier)
        self.assertEqual(self.selected_cells(), {(r, c) for r in (1, 2) for c in (1, 2)})
        self.press(Qt.Key_Up, Qt.ShiftModifier)
        self.assertEqual(self.selected_cells(), {(1, 1), (1, 2)})
        self.press(Qt.Key_Right)
        self.assertEqual(self.selected_cells(), {(1, 3)})

    def test_control_arrows_jump_across_panes_and_keep_shift_anchor(self):
        self.table.setModel(SheetModel([[None, 1, 2, None, None, 3, None, None]] * 4))
        self.table.setFreeze(2, 2)
        self.click_cell(1, 1)
        self.press(Qt.Key_Right, Qt.ControlModifier | Qt.ShiftModifier)
        self.assert_cell(1, 2)
        self.press(Qt.Key_Right, Qt.ControlModifier | Qt.ShiftModifier)
        self.assert_cell(1, 5)
        self.assertEqual(self.selected_cells(), {(1, c) for c in range(1, 6)})
        self.press(Qt.Key_Right, Qt.ControlModifier)
        self.assert_cell(1, 7)
        self.press(Qt.Key_Left, Qt.ControlModifier)
        self.assert_cell(1, 5)

    def test_arrows_skip_merged_cells_and_collapsed_groups(self):
        self.table.setMergedCells(["C3:D3"])
        self.click_cell(2, 2)
        self.press(Qt.Key_Right)
        self.assert_cell(2, 4)
        self.press(Qt.Key_Left)
        self.assert_cell(2, 2)
        self.table.setGroups({3}, {4})
        self.table.toggleGroups()
        self.press(Qt.Key_Down)
        self.assert_cell(4, 2)
        self.press(Qt.Key_Right)
        self.assert_cell(4, 3)
        self.press(Qt.Key_Right)
        self.assert_cell(4, 5)

    def test_clicking_a_new_cell_resets_the_selection_anchor(self):
        self.click_cell(1, 1)
        self.press(Qt.Key_Right, Qt.ShiftModifier)
        self.click_cell(2, 2)
        self.press(Qt.Key_Down, Qt.ShiftModifier)
        self.assertEqual(self.selected_cells(), {(2, 2), (3, 2)})

    def test_arrows_work_without_freeze_panes(self):
        self.table.setFreeze(0, 0)
        view = self.table.br
        index = self.table.model().index(0, 0)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.visualRect(index).center())
        self.press(Qt.Key_Right)
        self.press(Qt.Key_Down)
        self.assert_cell(1, 1)
        self.press(Qt.Key_Left)
        self.press(Qt.Key_Up)
        self.assert_cell(0, 0)

    def test_navigation_scrolls_the_main_pane_and_stops_at_sheet_edges(self):
        self.table.resize(450, 180)
        APP.processEvents()
        self.click_cell(2, 2)
        for _ in range(20):
            self.press(Qt.Key_Down)
            self.press(Qt.Key_Right)
        self.assert_cell(11, 7)
        self.assertGreater(self.table.br.verticalScrollBar().value(), 0)
        self.assertGreater(self.table.br.horizontalScrollBar().value(), 0)
        self.press(Qt.Key_Up, Qt.ControlModifier)
        self.assert_cell(0, 7)
        self.press(Qt.Key_Left, Qt.ControlModifier)
        self.assert_cell(0, 0)
        self.press(Qt.Key_Up)
        self.press(Qt.Key_Left)
        self.assert_cell(0, 0)


if __name__ == "__main__":
    unittest.main()
