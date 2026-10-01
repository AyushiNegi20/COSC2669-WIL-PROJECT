"""Synthetic failures exercise the guard without adding reference answers."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from check_numeric_consistency import number_key, page_numbers, classify, cell_bbox, check_cell

SETTINGS = {'coordinate_tolerance_points': 1, 'text_x_tolerance_points': 2,
            'text_y_tolerance_points': 2}


def make_page(text, colour=0):
    chars = [{'text': char, 'x0': 10+i*5, 'x1': 15+i*5, 'top': 10, 'bottom': 20,
              'doctop': 10, 'upright': True, 'height': 10, 'width': 5,
              'non_stroking_color': colour if char == ')' else 0}
             for i, char in enumerate(text)]
    return SimpleNamespace(width=300, height=300, chars=chars, rects=[])


def make_cell(text, source_length=None):
    return {'text': text, 'bbox': {'l': 10, 't': 10, 'r': 10+5*(source_length or len(text)),
                                  'b': 20, 'coord_origin': 'TOPLEFT'}}


class NumericConsistencyTests(unittest.TestCase):
    def check(self, extracted, local, native=None):
        native = local if native is None else native
        return check_cell(make_cell(extracted, len(local)), native, page_numbers(native),
                          make_page(local), SETTINGS)

    def test_parentheses_equal_negative_not_positive(self):
        self.assertEqual(number_key('(1,234)'), number_key('-1234'))
        self.assertNotEqual(number_key('(1,234)'), number_key('1234'))

    def test_percent_is_not_bare_number(self):
        self.assertNotEqual(number_key('12%'), number_key('12'))
        self.assertNotIn(number_key('12'), page_numbers('12%'))

    def test_no_substring_match(self):
        self.assertNotIn(number_key('100'), page_numbers('1,100 1000 abc100 100) (100)'))

    def test_decimals_preserved(self):
        self.assertNotEqual(number_key('1.25'), number_key('125'))
        self.assertEqual(number_key('1.20'), number_key('1.2'))

    def test_split_digits_and_malformed_grouping_rejected(self):
        for text in ('1 234', '7,1 02', '12,34', '100)', '1.2.3', '1e3', '100(1)'):
            self.assertIsNone(number_key(text), text)

    def test_page_tokenizer_does_not_merge_columns(self):
        keys = page_numbers('100      200\n300')
        self.assertEqual(keys, {number_key(x) for x in ('100', '200', '300')})

    def test_placeholder_in_previous_column_is_not_a_negative_sign(self):
        self.assertIn(number_key('796'), page_numbers(' -         796     611'))
        self.assertNotIn(number_key('-796'), page_numbers(' -         796     611'))

    def test_unicode_minus_and_nonbreaking_space(self):
        self.assertEqual(number_key('\u2212\u00a0123'), number_key('(123)'))

    def test_dash_is_not_zero(self):
        self.assertEqual(classify('-'), 'placeholder_not_zero')
        self.assertIsNone(number_key('-'))

    def test_dates_and_footnotes_are_uncheckable(self):
        for text in ('30 Jun 25 $M', '100(1)', 'FY2025', '1,234 million'):
            self.assertEqual(classify(text), 'uncheckable_numeric_text')

    def test_correct_number_matches_both(self):
        result = self.check('1,234', '1,234')
        self.assertEqual(result['issues'], [])

    def test_swapped_value_present_elsewhere_fails_coordinate_check(self):
        result = self.check('200', '100', '100 200')
        self.assertEqual(result['page_check'], 'matched')
        self.assertEqual(result['coordinate_check'], 'mismatch')

    def test_silent_digit_error_fails_both(self):
        result = self.check('109', '100')
        self.assertEqual(result['page_check'], 'not_found')
        self.assertEqual(result['coordinate_check'], 'mismatch')

    def test_negative_sign_loss_fails_both(self):
        result = self.check('100', '(100)')
        self.assertEqual(result['page_check'], 'not_found')
        self.assertEqual(result['coordinate_check'], 'mismatch')

    def test_missing_coordinates_flagged(self):
        result = check_cell({'text': '100'}, '100', page_numbers('100'), make_page('100'), SETTINGS)
        self.assertIn('uncheckable_coordinates', result['issues'])

    def test_empty_coordinate_region_flagged(self):
        cell = make_cell('100')
        cell['bbox'].update(t=100, b=110)
        result = check_cell(cell, '100', page_numbers('100'), make_page('100'), SETTINGS)
        self.assertIn('no_source_glyphs', result['issues'])

    def test_bottom_left_conversion(self):
        cell = {'bbox': {'l': 10, 'r': 20, 't': 290, 'b': 280, 'coord_origin': 'BOTTOMLEFT'}}
        self.assertEqual(cell_bbox(cell, 300, 300), (10, 10, 20, 20))

    def test_invalid_box_rejected(self):
        for value in (float('nan'), -1, 500):
            cell = make_cell('100')
            cell['bbox']['l'] = value
            self.assertIsNone(cell_bbox(cell, 300, 300))

    def test_logged_invisible_bracket_rechecked_and_no_mutation(self):
        cell = make_cell('100', 4)
        cell.update(raw_text='100)', extraction_correction={
            'method': 'source_confirmed_background_colour_bracket',
            'raw_text': '100)', 'corrected_text': '100'})
        before = copy.deepcopy(cell)
        result = check_cell(cell, '100)', page_numbers('100)'), make_page('100)', 1), SETTINGS)
        self.assertEqual(result['page_check'], 'matched_via_logged_correction')
        self.assertEqual(result['coordinate_check'], 'matched')
        self.assertEqual(cell, before)

    def test_logged_correction_does_not_override_visible_bracket(self):
        cell = make_cell('100', 4)
        cell.update(raw_text='100)', extraction_correction={
            'method': 'source_confirmed_background_colour_bracket',
            'raw_text': '100)', 'corrected_text': '100'})
        result = check_cell(cell, '100)', page_numbers('100)'), make_page('100)', 0), SETTINGS)
        self.assertEqual(result['page_check'], 'not_found')
        self.assertEqual(result['coordinate_check'], 'mismatch')

    def test_unsupported_text_is_not_silently_passed(self):
        result = self.check('100(1)', '100(1)')
        self.assertIn('uncheckable_numeric_text', result['issues'])
        self.assertEqual(result['page_check'], 'not_applicable')


if __name__ == '__main__':
    unittest.main()
