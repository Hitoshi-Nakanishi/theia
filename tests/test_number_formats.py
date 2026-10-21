import unittest

from theia.model import SheetModel, apply_excel_format


class NumberFormatTests(unittest.TestCase):
    def test_negative_and_zero_sections_preserve_the_workbook_display(self):
        for value, fmt, expected in (
            (-0.125, '0.0%;[Red](0.00%);"-"', '(12.50%)'),
            (0, '0.0%;[Red](0.00%);"-"', '-'),
            (0, '0.0%;(0.0%);-', '-'),
            (-1234.5, '#,##0;[Red]-#,##0.00', '-1,234.50'),
            (-0.125, '0.0%', '-12.5%'),
            (-0.125, '0.0%;0.00%', '12.50%'),
            (0, '0.0%;-0.0%;', ''),
            (0, '0.0%;-0.0%;"zero; value"', 'zero; value'),
        ):
            with self.subTest(value=value, fmt=fmt):
                self.assertEqual(apply_excel_format(value, fmt), expected)

    def test_unsupported_formats_do_not_apply_a_partial_numeric_match(self):
        for fmt in ('0.00"%"', r'0.00\%', '0.00E+00', '[>=1]0.0%;0.0'):
            for value in (0.125, -0.125):
                with self.subTest(fmt=fmt, value=value):
                    self.assertIsNone(apply_excel_format(value, fmt))

    def test_rendering_never_changes_the_raw_numeric_value(self):
        model = SheetModel([[-0.125]], cell_formats={(1, 1): '0.0%;(0.00%)'})
        self.assertEqual(model.data(model.index(0, 0)), '(12.50%)')
        self.assertEqual(model.raw_value(0, 0), -0.125)
