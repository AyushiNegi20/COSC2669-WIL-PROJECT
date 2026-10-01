"""Synthetic release gates; no gold answer values or API requests."""
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_evidence_relevance import relevance
from bank_query_routing import normalise_query,checked_numeric_request,generic_loan_lookup
from bank_operations_v9 import operation_plan
from bank_source_selection import render_selected_sources
from bank_generation_v11 import evidence_cards
from test_generation_frozen_improvements import evidence


class ReleaseGates(TestCase):
    def test_capital_is_not_operating_expenses(self):
        q='Did the capital position strengthen?'
        self.assertFalse(relevance(q,'Operating expenses rose due to higher personnel costs.')[0])
        self.assertTrue(relevance(q,'The CET1 capital ratio fell, reflecting a capital distribution.')[0])
        self.assertTrue(relevance(q,'The CET1 capital ratio was 12.5%, a decrease of 0.2 percentage points.')[0])
        self.assertFalse(relevance(q,'The capital position meets requirements. The requirement increases next year.')[0])

    def test_capital_evidence_survives_performance_topic(self):
        from bank_narrative_routing import relevant_sections
        section={'source':{'company':'NAB','report_year':2025},'heading':'Group capital',
            'excerpts':[{'source_id':'capital','quote':'The CET1 capital ratio decreased following a capital distribution.'}]}
        self.assertEqual(relevant_sections([section],{'topic':'performance','company':'NAB','year':2025},
                         'Did NAB capital position strengthen in FY2025?'),[section])

    def test_equity_return_is_not_private_equity_exposure(self):
        q='What was return on equity?'
        self.assertFalse(relevance(q,'The Group lends to private equity sponsors.')[0])
        self.assertTrue(relevance(q,'Return on average equity declined as retained earnings grew.')[0])

    def test_nii_and_nim_not_substituted(self):
        self.assertFalse(relevance('What is net interest income?','Net interest margin rose.')[0])
        self.assertFalse(relevance('What was NIM?','Net interest income increased.')[0])

    def test_related_party_loans_not_group_total(self):
        p='Total loans to KMP and related parties increased.'
        self.assertFalse(relevance('What were total loans?',p)[0])
        self.assertTrue(relevance('What were loans to KMP?',p)[0])

    def test_cost_ratio_does_not_accept_expense_amount(self):
        self.assertFalse(relevance('What was cost-to-income ratio?','Operating expenses increased.')[0])
        self.assertTrue(relevance('What was cost-to-income ratio?','The cost to income ratio improved.')[0])

    def test_grouped_investment_categories_are_not_subarea_ranking(self):
        from test_cba_reports import fixture
        from cba_investment_answer import answer
        from types import SimpleNamespace
        result=answer('Is CBA putting more investment into technology or into branches in FY2025?',
                      {'banks':['CBA'],'years':[2025],'defaults':[]},
                      SimpleNamespace(data={'investment_tables':[fixture()]}),
                      {'topic':'spending','task':'comparison'})
        self.assertEqual(result['answer']['status'],'partial_answer')
        self.assertEqual(result['answer']['summary_statements'][0]['kind'],'limitation')

    def test_irrelevant_passage_never_reaches_model_or_fallback(self):
        e=evidence('Personnel costs increased due to salary inflation, partly offset by savings.')
        e['question']='Did the capital position strengthen?'
        c=Mock();c.config={'model':'fixture'};c.chat.side_effect=TimeoutError('should not be called')
        result=render_selected_sources(e,c,evidence_cards(e['answer']))
        c.chat.assert_not_called()
        self.assertEqual(result['answer']['status'],'unable_to_verify')
        self.assertEqual(result['answer']['source_excerpts'],[])

    def test_relevance_is_not_a_blanket_ban_on_new_topics(self):
        self.assertTrue(relevance('What is the whistleblower policy?','The whistleblower policy protects eligible disclosures.')[0])

    def test_plain_money_gets_labelled_profit_interpretation(self):
        q,notes=normalise_query('How much money did CBA make in the 2025 financial year?')
        self.assertIn('profit',q);self.assertTrue(notes)
        original='How much money did CBA make from selling a subsidiary in 2025?'
        self.assertEqual(normalise_query(original)[0],original)

    def test_dividend_wording_uses_checked_path(self):
        for q in ('What did NAB pay shareholders per share in 2025?',
                  'What dividend did CBA pay per share in 2025, and how does it compare to the year before?'):
            fixed,_=normalise_query(q)
            self.assertTrue(checked_numeric_request(fixed),fixed)

    def test_single_year_movements_have_explicit_comparison_window(self):
        for bank in ('CBA','NAB'):
            for measure in ('cash profit','net interest margin','customer deposits'):
                for wording in (f'Did {bank} {measure} grow in FY2025?',
                                f'How did {bank} {measure} move over the year to September 2025?'):
                    fixed,notes=normalise_query(wording)
                    self.assertIn('FY2024',fixed)
                    self.assertEqual(operation_plan(fixed)['kind'],'change')
                    self.assertTrue(notes)
                    self.assertEqual(normalise_query(fixed)[0],fixed)

    def test_period_and_reasoning_not_silently_expanded(self):
        for q in ('Why did NAB cash profit grow in FY2025?',
                  'How did NAB cash profit change in the half-year to March 2025?',
                  'How did NAB cash profit change in FY2024?',
                  'What will NAB cash profit grow to in FY2025?'):
            self.assertNotIn('Calculate the change',normalise_query(q)[0])

    def test_different_loan_scopes_are_not_typo_repairs(self):
        for q in ('NAB net loans FY2025','CBA total loans FY2025','NAB housing loans FY2025'):
            self.assertEqual(normalise_query(q)[0],q)
        self.assertTrue(generic_loan_lookup("What were NAB's total loans at the end of FY2025?"))
        for qualifier in ('to KMP','to directors','in New Zealand','to corporate customers','to related parties','net of allowances'):
            self.assertFalse(generic_loan_lookup(f'What were NAB total loans {qualifier} in FY2025?'))
