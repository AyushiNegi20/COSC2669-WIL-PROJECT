import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_bank_chunks import (ROOT, CONFIG, build, chunk, columns, expand_context, glossary,
                               header_rows, prefix, read, row_contexts, size, split_spans, table_chunks)
from validate_bank_chunks import validate


def fixture():
    source = {'document_id': 'test', 'company': 'CBA', 'document_title': 'Test FY2025',
              'report_year': 2025, 'report_period_end': '2025-06-30', 'pdf_page': 1,
              'printed_page': {'value': '1', 'reviewed': False}, 'source_sha256': 'a' * 64}
    table = {'id': 'test:p001:b001', 'type': 'table', 'rows': [
        ['', 'Full Year', ''], ['Metric', '2025 $m', '2024 $m'],
        ['Group - Continuing operations', '', ''], ['Profit', '10', '(5)'],
        ['Group - Including discontinued operations', '', ''], ['Profit', '12', '-']],
        'cells': [], 'quality_flags': ['table_semantics_need_review']}
    for r in range(6):
        for c in range(3):
            table['cells'].append({'start_row_offset_idx': r, 'start_col_offset_idx': c,
                'end_col_offset_idx': c + 1, 'col_span': 1, 'column_header': r < 2,
                'bbox': {'l': 10 + c * 100}})
    table['cells'][1]['col_span'] = 2
    table['cells'][1]['end_col_offset_idx'] = 3
    note = {'id': 'test:p001:b002', 'type': 'text', 'text': '(1) Comparative values were restated.'}
    page = {'id': 'test:p001', 'source': source, 'blocks': [table, note], 'quality': {'flags': []}}
    return page, read(ROOT / CONFIG)


class ChunkingTests(unittest.TestCase):
    def setUp(self):
        self.page, self.config = fixture()
        self.table = self.page['blocks'][0]
        self.data = build([self.page], self.config, [])

    def test_valid_contract(self):
        self.assertEqual(validate(self.data, [self.page], self.config, []), [])

    def test_deterministic(self):
        self.assertEqual(self.data, build([self.page], self.config, []))

    def test_no_input_mutation(self):
        before = copy.deepcopy(self.page)
        build([self.page], self.config, [])
        self.assertEqual(before, self.page)

    def test_merged_headers(self):
        self.assertEqual(columns(self.table, [0, 1])[2], ['Full Year', '2024 $m'])

    def test_no_blind_forward_fill(self):
        self.table['cells'][1]['col_span'] = 1
        self.assertEqual(columns(self.table, [0, 1])[2], ['2024 $m'])

    def test_scopes_do_not_merge(self):
        rows = [r for r in self.data['children'] if r['kind'] == 'table_rows']
        self.assertEqual(len(rows), 2)
        self.assertNotIn('Including discontinued', rows[0]['text'])
        self.assertNotIn('Continuing operations', rows[1]['text'])

    def test_negative_and_dash_preserved(self):
        text = '\n'.join(c['text'] for c in self.data['children'])
        self.assertIn('(5)', text)
        self.assertIn('= -', text)

    def test_years_not_document_year(self):
        self.assertIn('2024 $m', self.data['children'][0]['text'])
        self.assertEqual(self.data['children'][0]['source']['report_year'], 2025)

    def test_note_linked(self):
        r = self.data['children'][0]
        self.assertTrue(r['related_chunk_ids'])
        self.assertEqual(r['relationships'][0]['review_status'], 'unreviewed')

    def test_note_stops_at_heading(self):
        self.page['blocks'].insert(1, {'id': 'test:p001:heading', 'type': 'section_header', 'text': 'Other section'})
        self.assertEqual(build([self.page], self.config, [])['children'][0]['related_chunk_ids'], [])

    def test_note_never_crosses_pages(self):
        second = copy.deepcopy(self.page)
        second['source']['pdf_page'] = 2
        self.page['blocks'] = [self.table]
        second['blocks'] = [second['blocks'][1]]
        self.assertEqual(build([self.page, second], self.config, [])['children'][0]['related_chunk_ids'], [])

    def test_numeric_guard_quarantines(self):
        guard = [{'table_id': self.table['id'], 'row': 3, 'column': 1,
                  'category': 'numeric_scalar', 'issues': ['coordinate_text_mismatch']}]
        data = build([self.page], self.config, guard)
        self.assertEqual(data['children'][0]['quality']['status'], 'quarantined')
        self.assertEqual(data['parents'][0]['quality']['status'], 'quarantined')
        self.assertEqual(validate(data, [self.page], self.config, guard), [])

    def test_guard_flag_cannot_be_waived(self):
        guard = [{'table_id': self.table['id'], 'row': 3, 'column': 1,
                  'category': 'numeric_scalar', 'issues': ['coordinate_text_mismatch']}]
        self.assertTrue(validate(self.data, [self.page], self.config, guard))

    def test_mixed_headers_flag_not_certification(self):
        guard = [{'table_id': self.table['id'], 'row': 1, 'column': 1,
                  'category': 'uncheckable_numeric_text', 'issues': ['uncheckable_numeric_text']}]
        data = build([self.page], self.config, guard)
        self.assertIn('mixed_numeric_text_not_automatically_checked', data['children'][0]['quality']['issues'])
        self.assertFalse(data['children'][0]['quality']['calculation_ready'])

    def test_quarantine_configuration(self):
        self.config['quarantined_tables'][self.table['id']] = 'test defect'
        data = build([self.page], self.config, [])
        self.assertEqual(data['children'][0]['quality']['status'], 'quarantined')

    def test_default_expansion_denies_unreviewed(self):
        out = expand_context([self.data['children'][0]['chunk_id']], self.data['children'], self.data['parents'])
        self.assertEqual(out['records'], [])

    def test_parent_cannot_bypass_quarantine(self):
        self.data['children'][0]['quality']['status'] = 'quarantined'
        out = expand_context([self.data['children'][0]['chunk_id']], self.data['children'], self.data['parents'], allow_unreviewed=True)
        self.assertEqual(out['records'], [])

    def test_quarantined_parent_falls_back_to_clean_child(self):
        self.data['parents'][0]['quality']['status'] = 'quarantined'
        out = expand_context([self.data['children'][0]['chunk_id']], self.data['children'], self.data['parents'], allow_unreviewed=True)
        self.assertNotIn(self.data['parents'][0], out['records'])
        self.assertIn(self.data['children'][0], out['records'])

    def test_expansion_deduplicates(self):
        key = self.data['children'][0]['chunk_id']
        out = expand_context([key, key], self.data['children'], self.data['parents'], allow_unreviewed=True)
        ids = [r['chunk_id'] for r in out['records']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_small_budget_reports_omissions(self):
        out = expand_context([self.data['children'][0]['chunk_id']], self.data['children'], self.data['parents'], max_bytes=10, allow_unreviewed=True)
        self.assertEqual(out['records'], [])
        self.assertFalse(out['complete_context'])

    def test_size_budget_includes_prefix(self):
        self.config['child_max_utf8_bytes'] = 300
        data = build([self.page], self.config, [])
        for r in data['children']:
            self.assertTrue(r['utf8_bytes'] <= 300 or r['quality']['status'] == 'quarantined')

    def test_utf8_split_roundtrip(self):
        text = ('A sentence with £ and α. Another sentence. ' * 30)
        spans = list(split_spans(text, 80))
        self.assertEqual(''.join(text[a:b] for a, b in spans), text)
        self.assertTrue(all(size(text[a:b]) <= 80 for a, b in spans))

    def test_long_word_split_roundtrip(self):
        text = 'a' * 300
        self.assertEqual(''.join(text[a:b] for a, b in split_spans(text, 40)), text)

    def test_glossary_false_header_preserved(self):
        self.table['rows'] = [['NPAT', 'A complete definition. ' * 8], ['EPS', 'A second complete definition. ' * 8]]
        self.table['cells'] = [{'start_row_offset_idx': 0, 'start_col_offset_idx': 0,
                                'col_span': 1, 'column_header': True}]
        self.assertTrue(glossary(self.table))
        self.assertEqual(header_rows(self.table), [])
        data = build([self.page], self.config, [])
        self.assertEqual([c['kind'] for c in data['children'][:2]], ['definition', 'definition'])

    def test_changed_value_detected(self):
        self.data['children'][0]['text'] = self.data['children'][0]['text'].replace('(5)', '(6)')
        self.assertTrue(validate(self.data, [self.page], self.config, []))

    def test_wrong_source_detected(self):
        self.data['children'][0]['source'] = {**self.page['source'], 'pdf_page': 9}
        self.assertTrue(validate(self.data, [self.page], self.config, []))

    def test_missing_row_detected(self):
        self.data['children'].pop(0)
        self.assertTrue(validate(self.data, [self.page], self.config, []))

    def test_missing_header_detected(self):
        self.data['children'][0]['anchors'][0]['header_rows'] = []
        self.assertTrue(validate(self.data, [self.page], self.config, []))

    def test_fake_approval_detected(self):
        self.data['children'][0]['quality']['calculation_ready'] = True
        self.assertTrue(validate(self.data, [self.page], self.config, []))

    def test_swapped_column_binding_detected(self):
        self.data['children'][0]['anchors'][0]['column_paths'][1] = ['2024 $m']
        self.assertTrue(validate(self.data, [self.page], self.config, []))

    def test_missing_passage_detected(self):
        self.data['children'] = [c for c in self.data['children'] if c['kind'] != 'passage']
        self.assertTrue(validate(self.data, [self.page], self.config, []))

    def test_parent_keeps_all_raw_rows(self):
        for i, row in enumerate(self.table['rows']):
            self.assertIn(f'Row {i}: ' + ' | '.join(row), self.data['parents'][0]['text'])

    def test_nesting_expires_after_indented_subcategory(self):
        self.table['rows'] = [['Metric', '2025'], ['Assets', ''], ['Investment securities:', ''],
                              ['At amortised cost', '1'], ['Total assets', '2']]
        self.table['cells'] = [dict(start_row_offset_idx=r, start_col_offset_idx=0, column_header=r == 0,
                                  col_span=1, bbox={'l': 20 if r == 3 else 10}) for r in range(5)]
        contexts, _ = row_contexts(self.table, [0])
        self.assertEqual(contexts[3], [1, 2])
        self.assertEqual(contexts[4], [1])

    def test_unit_section_survives_incidental_indentation(self):
        self.table['rows'] = [['Metric', '2025'], ['Volumes ($bn)', ''], ['Loans', '1'], ['Deposits', '2']]
        self.table['cells'] = [dict(start_row_offset_idx=r, start_col_offset_idx=0, column_header=r == 0,
                                  col_span=1, bbox={'l': 20 if r == 2 else 10}) for r in range(4)]
        contexts, _ = row_contexts(self.table, [0])
        self.assertEqual(contexts[3], [1])

    def test_changed_version_changes_ids(self):
        self.config['version'] = 'different-version'
        self.assertNotEqual(self.data['children'][0]['chunk_id'], build([self.page], self.config, [])['children'][0]['chunk_id'])

    def test_missing_column_headers_quarantined(self):
        for c in self.table['cells']:
            c['column_header'] = False
        data = build([self.page], self.config, [])
        self.assertTrue(all(c['quality']['status'] == 'quarantined' for c in data['children'] if c['kind'] == 'table_rows'))


if __name__ == '__main__':
    unittest.main()
