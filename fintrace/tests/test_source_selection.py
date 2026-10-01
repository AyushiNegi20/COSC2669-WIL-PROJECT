"""Synthetic checks for source selection; no finance answer key or API calls."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_generation_v11 import evidence_cards
from bank_source_selection import source_passages,validate_selection,render_selected_sources
from test_generation_frozen_improvements import evidence


class SourceSelectionTests(unittest.TestCase):
    def setup_example(self):
        e=evidence('Personnel costs increased due to salary inflation, partly offset by productivity savings.')
        c=Mock();c.config={'model':'fixture','research_mode':'source_selection'}
        c.chat.return_value=({'passage_ids':['P1']},{})
        return e,c,evidence_cards(e['answer'])

    def test_quotes_remain_whole_including_offsets(self):
        e,c,cards=self.setup_example();original=deepcopy(e)
        r=render_selected_sources(e,c,cards)
        text=r['answer']['generated_explanation']['statements'][0]['text']
        self.assertIn(cards[0]['content']['text'],text)
        self.assertEqual(r['generation']['status'],'source_selected')
        self.assertEqual(e,original)
        self.assertEqual(c.chat.call_count,1)
        self.assertEqual(c.chat.call_args.args[-1],160)

    def test_no_model_written_connection_or_number_can_be_injected(self):
        e,c,cards=self.setup_example()
        c.chat.return_value=({'passage_ids':['P1'],'text':'Staff savings caused lending growth of 42.'},{})
        r=render_selected_sources(e,c,cards)
        self.assertEqual(r['generation']['status'],'fallback')
        self.assertNotIn('42',r['answer']['message'])

    def test_unknown_duplicate_and_nonstring_ids_fail(self):
        e,c,cards=self.setup_example();p=source_passages(cards)
        for ids in (['P99'],['P1','P1'],[{}],None):
            with self.assertRaises(ValueError):validate_selection({'passage_ids':ids},p)

    def test_tampered_literal_fails_even_when_model_approves(self):
        e,c,cards=self.setup_example();p=source_passages(cards);p[0]['text']='Different subject.'
        with self.assertRaises(ValueError):validate_selection({'passage_ids':['P1']},p)

    def test_empty_selection_honestly_has_no_answer(self):
        e,c,cards=self.setup_example();c.chat.return_value=({'passage_ids':[]},{})
        r=render_selected_sources(e,c,cards)
        self.assertEqual(r['answer']['status'],'unable_to_verify')
        self.assertEqual(r['answer']['source_excerpts'],[])
        self.assertIn('does not mean',r['answer']['message'])

    def test_timeout_preserves_fallback_and_has_no_hidden_retry(self):
        e,c,cards=self.setup_example();c.chat.side_effect=TimeoutError('fixture timeout')
        r=render_selected_sources(e,c,cards)
        self.assertEqual(r['generation']['status'],'fallback')
        self.assertIn('not a verified answer',r['answer']['message'])
        self.assertEqual(c.chat.call_count,1)

    def test_missing_requested_year_is_visible(self):
        e,c,cards=self.setup_example();e['research_coverage'].append({'company':'NAB','year':2024})
        r=render_selected_sources(e,c,cards)
        self.assertEqual(r['generation']['missing_scopes'],[('NAB',2024)])
        self.assertIn('NAB FY2024',' '.join(r['answer']['important_notes']))

    def test_selected_citation_is_the_matching_block_not_neighbours(self):
        e,c,cards=self.setup_example()
        cards[0]['citations'].append({**deepcopy(cards[0]['citations'][0]),'source_id':'other',
            'quote':'Total operating costs declined due to lower business acquisition and closure costs.'})
        c.chat.return_value=({'passage_ids':['P1']},{})
        r=render_selected_sources(e,c,cards)
        self.assertNotIn('acquisition',str(r['answer']['generated_explanation']))
        self.assertEqual(r['answer']['source_excerpts'][0]['excerpts'][0]['source_id'],'source')

if __name__=='__main__':unittest.main()
