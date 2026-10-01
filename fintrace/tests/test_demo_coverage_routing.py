"""General routing and source-contract regressions, not a blind accuracy set."""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from answer_bank_simplified import Backend, is_reasoning_request
from bank_statement_tables import parse_table, parse_segment, ROWS, EPS_ROWS, SEGMENT_ROWS, requested_metrics, answer
from bank_query_routing import explanation_subject
from bank_narrative_routing import relevant_sections, narrative_evidence, narrative_decision
from bank_report_library import nab_blocks
from bank_conversation import paragraphs


class CoverageRoutingTests(unittest.TestCase):
    def test_change_requests_do_not_go_to_prose(self):
        for bank in ('CBA','NAB'):
            for measure in ('cash profit','net interest margin','CET1 capital ratio','customer deposits'):
                q=f'How did {bank} {measure} change from FY2024 to FY2025?'
                self.assertFalse(is_reasoning_request(q),q)
                evidence=Mock(); evidence.answer.return_value={'answer':{'status':'source_bound_answer','parts':[]}}
                client=Mock()
                result=Backend(evidence,client).answer(q)
                evidence.answer.assert_called_once_with(q)
                client.chat.assert_not_called()
                self.assertEqual(result['generation']['status'],'skipped')

    def test_why_is_still_prose(self):
        self.assertTrue(is_reasoning_request('Why did NAB operating expenses increase in FY2025?'))
        self.assertIsNotNone(explanation_subject('Explain the drivers of CBA operating expenses.'))

    def test_metric_driver_not_an_incidental_mention(self):
        good={'source':{'company':'NAB','report_year':2025},'heading':'Annual','excerpts':[
            {'source_id':'good','quote':'Operating expenses increased due to wages, offset by productivity.'}]}
        bad={**good,'excerpts':[{'source_id':'bad','quote':'Net profit increased despite higher operating expenses.'}]}
        d={'topic':'general','company':'NAB','year':2025}
        self.assertEqual(relevant_sections([bad,good],d,'Why did NAB operating expenses increase?'),[good])

    def test_explanation_keeps_the_checked_source_report(self):
        q='Why did NAB credit impairment charge increase in FY2025?'
        decision=narrative_decision(q,topic_hint='general')
        decision['source_documents']=['checked-cash-report']
        sections=[{'source':{'company':'NAB','report_year':2025,'document_id':doc,'pdf_page':1},
                   'heading':'Group', 'excerpts':[{'source_id':doc,
                    'quote':'Credit impairment charge increased due to higher individual charges.'}]}
                  for doc in ('other-statutory-report','checked-cash-report')]
        result=narrative_evidence(q,decision,Mock(),full_search=lambda *a,**kw:sections)
        self.assertEqual([s['source']['document_id'] for s in result['answer']['source_excerpts']],
                         ['checked-cash-report'])

    def test_statutory_explanation_checks_new_statement_path_first(self):
        from answer_bank_conversational import Backend as ConversationalBackend
        core=Mock()
        core.research.return_value={'answer':{'status':'partial_answer','source_excerpts':[]}}
        backend=ConversationalBackend(core);backend.use_cba_reports=True
        cells=[{'metric':'statutory_operating_expenses','basis':'statutory',
                'period_end':f'{y}-09-30','source':{'document_id':'annual'}} for y in (2025,2024)]
        checked={'answer':{'parts':[{'calculations':[{'absolute_change':'5','source_cells':cells}]}]}}
        with patch('bank_statement_tables.answer',return_value=checked):
            result=backend.check_directional_premise('Why did NAB statutory operating expenses increase in FY2025?')
        core.answer.assert_not_called()
        self.assertEqual(core.research.call_args.kwargs['source_documents'],{'annual'})
        self.assertIn('statutory reporting basis',core.research.call_args.args[0])
        self.assertTrue(result['premise_check'][0]['matches_question'])

    def test_cross_column_sentence_keeps_driver_and_offset(self):
        page=Mock();page.rect.width=600;page.rect.height=850;page.number=0
        first=(40,700,280,745,'Credit impairment charge increased due to higher individual charges in business lending. This',0,0)
        second=(310,100,550,120,'was partially offset by lower collective charges.',1,0)
        page.get_text.return_value=[first,second]
        blocks,_,_=nab_blocks(page,{'id':'synthetic'})
        self.assertEqual(len(blocks),1)
        self.assertIn('This was partially offset',blocks[0]['quote'])
        self.assertEqual(len(blocks[0]['component_source_ids']),2)

    def test_distinct_measures_are_not_statement_aliases(self):
        for q in ('NAB cash net interest income FY2025','NAB underlying profit FY2025',
                  'Why did NAB statutory operating income increase?'):
            self.assertEqual(requested_metrics(q),[])

    def test_basic_and_diluted_statutory_eps_are_both_requested(self):
        self.assertEqual(requested_metrics('NAB basic and diluted statutory EPS FY2025'),
                         ['basic_statutory_eps','diluted_statutory_eps'])

    def test_eps_answer_entry_does_not_misread_earnings_as_npat(self):
        table={'source':{'document_id':'synthetic','pdf_page':1,'report_year':2025},
               'years':[2025,2024], 'unit':'cents/share', 'kind':'eps',
               'rows':{'basic_statutory_eps':['120.1','110.2'],
                       'diluted_statutory_eps':['119.5','109.4']}}
        with patch('bank_statement_tables.tables',return_value=[table]):
            for wording in ('EPS','earnings per share'):
                result=answer(f'What were NAB FY2025 basic and diluted statutory {wording}?',
                              {'banks':['NAB'],'years':[2025]})
                self.assertIsNotNone(result)
                self.assertEqual([p['claims'][0]['cell']['value'] for p in result['answer']['parts']],
                                 ['120.1','119.5'])
            for measure in ('statutory profit','customer deposits'):
                self.assertIsNone(answer(f'NAB FY2025 basic statutory earnings per share and {measure}',
                                         {'banks':['NAB'],'years':[2025]}))


class StatementParsingTests(unittest.TestCase):
    def fixture(self):
        values=[(100,90),(20,10),(120,100),(-40,-40),(-10,-5),(70,55),(-20,-15),
                (50,40),(-5,-3),(45,37),(2,1),(43,36)]
        return 'Financial performance\nGroup\n2025 2024\n$m $m\n'+'\n'.join(
            label+' '+str(a)+' '+str(b) for label,(a,b) in zip(ROWS.values(),values))

    def test_all_five_accounting_identities_reconcile(self):
        years,rows=parse_table(self.fixture(),self.fixture(),'performance')
        self.assertEqual(years,[2025,2024]);self.assertEqual(rows['statutory_total_profit'],['45','37'])

    def test_disagreement_fails_closed(self):
        with self.assertRaises(ValueError):parse_table(self.fixture(),self.fixture().replace('100 90','101 90'),'performance')

    def test_equal_extraction_with_bad_totals_still_fails(self):
        broken=self.fixture().replace('100 90','101 90')
        with self.assertRaises(ValueError):parse_table(broken,broken,'performance')

    def test_wrong_unit_or_company_headers_fail(self):
        for value in (self.fixture().replace('$m','$bn'),self.fixture().replace('Group','Company'),
                      self.fixture().replace('2025 2024','2024 2025')):
            with self.assertRaises(ValueError):parse_table(value,value,'performance')

    def test_eps_needs_exact_statutory_labels_and_years(self):
        text='5 Year Key Performance Indicators\nGroup\n2025 2024 2023 2022 2021\n'
        text+='\n'.join(label+' 120.1 110.2 100.3 90.4 80.5' for label in EPS_ROWS.values())
        self.assertEqual(parse_table(text,text,'eps')[1]['basic_statutory_eps'][0],'120.1')
        with self.assertRaises(ValueError):parse_table(text.replace('Statutory','Cash'),text,'eps')

    def segment_fixture(self):
        values={'underlying_profit':40,'cash_earnings':30,'hedging_adjustment':1,
                'other_non_cash_adjustments':-1,'continuing_owners_profit':30,
                'discontinued_owners_loss':-1,'statutory_owners_profit':29}
        header='Segment information\n2025\nBusiness and Private Banking Personal Banking Corporate and Institutional Banking New Zealand Banking Corporate Functions and Other Total Group\n'
        return header+'$m '*6+'\nReportable segment information\n'+'\n'.join(
            label+' '+' '.join([str(values[k])]*5+[str(values[k]*5)]) for k,label in SEGMENT_ROWS.items())

    def test_segment_totals_and_reconciliation(self):
        year,rows=parse_segment(self.segment_fixture(),self.segment_fixture())
        self.assertEqual(year,2025);self.assertEqual(rows['statutory_owners_profit'],'145')

    def test_segment_group_column_is_required(self):
        bad=self.segment_fixture().replace('Total Group','Parent Company')
        with self.assertRaises(ValueError):parse_segment(bad,bad)

    def test_consistent_row_totals_do_not_override_failed_reconciliation(self):
        bad=self.segment_fixture().replace('29 29 29 29 29 145','28 28 28 28 28 140')
        with self.assertRaises(ValueError):parse_segment(bad,bad)

    def test_parent_company_and_explicit_note_are_not_group_substitutes(self):
        for q in ('NAB parent company statutory net interest income FY2025',
                  'NAB income tax expense in Note 6 for FY2025',
                  'NAB Business and Private Banking statutory net interest income FY2025',
                  'NAB underlying profit and customer deposits FY2025',
                  'NAB statutory net interest income and customer deposits FY2025'):
            self.assertIsNone(answer(q,{'banks':['NAB'],'years':[2025]}))


if __name__=='__main__': unittest.main()
