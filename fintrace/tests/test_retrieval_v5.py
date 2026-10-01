import copy
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_retrieval import ROOT,read
from bank_retrieval_v5 import query_plan,normalise_question,operation,HybridEvidenceRetriever,annual_explanation,semantic_focus
from bank_retrieval_v4 import build_view


class PlannerTests(unittest.TestCase):
    def test_valid_financial_words_not_typo_corrected(self):
        text='expense earning deposit customers margins shares'
        self.assertEqual(normalise_question(text),(text,[]))

    def test_annual_preference_excludes_interim_requests(self):
        self.assertTrue(annual_explanation('Why did costs rise in FY2025?'))
        for text in ['FY2025 half-year cost changes','Six months to March 2025','H1 FY2025 expenses','quarterly costs']:
            self.assertFalse(annual_explanation(text))

    def test_total_income_alias_not_loan_losses(self):
        p=query_plan('CBA FY2025 total income',{'credit_impairment':.9,'operating_income':.4})
        self.assertEqual(p['metrics'],['operating_income'])

    def test_bridge_retains_both_profit_bases(self):
        p=query_plan('Bridge NAB FY2025 cash earnings to the accounting bottom line.')
        self.assertEqual(set(p['metrics']),{'cash_profit','statutory_npat'})
        self.assertEqual(p['intent'],'reconcile')

    def test_focus_does_not_modify_retrieval_scope(self):
        q='NAB FY2025 report cash earnings, not a later restatement.'
        focus=semantic_focus(q)
        self.assertNotIn('FY2025',focus)
        self.assertIn('not a later restatement',focus)
        self.assertEqual(query_plan(q)['report_year'],2025)

    def test_indirect_concept_uses_semantic_candidate(self):
        p=query_plan('NAB FY2025 report: quantify common equity relative to risk-weighted assets.',{'cet1':.75,'lcr':.4})
        self.assertEqual(p['metrics'],['cet1'])
        self.assertEqual(p['metric_resolution'],'semantic_candidate_not_verified')

    def test_close_semantic_candidates_require_clarification(self):
        p=query_plan('NAB FY2025 report: quantify the protective reserve.',{'cet1':.65,'lcr':.64})
        self.assertEqual(p['behavior'],'clarify')

    def test_low_semantic_similarity_requires_clarification(self):
        p=query_plan('CBA FY2025 report: tell me the quantity.',{'total_assets':.2,'gross_loans':.1})
        self.assertEqual(p['behavior'],'clarify')

    def test_ambiguous_money_not_resolved_by_high_similarity(self):
        p=query_plan('How much money did CBA make in FY2025?',{'cash_profit':.99,'statutory_npat':.8})
        self.assertEqual(p['behavior'],'clarify')

    def test_exact_metric_not_overridden_by_similarity(self):
        p=query_plan('CBA FY2025 report net interest margin',{'cash_profit':.99,'nim':.2})
        self.assertEqual(p['metrics'],['nim'])

    def test_typo_correction_is_visible(self):
        p=query_plan('Commonwelth Bank FY2025 report: net intrest margin')
        self.assertEqual(p['companies'],['CBA'])
        self.assertEqual(p['metrics'],['nim'])
        self.assertEqual(len(p['corrections']),2)
        self.assertIn('Commonwelth',p['original_question'])

    def test_two_digit_financial_year(self):
        self.assertEqual(query_plan('NAB FY24 report cash earnings')['report_year'],2024)

    def test_explicit_report_and_comparative_distinct(self):
        p=query_plan('Compare CBA FY2024 NIM with FY2025 in the FY2025 report.')
        self.assertEqual(p['report_year'],2025)
        self.assertEqual(p['value_years'],[2024,2025])

    def test_natural_explanations(self):
        for q in ['What made the yearly IT bill bigger?','What reasons did management give?','Why did staff costs rise?']:
            self.assertEqual(operation(q),'explain')

    def test_negated_restatement_not_reconciliation(self):
        self.assertEqual(operation('Find operating expenses, not a later restatement.'),'find')

    def test_definition_before_explanation(self):
        self.assertEqual(operation('Explain the definition of cash earnings.'),'define')

    def test_scope_guards(self):
        for q in ['What is today\'s CBA share price?','What will NAB pay for each share next year?',
                  'What is my NAB account balance?','Give Macquarie FY2025 cash profit.',
                  'CBA FY2023 cash profit','NAB FY2025 report: what is the account balance of customer Jane Smith?']:
            with self.subTest(q=q): self.assertEqual(query_plan(q)['behavior'],'abstain')

    def test_generic_definition_needs_bank(self):
        self.assertEqual(query_plan('Define cash earnings')['behavior'],'clarify')

    def test_positive_deposits_not_personal_information(self):
        self.assertEqual(query_plan('NAB FY2025 report customer deposits')['behavior'],'answer')

    def test_catalog_has_no_values_or_source_anchors(self):
        catalog=read(ROOT/'config/financial_concepts_v5.json')
        self.assertEqual(len(catalog),13)
        for item in catalog.values(): self.assertEqual(set(item),{'label','description'})
        for file in ['scripts/bank_retrieval_v5.py','config/financial_concepts_v5.json']:
            text=(ROOT/file).read_text(encoding='utf-8')
            for term in ['bank-q','indirect-0','required_evidence_groups','expected_answer','metric_scope_13.json','nab25:p0','cba25:p0']:
                self.assertNotIn(term,text)


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/'data/processed/banking_chunks_v1/children.jsonl').exists():
            raise unittest.SkipTest('Requires the generated local corpus; see docs/SETUP.md')
        cls.records,cls.units=build_view()
        cls.engine=HybridEvidenceRetriever(cls.records,cls.units,np.zeros((len(cls.records),2)))

    def test_company_and_vintage_filters(self):
        p=query_plan('NAB FY2024 report customer deposits')
        result=self.engine.search_plan(p,np.zeros(2))
        self.assertTrue(result['records'])
        self.assertTrue(all(r['source']['company']=='NAB' and r['source']['report_year']==2024 for r in result['records']))

    def test_no_evidence_on_abstention(self):
        p=query_plan('What is today\'s CBA share price?')
        self.assertEqual(self.engine.search_plan(p,np.zeros(2))['records'],[])

    def test_reconciliation_expansion_preserves_explicit_scope(self):
        p=query_plan('NAB FY2025 disclosures: explain the reclassification of comparative expenses.')
        result=self.engine.search_plan(p,np.zeros(2))
        self.assertTrue(result['records'])
        for record in result['records']:
            self.assertEqual(record['source']['company'],'NAB')
            self.assertEqual(record['source']['report_year'],2025)

    def test_annual_report_only_remains_after_reconciliation(self):
        p=query_plan('NAB FY2025 annual report: reconcile the reclassification of comparative expenses.')
        result=self.engine.search_plan(p,np.zeros(2))
        self.assertTrue(result['records'])
        self.assertTrue(all('_ar' in r['source']['document_id'] for r in result['records']))

    def test_no_quarantine_or_approval(self):
        p=query_plan('CBA FY2025 report cash profit')
        for r in self.engine.search_plan(p,np.zeros(2))['records']:
            self.assertNotEqual(r['quality']['status'],'quarantined')
            self.assertFalse(r['quality']['calculation_ready'])

    def test_bad_method_rejected(self):
        with self.assertRaises(ValueError): self.engine.search_plan(query_plan('NAB cash profit'),np.zeros(2),'magic')

    def test_reranker_required(self):
        with self.assertRaises(ValueError): self.engine.search_plan(query_plan('NAB cash profit'),np.zeros(2),'hybrid_rerank')


if __name__=='__main__': unittest.main()
