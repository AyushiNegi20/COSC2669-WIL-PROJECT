from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_retrieval_v7 import plan_question,company_metrics,RequestRetriever


class ConstraintTests(unittest.TestCase):
    def test_balance_sheet_total_alias(self):
        p=plan_question('NAB FY2024 balance-sheet total for all Group assets.')
        self.assertEqual(p['behavior'],'answer');self.assertIn('total_assets',p['metrics'])

    def test_cash_flow_distinction_is_definition_not_numeric_substitution(self):
        p=plan_question('NAB FY2025: what is adjusted to produce cash earnings, and does it show cash flows?')
        self.assertEqual(p['behavior'],'answer');self.assertEqual(p['intent'],'define')

    def test_description_requires_definition_evidence(self):
        p=plan_question('CBA FY2024 LCR description: what stress horizon does it cover?')
        self.assertEqual(p['intent'],'define');self.assertEqual(p['report_year'],2024)

    def test_coverage_ratio_word_does_not_mean_define(self):
        p=plan_question('What was NAB FY2024 Liquidity Coverage Ratio, as originally reported?')
        self.assertEqual(p['intent'],'find')

    def test_funding_contributions_are_explanation(self):
        p=plan_question('How did deposit costs combine with funding costs in NAB FY2024 NIM?')
        self.assertEqual(p['intent'],'explain')

    def test_new_guard_grains(self):
        for q in ['NAB FY2025 NIM for three months January through March.',
                  'CBA FY2024 lowest daily LCR; minimum across days.']:
            self.assertEqual(plan_question(q)['behavior'],'abstain')

    def test_unresolved_basis_is_not_selected_for_user(self):
        p=plan_question('CBA FY2024 profit: not decided whether statutory or adjusted.')
        self.assertEqual(p['behavior'],'clarify')

    def test_company_metric_bindings(self):
        self.assertEqual(company_metrics('NAB FY2025 DPS and CBA FY2024 basic cash EPS.',['CBA','NAB']),
                         {'CBA':{'basic_cash_eps'},'NAB':{'dividend_per_share'}})

    def test_shared_metrics_do_not_get_split_by_company_mention(self):
        self.assertIsNone(company_metrics('CBA and NAB: DPS and basic cash EPS.',['CBA','NAB']))

    def test_bridge_keeps_intermediate_source_row(self):
        engine=object.__new__(RequestRetriever)
        labels=['Underlying operating expenses','Restructuring','Total operating expenses']
        engine.records=[{'chunk_id':str(i),'kind':'financial_row','source':{'company':'CBA','report_year':2024},
            'row':i,'row_label':label,'table_id':'table','metric_tags':['operating_expenses']} for i,label in enumerate(labels)]
        p={'original_question':'Underlying costs and restructuring bridge','companies':['CBA'],'report_year':2024}
        result=engine.bridge_rows(p,[engine.records[0],engine.records[2]])
        self.assertEqual([r['row'] for r in result],[0,1,2])

    def test_no_evaluation_ids_in_runtime(self):
        code=(Path(__file__).resolve().parents[1]/'scripts/bank_retrieval_v7.py').read_text()
        for text in ['v2_','source_mapping.json','expected_answer','fresh01']:
            self.assertNotIn(text,code)


if __name__=='__main__': unittest.main()
