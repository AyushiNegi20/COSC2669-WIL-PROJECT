import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_conversational_intent import validate, table_allowed, IntentPlanner
from bank_narrative_routing import narrative_decision
from cba_investment_answer import answer
from test_cba_reports import fixture
from types import SimpleNamespace


def plan(subject, topic='investment'):
    return dict(topic=topic, task='figures', subject=subject, specific_amount=False, advice=False)


class IntentTests(unittest.TestCase):
    def test_model_cannot_invent_subject(self):
        with self.assertRaises(ValueError): validate(plan('total lending'), 'Where is mortgage lending growing?')

    def test_model_cannot_provide_values_or_rewrite_question(self):
        for field in ('value','answer','rewritten_question'):
            with self.assertRaises(ValueError): validate({**plan('spending'),field:'100'},'CBA spending')

    def test_strict_boolean_flags(self):
        with self.assertRaises(ValueError): validate({**plan('money'),'advice':'false'},'money')

    def test_table_vetoes_distinct_concepts_even_when_model_wrong(self):
        for q in ('IT expenses','staff costs','mortgage lending','investment by industry',
                  'investment in shares','capitalised software','half-year investment'):
            p=validate(plan(q),q)
            if q=='capitalised software': continue  # Exclusions run before the planner.
            self.assertFalse(table_allowed(q,{'banks':['CBA']},{**p,'status':'interpreted'}),q)

    def test_tool_choice_generalises_without_rewriting_original(self):
        for q in ('Where is CBA putting more money?', 'Where did CBA direct its investment budget?',
                  'Which part of its own business got a bigger allocation?'):
            p={**validate(plan(q),q),'status':'interpreted'}
            ctx={'banks':['CBA'],'years':[2025],'defaults':[]}
            result=answer(q,ctx,SimpleNamespace(data={'investment_tables':[fixture()]}),p)
            self.assertEqual(result['question'],q)
            self.assertEqual(result['route'],'numeric')

    def test_nab_cannot_use_cba_table(self):
        self.assertFalse(table_allowed('investment',{'banks':['NAB']},{**plan('investment'),'status':'interpreted'}))

    def test_topic_does_not_override_explanation_task(self):
        for task in ('definition','explanation','causality','unsupported'):
            self.assertFalse(table_allowed('CBA investment',{'banks':['CBA']},
                {**plan('investment'),'task':task,'status':'interpreted'}))

    def test_narrative_hint_preserves_original_query(self):
        question='What stands out about CBA FY2025?'
        result=narrative_decision(question,topic_hint='performance')
        self.assertEqual(result['topic'],'performance')
        self.assertEqual(result['question'],question)
        self.assertIn(question,result['requests'][0]['followup'])

    def test_model_failure_has_visible_offline_fallback(self):
        class Broken:
            def request(self,*args): raise OSError('Offline')
        result=IntentPlanner(Broken()).plan('Where does the budget go?')
        self.assertEqual(result['status'],'fallback')
        self.assertEqual(result['topic'],'existing')

    def test_advice_never_uses_table(self):
        self.assertFalse(table_allowed('Should I invest in CBA?',{'banks':['CBA']},
                                      {**plan('invest'),'status':'interpreted'}))

    def test_period_and_prediction_do_not_reach_core(self):
        from answer_bank_conversational import Backend
        class NoCall:
            def answer(self,q): raise AssertionError('No annual substitution allowed')
        for q in ('CBA investment in the six months ended June 2025',
                  'Does CBA investment prove profit will keep rising in FY2025?'):
            result=Backend(core=NoCall()).answer(q)
            self.assertEqual(result['answer']['status'],'unable_to_verify')

    def test_payback_not_spending_ranking(self):
        from answer_bank_conversational import Backend
        result=Backend(core=object()).answer('Which CBA project paid back fastest in FY2025?')
        self.assertEqual(result['answer']['status'],'unable_to_verify')
        self.assertIn('benefits and timing',result['answer']['message'])

    def test_budget_share_is_not_stock_shares(self):
        p={**plan('investment'),'status':'interpreted'}
        self.assertTrue(table_allowed('share of CBA investment',{'banks':['CBA']},p))
        self.assertFalse(table_allowed('CBA investment in shares',{'banks':['CBA']},p))

    def test_narrative_numeric_claim_does_not_receive_generated_endorsement(self):
        from bank_research_answer import render_research
        from unittest.mock import Mock
        source={'company':'CBA','report_year':2025,'document_id':'synthetic','document_title':'Synthetic','pdf_page':1}
        evidence={'question':'Was the extra 123 million all spent on AI?',
          'answer':{'status':'partial_answer','source_excerpts':[{'source':source,'heading':'Staff expenses',
             'excerpts':[{'source_id':'s1','quote':'Staff expenses increased with wage inflation and additional frontline employees.'}]}]},
          'narrative_request':{'topic':'spending'}}
        client=Mock();client.config={'model':'fake'}
        result=render_research(evidence,client)
        client.generate_research.assert_not_called()
        self.assertEqual(result['generation']['status'],'fallback')
        self.assertIn('not verification',result['answer']['important_notes'][0])

if __name__=='__main__': unittest.main()
