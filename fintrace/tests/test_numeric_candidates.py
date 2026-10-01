"""Structural candidate coverage does not weaken the source-cell binder."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from answer_bank_v9 import Backend


class CandidateTests(unittest.TestCase):
    def test_all_matching_rows_not_just_ranked_top_k(self):
        def row(key, bank='CBA', metric='cash_profit', kind='financial_row'):
            return {'chunk_id': key, 'source': {'company': bank}, 'metric_tags': [metric], 'kind': kind}
        backend = Backend.__new__(Backend)
        backend.retriever = SimpleNamespace(engine=SimpleNamespace(records=[
            row('b'), row('a'), row('other_bank', bank='NAB'),
            row('other_metric', metric='gross_loans'), row('prose', kind='passage')]))
        request = {'id': 'q', 'company': 'CBA', 'metric': 'cash_profit'}
        context = {'records': [row('b')], 'request_coverage': {'q': {'included_ids': ['b']}}}
        self.assertEqual([r['chunk_id'] for r in backend.numerical_records(context, request)], ['a', 'b'])

    def test_no_index_retains_existing_context_contract(self):
        backend = Backend.__new__(Backend)
        backend.retriever = SimpleNamespace(engine=None)
        context = {'records': [{'chunk_id': 'a'}, {'chunk_id': 'b'}],
                   'request_coverage': {'q': {'included_ids': ['b']}}}
        self.assertEqual(backend.numerical_records(context, {'id': 'q'}), [{'chunk_id': 'b'}])


if __name__ == '__main__': unittest.main()
