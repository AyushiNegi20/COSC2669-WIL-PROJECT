from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_operations_v9 import operation_plan,finish_plan,calculate,presentation
from bank_source_cells import BoundCell
from bank_retrieval_v7 import plan_question
from answer_bank_v9 import Backend,display


def cell(value='100',year=2024,**changes):
    fields=dict(metric='cash_profit',company='CBA',value=value,raw_value=value,unit='AUD million',
        basis='cash',scope='continuing',period_kind='annual',period_end=f'{year}-06-30',report_year=2025,
        column=1,source_id='fixture:r1',header_ids=('fixture:r0',),record_id='fixture',
        source={'document_title':'Synthetic fixture','pdf_page':1},row_quote='Synthetic fixture value')
    fields.update(changes);return BoundCell(**fields)


class OperationTests(unittest.TestCase):
    def test_chronological_arithmetic_not_refused(self):
        for q in ['CBA FY2025-minus-FY2024 cash profit','CBA cash profit later-minus-earlier',
                  'CBA cash profit: subtract FY2024 from FY2025']:
            op=operation_plan(q);self.assertEqual(op['kind'],'year_difference')
            self.assertEqual(calculate([cell('100'),cell('110',2025)],op)['absolute_change'],'10')

    def test_reverse_arithmetic_preserves_order(self):
        for q in ['CBA FY2024 cash profit minus FY2025 cash profit',
                  'CBA cash profit: subtract FY2025 from FY2024',
                  'CBA cash profit earlier minus later']:
            result=calculate([cell('100'),cell('110',2025)],operation_plan(q))
            self.assertEqual(result['absolute_change'],'-10')
            self.assertTrue(result['operand_labels'][0].endswith('2024-06-30'))

    def test_wrong_or_same_requested_years_not_substituted(self):
        for years in [[2025,2025],[2023,2024]]:
            with self.assertRaises(ValueError):
                calculate([cell(),cell('110',2025)],{'kind':'year_difference','order':years,'expense_magnitude':False,'relative_percent':False})

    def test_expense_magnitude_preserves_raw_negative(self):
        first=cell('-100',metric='operating_expenses');last=cell('-110',2025,metric='operating_expenses')
        op=operation_plan('Calculate increase in CBA operating expenses FY2024 and FY2025')
        result=calculate([first,last],op)
        self.assertEqual(result['absolute_change'],'10')
        self.assertEqual(result['source_signed_difference'],'-10')
        self.assertEqual(result['source_cells'][0]['value'],'-110')
        self.assertEqual(presentation(last,op)['value'],'110')
        self.assertIn('deduction',presentation(last,op)['note'])

    def test_explicit_source_signed_difference_preserved(self):
        op=operation_plan('Calculate the source-signed change in CBA operating expenses FY2024 and FY2025')
        result=calculate([cell('-100',metric='operating_expenses'),cell('-110',2025,metric='operating_expenses')],op)
        self.assertEqual(result['absolute_change'],'-10')

    def test_income_is_not_absolute_valued(self):
        op=operation_plan('Calculate the increase in operating income FY2024 and FY2025')
        result=calculate([cell('-100',metric='operating_income'),cell('-80',2025,metric='operating_income')],op)
        self.assertEqual(result['absolute_change'],'20')
        self.assertEqual(result['left'],'-80')

    def test_credit_recovery_sign_flip_not_hidden(self):
        op=operation_plan('Calculate increase in credit impairment FY2024 and FY2025')
        with self.assertRaises(ValueError):
            calculate([cell('-100',metric='credit_impairment'),cell('10',2025,metric='credit_impairment')],op)

    def test_percentages_become_basis_points(self):
        op=operation_plan('CBA FY2025 minus FY2024 CET1 ratio, not percent growth')
        result=calculate([cell('12.3',metric='cet1',unit='percent'),cell('11.8',2025,metric='cet1',unit='percent')],op)
        self.assertEqual(Decimal(result['basis_points']),Decimal('-50'))
        self.assertNotIn('relative_change_percent',result)

    def test_no_extra_relative_percentage_when_excluded(self):
        result=calculate([cell('100'),cell('110',2025)],operation_plan('CBA FY2025 minus FY2024 cash profit, not a percentage'))
        self.assertNotIn('relative_change_percent',result)

    def test_relative_percentage_when_requested(self):
        result=calculate([cell('100'),cell('110',2025)],operation_plan('Calculate CBA cash profit percentage change FY2024 to FY2025'))
        self.assertEqual(Decimal(result['relative_change_percent']),Decimal('10'))

    def test_compatible_fields_enforced(self):
        op=operation_plan('Calculate CBA cash profit change FY2024 and FY2025')
        for changes in [{'company':'NAB'},{'scope':'including_discontinued'},{'unit':'AUD billion'},
                        {'report_year':2024},{'basis':'statutory'},{'period_kind':'half_year'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                calculate([cell(),cell('110',2025,**changes)],op)

    def test_same_period_profit_gap_named_exception(self):
        op=operation_plan('CBA FY2025 continuing operations only: quantify cash profit minus statutory profit')
        statutory=cell('95',2025,metric='statutory_npat',basis='statutory')
        result=calculate([cell('100',2025),statutory],op)
        self.assertEqual(result['absolute_change'],'5')
        self.assertIn('not an explanation',result['note'])

    def test_profit_gap_rejects_period_scope_currency_vintage(self):
        op=operation_plan('CBA FY2025 cash profit minus statutory profit')
        stat=cell('95',2025,metric='statutory_npat',basis='statutory')
        for changes in [{'period_end':'2024-06-30'},{'scope':'including_discontinued'},
                        {'report_year':2024},{'unit':'AUD billion'},{'company':'NAB'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                calculate([cell('100',2025),replace(stat,**changes)],op)

    def test_global_scope_reaches_both_metrics(self):
        q='For CBA FY2025 continuing operations only, quantify cash profit minus statutory profit.'
        p=finish_plan(q,plan_question(q))
        self.assertEqual({r['scope'] for r in p['requests']},{'continuing'})
        self.assertEqual({r['metric'] for r in p['requests']},{'cash_profit','statutory_npat'})

    def test_explicit_mixed_scopes_not_overwritten(self):
        q='CBA FY2025: give cash profit from continuing operations and statutory profit including discontinued operations.'
        p=finish_plan(q,plan_question(q))
        self.assertEqual({r['scope'] for r in p['requests']},{'continuing','including_discontinued'})

    def test_dividend_increase_is_operation(self):
        for q in ['CBA dividends FY2024/FY2025: work out the increase in cents',
                  'CBA dividend per share FY2024/FY2025: how much did it grow?']:
            self.assertEqual(operation_plan(q)['kind'],'change')

    def test_explanation_does_not_become_arithmetic(self):
        self.assertEqual(operation_plan('Why did CBA expenses increase in FY2025?')['kind'],'none')

    def test_unsupported_and_ambiguous_calculations_withheld(self):
        for q in ['Subtract CET1 ratio from total Group assets for NAB FY2025',
                  'Give ratio of CBA cash profit FY2024 to FY2025','Convert NAB assets to USD',
                  'CBA cash profit minus the other number']:
            self.assertEqual(operation_plan(q)['kind'],'unsupported')

    def test_missing_calculation_is_not_complete(self):
        q='Calculate CBA cash profit change FY2024 and FY2025'
        p=finish_plan(q,plan_question(q))
        class Retriever:
            def retrieve(self,q):
                return p,{'records':[],'request_coverage':{r['id']:{'included_ids':[]} for r in p['requests']},'tokens':0,'omissions':[]}
        class Binder:
            units={'fixture:r1':'Synthetic fixture value','fixture:r0':'Date header'}
            def select(self,*args): return [cell('100')],[]
        b=object.__new__(Backend);b.retriever=Retriever();b.binder=Binder()
        answer=b.answer(q)['answer']
        self.assertEqual(answer['status'],'partial_answer')
        self.assertEqual(answer['calculation_coverage'],{'required':1,'completed':0})

    def test_cli_shows_prose_limitations(self):
        shown=display({'answer':{'status':'evidence_answer','limitations':['Coverage is not certified.']}})
        self.assertIn('Coverage is not certified.',shown)

    def test_cli_change_of_percentage_is_not_percent_growth(self):
        calc=calculate([cell('12.3',unit='percent'),cell('11.8',2025,unit='percent')],
                       operation_plan('CBA FY2025 minus FY2024 cash profit'))
        shown=display({'answer':{'status':'source_bound_answer','parts':[{'claims':[],'calculations':[calc],'issues':[]}]}})
        self.assertIn('= -0.5 percentage points',shown)
        self.assertNotIn('= -0.5 percent.',shown)

    def test_no_answer_keys_in_v9_runtime(self):
        for name in ['bank_operations_v9.py','answer_bank_v9.py','bank_retrieval_service_v9.py']:
            text=(Path(__file__).resolve().parents[1]/'scripts'/name).read_text()
            for prohibited in ['metric_scope_13.json','fresh_agent_v3','10252','10253','reference.json']:
                self.assertNotIn(prohibited,text)


if __name__=='__main__': unittest.main()
