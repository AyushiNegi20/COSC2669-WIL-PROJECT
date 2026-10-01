import copy
import json
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_retrieval import (BM25, Retriever, covered_units, eligible_record, full_fragment,
                            plan_query, ranked, rrf, tokens, assemble_context, clean_search_question, search_representation)
from evaluate_bank_retrieval import evidence_scores, choose, ndcg


def record(key, bank='CBA', year=2025, text='cash profit', status='development_unreviewed', unit=None):
    return {'chunk_id':key,'kind':'table_rows','text':text,
            'source':{'company':bank,'report_year':year,'document_id':bank.lower()+str(year)[2:]},
            'quality':{'status':status},'fragments':[full_fragment(unit or key,text)],
            'parent_id':None,'related_chunk_ids':[],'anchors':[]}


class FakeTokenizer:
    def encode(self,text,truncation=False):
        if truncation:
            raise AssertionError('Silent truncation')
        return list(text)


class RetrievalTests(unittest.TestCase):
    def test_cleanup_preserves_financial_scope(self):
        text = clean_search_question('CBA FY2024 cash profit from continuing operations, as originally reported? Include the unit and reporting basis.')
        self.assertIn('cash profit from continuing operations', text)
        self.assertIn('FY2024', text)
        self.assertNotIn('Include', text)

    def test_cleanup_preserves_claim_numbers(self):
        self.assertIn('170', clean_search_question('Was NAB dividend per share 170 cents?'))

    def test_search_representation_uses_literal_spans(self):
        r = record('a', text='original')
        r['source']['document_title'] = 'Report'
        self.assertEqual(search_representation(r, {'a':'original'}), 'Report\noriginal')
        self.assertEqual(r['text'], 'original')

    def test_financial_plural_matching(self):
        self.assertEqual(tokens('dividends',normalise=True), tokens('dividend',normalise=True))

    def test_exact_financial_terms(self):
        model=BM25(['net interest margin','cash profit','statutory profit'])
        self.assertEqual(int(np.argmax(model.score('net interest margin'))),0)

    def test_abbreviation_expansion(self):
        self.assertIn('interest',tokens('NIM'))
        self.assertIn('statutory',tokens('statutory NPAT'))

    def test_no_cash_statutory_synonym(self):
        self.assertNotIn('statutory',tokens('cash earnings'))

    def test_missing_terms_zero(self):
        self.assertEqual(list(BM25(['cash profit']).score('xyz')), [0])

    def test_empty_corpus(self):
        self.assertEqual(len(BM25([]).score('profit')),0)

    def test_rrf_rewards_agreement(self):
        self.assertEqual(rrf([[0,1,2],[1,0,3]])[:2],[0,1])

    def test_rrf_deterministic_ties(self):
        self.assertEqual(rrf([[2],[1]]),[1,2])

    def test_company_alias(self):
        self.assertEqual(plan_query('National Australia Bank cash profit')['companies'],['NAB'])

    def test_company_comparison(self):
        self.assertEqual(plan_query('Compare CBA and NAB')['branches'],['CBA','NAB'])

    def test_value_year_not_report_filter(self):
        self.assertIsNone(plan_query('What was CBA FY2024 cash profit?')['report_year'])

    def test_original_report_filter(self):
        self.assertEqual(plan_query('What was CBA FY2024 cash profit as originally reported?')['report_year'],2024)

    def test_multiple_years_no_document_filter(self):
        self.assertIsNone(plan_query('Compare CBA FY2024 and FY2025 as originally reported')['report_year'])

    def test_annual_document_request(self):
        self.assertTrue(plan_query('NAB FY2025 annual report')['annual_report_only'])

    def test_ambiguous_profit(self):
        self.assertTrue(plan_query('How much did CBA profit grow?')['ambiguity'])

    def test_explicit_cash_not_ambiguous(self):
        self.assertIsNone(plan_query('CBA cash profit')['ambiguity'])

    def test_source_company_filter(self):
        rs=[record('a','CBA'),record('b','NAB')]
        out=Retriever(rs).search('NAB cash profit')
        self.assertEqual([r['chunk_id'] for r in out['hits']],['b'])

    def test_quarantine_always_excluded(self):
        rs=[record('a',status='quarantined'),record('b')]
        self.assertEqual([r['chunk_id'] for r in Retriever(rs).search('cash profit')['hits']],['b'])

    def test_validated_mode_denies_pending(self):
        self.assertFalse(eligible_record(record('a'),'validated_only'))

    def test_development_mode_allows_pending(self):
        self.assertTrue(eligible_record(record('a'),'development_unreviewed'))

    def test_comparison_round_robin(self):
        rs=[record(str(i),'CBA') for i in range(5)]+[record('n','NAB')]
        out=Retriever(rs).search('Compare CBA and NAB cash profit',final_k=2)
        self.assertEqual({r['source']['company'] for r in out['hits']},{'CBA','NAB'})

    def test_missing_dense_vectors_fails(self):
        with self.assertRaises(ValueError):
            Retriever([record('a')]).search('profit','dense')

    def test_dense_exact_search(self):
        rs=[record('a'),record('b')]
        out=Retriever(rs,np.eye(2)).search('profit','dense',np.array([0.,1.]))
        self.assertEqual(out['hits'][0]['chunk_id'],'b')

    def test_bm25_zero_matches_returns_empty(self):
        self.assertEqual(Retriever([record('a')]).search('xyz')['hits'],[])

    def test_partial_evidence_not_complete(self):
        r=record('a')
        r['fragments']=[{'unit':'u','start':0,'end':5,'length':10}]
        self.assertNotIn('u',covered_units([r]))

    def test_two_fragments_reconstruct(self):
        a,b=record('a'),record('b')
        a['fragments']=[{'unit':'u','start':0,'end':5,'length':10}]
        b['fragments']=[{'unit':'u','start':5,'end':10,'length':10}]
        self.assertIn('u',covered_units([a,b]))

    def test_gap_not_complete(self):
        a,b=record('a'),record('b')
        a['fragments']=[{'unit':'u','start':0,'end':4,'length':10}]
        b['fragments']=[{'unit':'u','start':5,'end':10,'length':10}]
        self.assertNotIn('u',covered_units([a,b]))

    def test_duplicate_fragment_no_extra_credit(self):
        a=record('a',unit='u')
        self.assertEqual(covered_units([a,a]),{'u'})

    def test_all_evidence_requires_both_years(self):
        q={'required_evidence_groups':[{'alternatives':[['y24']]},{'alternatives':[['y25']]}]}
        score=evidence_scores(q,[record('a',unit='y25')])
        self.assertEqual(score['hit'],1)
        self.assertEqual(score['evidence_recall'],.5)
        self.assertEqual(score['complete'],0)

    def test_header_required_with_row(self):
        q={'required_evidence_groups':[{'alternatives':[['row','header']]}]}
        self.assertEqual(evidence_scores(q,[record('a',unit='row')])['complete'],0)

    def test_alternative_evidence(self):
        q={'required_evidence_groups':[{'alternatives':[['a'],['b']]}]}
        self.assertEqual(evidence_scores(q,[record('x',unit='b')])['complete'],1)

    def test_unanswerable_not_in_denominator(self):
        self.assertIsNone(evidence_scores({'required_evidence_groups':[]},[])['complete'])

    def test_context_budget_no_truncation(self):
        out=assemble_context([record('a',text='x'*50)],{}, {},{},FakeTokenizer(),10)
        self.assertEqual(out['records'],[])
        self.assertEqual(out['omissions'][0]['reason'],'token_budget')

    def test_context_quarantine_no_bypass(self):
        r=record('a');r['parent_id']='p'
        p=record('p',status='quarantined')
        out=assemble_context([r],{'p':p},{},{},FakeTokenizer(),1000)
        self.assertEqual([x['chunk_id'] for x in out['records']],['a'])

    def test_context_duplicates(self):
        r=record('a')
        out=assemble_context([r,r],{},{},{},FakeTokenizer(),1000)
        self.assertEqual(len(out['records']),1)

    def test_parent_replaces_contained_child(self):
        r=record('a',text='123456789');r['parent_id']='p'
        p=record('p',text='parent with context')
        p['fragments']=r['fragments']+[full_fragment('extra','context')]
        out=assemble_context([r],{'p':p},{},{},FakeTokenizer(),20)
        self.assertEqual([x['chunk_id'] for x in out['records']],['p'])
        self.assertLessEqual(out['tokens'],20)

    def test_selection_prefers_complete_over_hit(self):
        base={'context_complete':.5,'context_evidence_recall':.8,'mrr_at_5':.9,'mean_search_seconds':.1}
        other={**base,'context_complete':.6,'mrr_at_5':.5}
        self.assertEqual(choose({'structured:bm25':base,'structured:dense':other}),'structured:dense')

    def test_selection_prefers_simple_tie(self):
        base={'context_complete':.5,'context_evidence_recall':.8,'mrr_at_5':.9,'mean_search_seconds':.1}
        self.assertEqual(choose({'structured:bm25':base,'structured:hybrid':base}),'structured:bm25')

    def test_ndcg_bounds(self):
        rs=[record('a'),record('b')]
        q={'required_evidence_groups':[{'alternatives':[['a']]}]}
        score=ndcg(q,rs,rs)
        self.assertGreaterEqual(score,0)
        self.assertLessEqual(score,1)

    def test_scores_not_answer_probability(self):
        out=Retriever([record('a')]).search('cash profit')
        self.assertEqual(out['evidence_sufficiency'],'not_established_by_retrieval_scores')


if __name__=='__main__':
    unittest.main()
