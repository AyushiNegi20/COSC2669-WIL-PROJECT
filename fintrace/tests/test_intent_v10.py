from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from answer_bank_v10 import interpret,focus_excerpts,Backend
from bank_operations_v9 import operation_plan
from bank_retrieval_service_v10 import direct_contrast

class IntentTests(unittest.TestCase):
    def test_direct_contrast_respects_bank_year_and_literal_exclusion(self):
        good={'kind':'passage','source':{'company':'CBA','report_year':2025},'body':'The cash basis is not a measure based on cash accounting or cash flows.'}
        wrong_year={**good,'source':{'company':'CBA','report_year':2024}}
        wrong_bank={**good,'source':{'company':'NAB','report_year':2025}}
        tangential={**good,'body':'Cash profit increased. Cash flows changed.'}
        self.assertEqual(direct_contrast([wrong_year,wrong_bank,tangential,good],{'company':'CBA','report_year':2025}),[good])

    def test_unspecified_profit_requires_choice(self):
        for q in ['CBA FY2025 profit please','How much profit did NAB make in FY2024?',
                  'For CBA FY2025 give me profit. I have not chosen an accounting basis.']:
            self.assertIsNotNone(interpret(q)['clarify'])

    def test_explicit_basis_not_blocked(self):
        for q in ['CBA FY2025 cash profit','NAB FY2024 statutory profit','CBA FY2025 basic cash EPS']:
            self.assertIsNone(interpret(q)['clarify'])

    def test_conceptual_difference_not_arithmetic(self):
        for q in ['For CBA FY2025 what is the difference between cash profit and cash flow?',
                  'For CBA FY2025 is cash profit cash that flowed into the bank?']:
            d=interpret(q);self.assertIsNone(d['clarify']);self.assertIn('Explain',d['question'])
            self.assertEqual(operation_plan(d['question'])['kind'],'none')

    def test_explicit_subtraction_keeps_arithmetic(self):
        q='Calculate CBA FY2025 cash profit minus statutory profit.'
        self.assertEqual(interpret(q)['question'],q)

    def test_negated_daily_target_only(self):
        q="Explain NAB FY2025 quarterly average LCR, rather than a single day's liquidity position."
        self.assertNotIn('single day',interpret(q)['question'])
        q='What was NAB FY2025 lowest daily LCR?'
        self.assertEqual(interpret(q)['question'],q)

    def test_not_chosen_is_not_silently_cash(self):
        self.assertIsNotNone(interpret('CBA FY2025 profit; I have not yet selected a basis.')['clarify'])

    def test_excerpt_filter_preserves_verbatim(self):
        relevant={'heading':'Cash profit','excerpts':[{'quote':'It is not a measure based on cash accounting or cash flows.','source_id':'x'}]}
        irrelevant={'heading':'Earnings per share (EPS) (basic)','excerpts':[{'quote':'Other measure','source_id':'y'}]}
        self.assertEqual(focus_excerpts([irrelevant,relevant],'Explain CBA cash profit versus cash flows','define'),[relevant])

    def test_contrast_can_be_under_statutory_heading(self):
        section={'heading':'Non-Cash Items Included in Statutory Profit','excerpts':[{'quote':'The cash basis is not a measure based on cash accounting or cash flows.'}]}
        self.assertEqual(focus_excerpts([section],'Explain cash profit versus cash flows','define'),[section])

    def test_bridge_tables_are_not_filtered(self):
        sections=[{'heading':'Cash reconciliation','excerpts':[]}]
        self.assertEqual(focus_excerpts(sections,'CBA cash profit','reconcile'),sections)

    def test_reporting_basis_excludes_unrelated_income_commentary(self):
        good={'heading':'Reporting basis','excerpts':[{'quote':'The statutory basis follows Australian Accounting Standards.'}]}
        other={'heading':'Operating income','excerpts':[{'quote':'Income increased.'}]}
        self.assertEqual(focus_excerpts([other,good],'Explain statutory reporting basis and accounting standards','explain'),[good])

    def test_invalid_question_rejected_before_model_load(self):
        backend=object.__new__(Backend)
        for value in [None,'',' '*3,'a'*2001]:
            with self.assertRaises(ValueError): backend.answer(value)

if __name__=='__main__': unittest.main()
