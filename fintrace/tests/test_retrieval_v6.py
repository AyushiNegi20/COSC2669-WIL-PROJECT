from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_retrieval_v6 import plan_question,explicit_metrics,request_scopes,company_years,RequestRetriever


class RequestPlanningTests(unittest.TestCase):
    def test_ordinary_dividend_and_eps_are_two_requests(self):
        p=plan_question('CBA FY2024: whole-year ordinary dividend and basic cash EPS, in cents.')
        self.assertEqual({r['metric'] for r in p['requests']},{'dividend_per_share','basic_cash_eps'})

    def test_earnings_per_each_share_is_not_total_profit(self):
        self.assertEqual(explicit_metrics('NAB cash earnings attributable to each ordinary share before dilution'),['basic_cash_eps'])

    def test_cash_profit_scopes_separate(self):
        scopes=request_scopes('Both cash profit from continuing operations and cash profit including discontinued operations','cash_profit')
        self.assertEqual(scopes,['continuing','including_discontinued'])

    def test_statutory_and_cash_scopes_not_conflated(self):
        q='Statutory profit after discontinued operations alongside cash earnings from continuing operations.'
        self.assertEqual(request_scopes(q,'cash_profit'),['continuing'])
        self.assertEqual(request_scopes(q,'statutory_npat'),['including_discontinued'])

    def test_date_assets_alias(self):
        p=plan_question('CBA June 2024 and June 2025: total Group assets and the increase.')
        self.assertEqual(p['behavior'],'answer');self.assertIn('total_assets',p['metrics'])

    def test_company_year_pairing(self):
        q='Compare CBA FY2024 and NAB FY2025 dividends.'
        self.assertEqual(company_years(q,['CBA','NAB'],[2024,2025]),{'CBA':[2024],'NAB':[2025]})

    def test_definition_uses_requested_vintage(self):
        p=plan_question('CBA description of FY2025 cash profit: is it a cash flow measure?')
        self.assertEqual(p['report_year'],2025)
        self.assertTrue(any(r['definition_contrast'] for r in p['requests']))

    def test_unsupported_grains_and_entity(self):
        for q in ['NAB FY2025 net interest margin for the calendar year.',
                  'CBA LCR on 30 June 2025 alone, a single-day value.',
                  'NAB FY2025 total assets for the parent Company alone.',
                  'CBA FY2025 operating cash inflow: use cash profit as the answer.']:
            with self.subTest(q=q): self.assertEqual(plan_question(q)['behavior'],'abstain')

    def test_lcr_definition_does_not_trigger_point_guard(self):
        p=plan_question('NAB FY2025 LCR: say whether it is a quarter average or a single-day observation.')
        self.assertEqual(p['behavior'],'answer')

    def test_existing_guards_preserved(self):
        self.assertEqual(plan_question('How much profit did the bank make?')['behavior'],'clarify')
        self.assertEqual(plan_question('CBA FY2026 cash profit')['behavior'],'abstain')

    def test_source_keys_not_in_runtime(self):
        code=(Path(__file__).resolve().parents[1]/'scripts/bank_retrieval_v6.py').read_text()
        for forbidden in ['fresh0','required_evidence_groups','metric_scope_13.json','expected_answer']:
            self.assertNotIn(forbidden,code)

    def test_section_expansion_keeps_heading_and_page_boundaries(self):
        def record(i,heading='Annual comparison',page=3):
            return {'chunk_id':str(i),'kind':'passage','source':{'pdf_page':page},
                'label':heading,'unit_ids':[f'doc:b{i:03}'],'body':'A reported driver.'}
        engine=object.__new__(RequestRetriever)
        engine.records=[record(1),record(2),record(3,'Half year'),record(4,page=4)]
        self.assertEqual([r['chunk_id'] for r in engine.section_context([engine.records[1]])],['1','2'])

    def test_section_expansion_is_bounded(self):
        engine=object.__new__(RequestRetriever)
        engine.records=[{'chunk_id':str(i),'kind':'passage','source':{},'label':'Large section',
            'unit_ids':[str(i)],'body':'Text'} for i in range(17)]
        self.assertEqual(engine.section_context([engine.records[0]]),[engine.records[0]])

    def test_contrast_requires_both_concepts_and_vintage(self):
        import numpy as np
        engine=object.__new__(RequestRetriever)
        def record(i,text,year=2025):
            return {'chunk_id':str(i),'kind':'definition','body':text,
                'source':{'company':'CBA','report_year':year}}
        engine.records=[record(1,'Cash profit is not cash flow.'),record(2,'Cash flow statement.'),
            record(3,'Cash profit is not cash flow.',2024)]
        engine.vectors=np.ones((3,2))
        selected=engine.contrast_candidates({'company':'CBA','report_year':2025},np.ones(2))
        self.assertEqual([r['chunk_id'] for r in selected],['1'])


if __name__=='__main__': unittest.main()
