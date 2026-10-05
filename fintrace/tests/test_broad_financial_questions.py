"""Broad prompts must not erase financial qualifiers or conceal partial coverage."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_broad_questions import subject, answer, eps_answer
from bank_source_cells import row_identity, EPS_METRICS, LABELS
from bank_conversation import paragraphs


class BroadGrammarTests(unittest.TestCase):
    def test_plain_prompts_are_recognised(self):
        for bank in ('CBA','NAB'):
            for measure in ('income','loans','margin','EPS'):
                self.assertEqual(subject(f'What was {bank} {measure} in FY2025?'),measure.lower())
            self.assertEqual(subject(f'How much income did {bank} earn in FY2025?'),'income')
            self.assertEqual(subject(f'What were {bank} total loans in FY2025?'),'loans')

    def test_distinct_measures_and_prose_do_not_match(self):
        for q in ('NAB net loans FY2025','NAB housing loans FY2025',
                  'CBA profit margin FY2025','NAB income tax FY2025',
                  'NAB other operating income FY2025','CBA net interest income FY2025',
                  'CBA loans to directors FY2025','CBA loans in New Zealand FY2025',
                  'CBA EPS for the parent company FY2025','Why did NAB EPS rise FY2025?',
                  'What does EPS mean?','CBA EPS in the half-year FY2025',
                  'CBA EPS at 31 December 2025','CBA EPS from discontinued operations only FY2025'):
            self.assertIsNone(subject(q),q)

    def test_explicit_eps_qualifiers_are_preserved(self):
        for q in ('NAB diluted statutory EPS FY2025','CBA basic cash EPS FY2025',
                  'CBA EPS from continuing operations FY2025',
                  'NAB EPS including discontinued operations FY2025'):
            self.assertEqual(subject(q),'eps')

    def test_ui_filter_context_keeps_broad_route(self):
        from bank_ui_scope import resolve_scope
        for measure in ('EPS','income','loans','margin'):
            q=resolve_scope('What was '+measure+'?',{'company':'NAB','year':'2025'})['effective_question']
            self.assertEqual(subject(q),measure.lower())
        self.assertIsNone(subject('What were net loans?\nFor NAB, FY2025.'))
        self.assertIsNone(subject('What was EPS?\nFor the parent company.'))

    def test_other_banks_and_unsupported_years_not_answered(self):
        core=Mock()
        for context in ({'banks':['CBA','NAB'],'years':[2025]},
                        {'banks':['NAB'],'years':[2026]}):
            self.assertIsNone(answer('What was NAB EPS FY2025?',context,core))
        core.answer.assert_not_called()

    def test_broad_loans_are_labelled_not_silent_substitution(self):
        core=Mock()
        core.answer.return_value={'answer':{'status':'source_bound_answer','parts':[
            {'claims':[{'cell':{'metric':'gross_loans'}}],'issues':[]}]}}
        result=answer('What were CBA loans FY2025?',{'banks':['CBA'],'years':[2025]},core)
        self.assertIn('gross loans and acceptances',core.answer.call_args.args[0])
        self.assertIn('not net loans',result['answer']['important_notes'][0])

    def test_broad_income_is_explicitly_not_exhaustive(self):
        core=Mock()
        core.answer.return_value={'answer':{'status':'source_bound_answer','parts':[
            {'claims':[{'cell':{'metric':'operating_income'}}],'issues':[]}]}}
        result=answer('What was CBA income FY2025?',{'banks':['CBA'],'years':[2025]},core)
        self.assertEqual(result['answer']['status'],'partial_answer')
        self.assertIn('not an exhaustive',result['answer']['message'])


class EpsIdentityTests(unittest.TestCase):
    def test_real_corpus_eps_variants_preserve_basis_and_scope(self):
        root=Path(__file__).resolve().parents[1]
        if not (root/'data/processed/banking_chunks_v1/children.jsonl').exists():
            self.skipTest('Requires the generated local corpus')
        from bank_retrieval_v4 import build_view
        from bank_source_cells import CellBinder
        records,_=build_view()
        evidence=SimpleNamespace(retriever=SimpleNamespace(engine=SimpleNamespace(records=records)),binder=CellBinder())
        core=SimpleNamespace(evidence_backend=SimpleNamespace(core=evidence))
        for bank,count in (('CBA',4),('NAB',6)):
            result=eps_answer(f'What was {bank} EPS FY2025?',{'banks':[bank],'years':[2025]},core)
            cells=[c['cell'] for p in result['answer']['parts'] for c in p['claims']]
            self.assertEqual(len(cells),count)
            self.assertTrue(all(c['unit']=='cents/share' and c['period_kind']=='annual' for c in cells))
            self.assertTrue(all(c['source']['pdf_page'] for c in cells))
        result=eps_answer('NAB diluted statutory EPS from continuing operations FY2025',{'banks':['NAB'],'years':[2025]},core)
        cells=[c['cell'] for p in result['answer']['parts'] for c in p['claims']]
        self.assertEqual([(c['metric'],c['scope']) for c in cells],[('diluted_statutory_eps','continuing')])

    def test_statutory_dilution_and_scope_are_literal(self):
        record={'row_label':'Statutory earnings per share - diluted (cents)',
                'label':'Group - Including discontinued operations / Statutory earnings per share - diluted (cents)',
                'body':'test', 'metric_tags':['basic_cash_eps'],'source':{'company':'NAB'}}
        page={'native_text':'Group performance results'}
        self.assertEqual(row_identity(record,'diluted_statutory_eps',page),('diluted statutory','including_discontinued'))
        self.assertIsNone(row_identity(record,'basic_statutory_eps',page))
        self.assertIsNone(row_identity(record,'diluted_cash_eps',page))
        self.assertIsNone(row_identity(record,'basic_cash_eps',page))

    def test_generic_eps_row_without_basis_is_not_assumed_statutory(self):
        record={'row_label':'Earnings per share (EPS) (diluted)',
                'label':'Earnings per share (EPS) (diluted)', 'body':'test',
                'metric_tags':['basic_cash_eps'],'source':{'company':'CBA'}}
        self.assertIsNone(row_identity(record,'diluted_statutory_eps',{'native_text':'Group'}))

    def test_every_eps_variant_has_a_human_readable_label(self):
        self.assertTrue(EPS_METRICS <= LABELS.keys())

    def test_percent_calculation_still_renders_percentage_points(self):
        from test_source_cells import cell
        from bank_operations_v9 import calculate
        calc=calculate([cell('1.99',2024,metric='nim',unit='percent'),
                        cell('2.08',2025,metric='nim',unit='percent')],
                       {'kind':'change','expense_magnitude':False,'relative_percent':True})
        result={'answer':{'parts':[{'calculations':[calc]}]}}
        text=paragraphs(result)[0]['text']
        self.assertIn('0.09 percentage points',text)
        self.assertNotIn('relative change is',text)


if __name__=='__main__': unittest.main()
