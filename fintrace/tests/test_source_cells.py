from dataclasses import replace
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_source_cells import BoundCell,CellBinder,column_date,calculate_change,period_restriction


def cell(value='100',year=2024,**kw):
    fields=dict(metric='cash_profit',company='CBA',value=value,raw_value=value,unit='AUD million',
        basis='cash',scope='continuing',period_kind='annual',period_end=f'{year}-06-30',report_year=2025,
        column=1,source_id='example:r2',header_ids=('example:r0',),record_id='example',source={},row_quote='Cash profit | '+value)
    fields.update(kw);return BoundCell(**fields)


class BindingTests(unittest.TestCase):
    def test_unsupported_ordered_arithmetic_is_declined(self):
        from answer_bank_v8 import unsupported_operation
        for q in ['CBA FY2024 cash profit minus FY2025 cash profit','ratio of CBA FY2024 cash profit to FY2025 cash profit','convert assets to USD']:
            self.assertIsNotNone(unsupported_operation(q))
        self.assertIsNone(unsupported_operation('Compare CBA cash profit FY2024 and FY2025 and calculate percentage change'))

    def test_requested_date_is_not_silently_replaced(self):
        for q in ['CBA total assets at 31 December 2024','CBA assets at 2024-12-31','CBA cash profit H1 2025','CBA assets 29 June 2025']:
            self.assertIsNotNone(period_restriction(q,'CBA'))
        self.assertIsNone(period_restriction('CBA assets June 2024 and June 2025','CBA'))

    def test_expense_component_is_not_total(self):
        if not (Path(__file__).resolve().parents[1]/'data/processed/banking_chunks_v1/children.jsonl').exists():
            self.skipTest('Requires the generated local corpus; see docs/SETUP.md')
        from bank_retrieval_v4 import build_view
        records,_=build_view();binder=CellBinder()
        component=next(r for r in records if r['chunk_id']=='v4:cba24:p027:b001:r3')
        total=next(r for r in records if r['chunk_id']=='v4:cba24:p027:b001:r5')
        self.assertEqual(binder.bind(component,'operating_expenses'),[])
        self.assertTrue(binder.bind(total,'operating_expenses'))

    def test_date_and_difference_columns(self):
        self.assertEqual(column_date('30 Jun 25 $M'),'2025-06-30')
        self.assertEqual(column_date('Sep 24 $m'),'2024-09-30')
        self.assertIsNone(column_date('Jun 25 vs Jun 24 %'))
        self.assertIsNone(column_date('Sep 25 v Sep 24'))

    def test_decimal_change(self):
        result=calculate_change([cell('100'),cell('110',2025)])
        self.assertEqual(result['absolute_change'],'10')
        self.assertEqual(result['relative_change_percent'],'10.0')

    def test_percent_change_is_percentage_points(self):
        result=calculate_change([cell('1.99',unit='percent'),cell('2.08',2025,unit='percent')])
        self.assertEqual(result['basis_points'],'9.00')
        self.assertEqual(result['percentage_points'],'0.09')
        self.assertNotIn('relative_change_percent',result)

    def test_comparability_fields_are_enforced(self):
        for changes in [{'company':'NAB'},{'scope':'including_discontinued'},{'unit':'AUD billion'},
                        {'basis':'statutory'},{'report_year':2024},{'period_kind':'half_year'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                calculate_change([cell(),cell('110',2025,**changes)])

    def test_zero_and_negative_base_no_growth_percent(self):
        for value in ['0','-5']:
            self.assertIsNone(calculate_change([cell(value),cell('10',2025)])['relative_change_percent'])

    def test_year_order_and_identical_dates(self):
        self.assertEqual(calculate_change([cell('110',2025),cell('100')])['absolute_change'],'10')
        with self.assertRaises(ValueError): calculate_change([cell(),cell()])

    def test_selection_conflict_is_not_hidden(self):
        binder=object.__new__(CellBinder)
        binder.bind=lambda record,metric:record['cells']
        request={'metric':'cash_profit','company':'CBA','scope':None,'report_year':2025,'value_years':[2024]}
        records=[{'source':{'company':'CBA'},'cells':[cell('100'),cell('101')]}]
        chosen,issues=binder.select(records,request,'cash profit')
        self.assertEqual(chosen,[]);self.assertIn('conflicting',issues[0])

    def test_selection_excludes_half_year_and_wrong_scope(self):
        binder=object.__new__(CellBinder);binder.bind=lambda r,m:r['cells']
        request={'metric':'cash_profit','company':'CBA','scope':None,'report_year':2025,'value_years':[2024]}
        records=[{'source':{'company':'CBA'},'cells':[cell('100'),cell('50',period_kind='half_year'),cell('110',scope='including_discontinued')]}]
        chosen,issues=binder.select(records,request,'cash profit')
        self.assertEqual([x.value for x in chosen],['100']);self.assertFalse(issues)

    def test_no_reference_keys_in_runtime(self):
        root=Path(__file__).resolve().parents[1]
        for file in ['bank_source_cells.py','answer_bank_v8.py']:
            code=(root/'scripts'/file).read_text()
            for name in ['metric_scope_13.json','reference.json','expected_answer','eval/']:
                self.assertNotIn(name,code)


if __name__=='__main__': unittest.main()
