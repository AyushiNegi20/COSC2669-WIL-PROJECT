"""Unit tests for extraction bookkeeping and honest benchmark scoring."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_pdf_extraction import row_matches, score
from extract_bank_reports import expanded, grid, ordered_items, printed_label
from pdf_visibility import hidden_bracket, correct_tables


class ExtractionTests(unittest.TestCase):
    def test_invisible_white_bracket_on_white_page(self):
        char={'text':')','x0':10,'x1':12,'top':10,'bottom':20,'non_stroking_color':(1.0,)}
        self.assertTrue(hidden_bracket(char,[]))

    def test_white_bracket_on_dark_background_is_preserved(self):
        char={'text':')','x0':10,'x1':12,'top':10,'bottom':20,'non_stroking_color':(1.0,)}
        rect={'x0':0,'x1':30,'top':0,'bottom':30,'fill':True,'non_stroking_color':0.0}
        self.assertFalse(hidden_bracket(char,[rect]))

    def test_visible_black_negative_bracket_is_preserved(self):
        char={'text':')','x0':10,'x1':12,'top':10,'bottom':20,'non_stroking_color':(0.0,)}
        self.assertFalse(hidden_bracket(char,[]))

    def test_correction_does_not_mutate_raw_document(self):
        from types import SimpleNamespace
        char={'text':')','x0':10,'x1':12,'top':10,'bottom':20,'non_stroking_color':(1.0,)}
        page=SimpleNamespace(chars=[char],rects=[])
        doc={'tables':[{'data':{'table_cells':[{'text':'100)','bbox':{'l':0,'r':12,'t':10,'b':20,'coord_origin':'TOPLEFT'}}]}}]}
        cleaned,changes,unresolved=correct_tables(doc,page)
        self.assertEqual(doc['tables'][0]['data']['table_cells'][0]['text'],'100)')
        self.assertEqual(cleaned['tables'][0]['data']['table_cells'][0]['text'],'100')
        self.assertEqual(len(changes),1)
        self.assertEqual(unresolved,[])

    def test_page_ranges_are_one_based_inclusive(self):
        self.assertEqual(expanded([[17,19],[19,20]]),[17,18,19,20])

    def test_negative_sign_not_discarded(self):
        ref={'rows':[['Expenses',['(9,848)','(9,413)']]],'anchors':[]}
        result={'text':'Expenses (9,848) (9,413)','tables':[{'rows':[['Expenses','9,848','9,413']]}]}
        self.assertFalse(score(result,ref)['rows'][0]['row_values_correct'])
        self.assertTrue(score(result,ref)['rows'][0]['values_present_in_page'])

    def test_values_elsewhere_do_not_pass_binding(self):
        ref={'rows':[['Cash earnings',['7,091','7,102']]],'anchors':[]}
        result={'text':'Cash earnings 7,091 7,102','tables':[{'rows':[['Other','7,091','7,102']]}]}
        self.assertFalse(score(result,ref)['rows'][0]['row_values_correct'])

    def test_column_reversal_fails(self):
        ref={'rows':[['Cash earnings',['7,091','7,102']]],'anchors':[]}
        result={'text':'7,091 7,102','tables':[{'rows':[['Cash earnings','7,102','7,091']]}]}
        self.assertFalse(score(result,ref)['rows'][0]['row_values_correct'])

    def test_split_number_is_not_silently_repaired(self):
        self.assertEqual(row_matches(['Cash earnings','7,091','7,1','02'],'Cash earnings'),['7,091','7,1','02'])

    def test_subtotal_is_not_same_as_profit(self):
        self.assertIsNone(row_matches(['Cash earnings before income tax','10,132','10,095'],'Cash earnings'))

    def test_label_footnote_not_a_value(self):
        self.assertEqual(row_matches(['Other operating income(1)','3,415','3,482'],'Other operating income'),['3,415','3,482'])

    def test_empty_cell_remains_empty_not_zero(self):
        table={'data':{'num_rows':1,'num_cols':2,'table_cells':[{'start_row_offset_idx':0,'start_col_offset_idx':0,'text':'Revenue'}]}}
        self.assertEqual(grid(table),[['Revenue','']])

    def test_dash_not_replaced_with_zero(self):
        table={'data':{'num_rows':1,'num_cols':2,'table_cells':[{'start_row_offset_idx':0,'start_col_offset_idx':1,'text':'-'}]}}
        self.assertEqual(grid(table),[['','-']])

    def test_printed_label_not_report_year(self):
        doc={'texts':[{'label':'page_footer','text':'11 2025 Full Year Results Management Discussion and Analysis'}]}
        self.assertEqual(printed_label(doc,{})['value'],'11')

    def test_ambiguous_printed_label_is_null(self):
        doc={'texts':[{'label':'page_footer','text':'11'},{'label':'page_footer','text':'12'}]}
        self.assertIsNone(printed_label(doc,{})['value'])

    def test_body_order_is_not_texts_then_tables(self):
        doc={'body':{'children':[{'cref':'#/texts/0'},{'cref':'#/tables/0'},{'cref':'#/texts/1'}]},
             'texts':[{'text':'Heading'},{'text':'Footnote'}],'tables':[{'label':'table'}]}
        self.assertEqual([i.get('text',i.get('label')) for i in ordered_items(doc)],['Heading','table','Footnote'])


if __name__=='__main__':
    unittest.main()
