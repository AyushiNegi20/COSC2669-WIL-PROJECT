"""Runtime safeguards. Reference values belong in evaluation, not retrieval."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import bank_retrieval_v4 as v4
from bank_retrieval import covered_units


class CharacterTokenizer:
    def encode(self,text,truncation=False):
        assert not truncation
        return list(text)


class QueryPlanTests(unittest.TestCase):
    def test_full_company_name(self):
        self.assertEqual(v4.plan('Commonwealth Bank FY2025 net interest margin')['companies'],['CBA'])

    def test_named_report_not_comparative_year(self):
        p=v4.plan('In the CBA FY2025 report, compare cash profit with FY2024.')
        self.assertEqual(p['report_year'],2025)
        self.assertEqual(p['value_years'],[2024,2025])

    def test_original_vintages(self):
        p=v4.plan('Compare NAB FY2024 and FY2025 customer deposits as originally reported.')
        self.assertIsNone(p['report_year'])

    def test_ambiguous_profit(self):
        self.assertEqual(v4.plan('How much did CBA profit grow?')['behavior'],'clarify')

    def test_company_required(self):
        self.assertEqual(v4.plan('What were total assets in FY2025?')['behavior'],'clarify')

    def test_out_of_scope(self):
        for question in ['Westpac FY2025 cash profit','NAB FY2028 cash profit','What is my CBA account balance?']:
            with self.subTest(question=question):
                self.assertEqual(v4.plan(question)['behavior'],'abstain')

    def test_definition_term(self):
        self.assertEqual(v4.plan('According to NAB FY2025, what does cash earnings mean?')['definition_term'],'cash earnings')

    def test_distinct_metrics(self):
        self.assertEqual(v4.metrics('cash earnings'),['cash_profit'])
        self.assertEqual(v4.metrics('statutory net profit'),['statutory_npat'])
        self.assertEqual(v4.metrics('cash earnings per share'),['basic_cash_eps'])
        self.assertEqual(v4.metrics('CET1 capital ratio'),['cet1'])


class SourceViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (Path(__file__).resolve().parents[1]/'data/processed/banking_chunks_v1/children.jsonl').exists():
            raise unittest.SkipTest('Requires the generated local corpus; see docs/SETUP.md')
        cls.records,cls.units=v4.build_view()
        cls.engine=v4.EvidenceRetriever(cls.records,cls.units)

    def test_all_fragments_are_complete_literal_units(self):
        for r in self.records:
            self.assertEqual(set(r['unit_ids']),covered_units([r]))
            self.assertEqual(r['body'],'\n'.join(self.units[u] for u in r['unit_ids']))

    def test_financial_rows_keep_headers_and_dependencies(self):
        rows=[r for r in self.records if r['kind']=='financial_row']
        self.assertTrue(rows)
        for r in rows:
            own=f"{r['table_id']}:r{r['row']}"
            self.assertIn(own,r['unit_ids'])
            self.assertNotIn(own,r['dependency_units'])
            self.assertTrue(set(r['dependency_units'])<=set(r['unit_ids']))

    def test_glossary_continuation(self):
        target=[r for r in self.records if 'nab25:p083:b036' in r['unit_ids']]
        self.assertTrue(target)
        self.assertTrue(all(r['kind']=='definition' for r in target))

    def test_no_standalone_headers(self):
        _,pages=v4.source_units()
        blocks={b['id']:b for p in pages.values() for b in p['blocks']}
        for r in self.records:
            if r['kind']=='financial_row' or 'table_id' in r:
                continue
            self.assertTrue(any(blocks[u]['type'] not in ('section_header','page_header','page_footer','caption') for u in r['unit_ids']))

    def test_no_quarantined_or_calculation_ready(self):
        for r in self.records:
            self.assertNotEqual(r['quality']['status'],'quarantined')
            self.assertFalse(r['quality']['calculation_ready'])

    def test_company_and_report_filters(self):
        result=self.engine.search('NAB FY2024 report customer deposits')
        self.assertTrue(result['records'])
        self.assertTrue(all(r['source']['company']=='NAB' and r['source']['report_year']==2024 for r in result['records']))

    def test_clarification_has_no_evidence(self):
        self.assertEqual(self.engine.search('How much did profit grow?')['records'],[])

    def test_reconciliation_preserves_bridge(self):
        result=self.engine.search('NAB FY2025 report: reconcile cash earnings with statutory net profit and non-cash adjustments.')
        rows=result['records']
        self.assertTrue(rows)
        self.assertEqual(len({r['table_id'] for r in rows}),1)
        self.assertTrue(any('cash_profit' in r['metric_tags'] for r in rows))
        self.assertTrue(any('statutory_npat' in r['metric_tags'] for r in rows))
        self.assertTrue(any('hedging' in r['row_label'].lower() for r in rows))

    def test_restatement_neighbors(self):
        result=self.engine.search('Why are NAB FY2024 comparatives different in FY2025? Find the reclassification and amount.')
        covered=covered_units(result['records'])
        self.assertTrue({'nab_ar25:p156:b021','nab_ar25:p156:b022','nab_ar25:p156:b023'}<=covered)

    def test_context_budget_never_truncates_units(self):
        result=self.engine.search('NAB FY2025 report customer deposits')
        context=self.engine.context(result,CharacterTokenizer(),budget=800)
        self.assertLessEqual(context['tokens'],800)
        for r in context['records']:
            for u in r['unit_ids']:
                self.assertIn('['+u+'] '+self.units[u],context['text'])

    def test_headers_deduplicated(self):
        result=self.engine.search('NAB FY2025 report total assets and customer deposits')
        text=self.engine.render(result['records'])
        for r in result['records']:
            for u in r['unit_ids']:
                self.assertEqual(text.count('['+u+']'),1)

    def test_quarantine_filter_also_aligns_vectors(self):
        rows=copy.deepcopy(self.records[:2])
        rows[0]['quality']['status']='quarantined'
        engine=v4.EvidenceRetriever(rows,self.units,np.eye(2))
        self.assertEqual(len(engine.records),1)
        np.testing.assert_array_equal(engine.vectors,np.array([[0.,1.]]))

    def test_no_runtime_gold_or_fixed_page_maps(self):
        source=Path(v4.__file__).read_text(encoding='utf-8')
        for forbidden in ['metric_scope_13.json','reference.json','required_evidence_groups','expected_answer','bank-q0','nab25:p0','cba25:p0']:
            self.assertNotIn(forbidden,source)


class CacheTests(unittest.TestCase):
    def test_corrupt_cache_rejected(self):
        class FakeEncoder:
            def __init__(self,*args): pass
            def encode(self,texts,query=False): return np.ones((len(texts),2))
        with tempfile.TemporaryDirectory() as tmp, patch.object(v4,'OUT4',Path(tmp)), patch.object(v4,'Encoder',FakeEncoder), patch.object(v4,'execution_profile',return_value={'test':True}):
            v4.embedding_cache(['hello'])
            cache=next(Path(tmp).glob('*.npz'))
            cache.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'integrity'):
                v4.embedding_cache(['hello'])

    def test_query_document_caches_distinct(self):
        class FakeEncoder:
            def __init__(self,*args): pass
            def encode(self,texts,query=False): return np.ones((len(texts),2))
        with tempfile.TemporaryDirectory() as tmp, patch.object(v4,'OUT4',Path(tmp)), patch.object(v4,'Encoder',FakeEncoder), patch.object(v4,'execution_profile',return_value={'test':True}):
            v4.embedding_cache(['hello'],query=False)
            v4.embedding_cache(['hello'],query=True)
            self.assertEqual(len(list(Path(tmp).glob('*.npz'))),2)


if __name__=='__main__': unittest.main()
