from dataclasses import replace
from decimal import Decimal
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_calculations import parse_number,reviewed_cell,change


def pair():
    row='Test metric | 100 | 110'
    registry={'test:r1':{'text':row,'source':{'company':'CBA','report_year':2025},
                         'quality':{'status':'development_unreviewed'}}}
    selection={'review_status':'approved','reviewer':'synthetic test only','source_id':'test:r1',
        'source_text_sha256':hashlib.sha256(row.encode()).hexdigest(),'column':1,
        'company':'CBA','metric':'synthetic_metric','basis':'cash','scope':'Group continuing',
        'period_kind':'annual','period_end':'2024-06-30','unit':'AUD million'}
    first=reviewed_cell(selection,registry)
    second=reviewed_cell({**selection,'column':2,'period_end':'2025-06-30'},registry)
    return first,second,selection,registry


class CalculationTests(unittest.TestCase):
    def test_exact_decimal_growth(self):
        a,b,_,_=pair();r=change(a,b)
        self.assertEqual(Decimal(r['relative_change_percent']),Decimal(10))

    def test_parentheses_sign(self): self.assertEqual(parse_number('(1,234.5)'),Decimal('-1234.5'))

    def test_dash_not_zero(self):
        for text in ('-','','large','NaN','1.2.3','1,23'):
            with self.assertRaises(ValueError): parse_number(text)

    def test_review_required(self):
        _,_,s,r=pair();s['review_status']='pending'
        with self.assertRaises(ValueError): reviewed_cell(s,r)

    def test_changed_source_rejected(self):
        _,_,s,r=pair();r['test:r1']['text']='Test metric | 999 | 110'
        with self.assertRaises(ValueError): reviewed_cell(s,r)

    def test_wrong_column_rejected(self):
        _,_,s,r=pair();s['column']=0
        with self.assertRaises(ValueError): reviewed_cell(s,r)

    def test_wrong_company_rejected(self):
        _,_,s,r=pair();s['company']='NAB'
        with self.assertRaises(ValueError): reviewed_cell(s,r)

    def test_basis_scope_period_metric_cannot_mix(self):
        a,b,_,_=pair()
        for key,value in [('company','NAB'),('basis','statutory'),('scope','Company'),
                          ('period_kind','half_year'),('metric','other')]:
            with self.assertRaises(ValueError): change(a,replace(b,**{key:value}))

    def test_million_billion_conversion(self):
        a,b,_,_=pair();b=replace(b,unit='AUD billion',value=Decimal('.11'))
        self.assertEqual(Decimal(change(a,b)['relative_change_percent']),Decimal(10))

    def test_percentage_points_not_percent_growth(self):
        a,b,_,_=pair();r=change(replace(a,unit='percent',value=Decimal('1.9')),replace(b,unit='percent',value=Decimal('2.1')))
        self.assertEqual(Decimal(r['basis_point_change']),Decimal(20))
        self.assertNotIn('relative_change_percent',r)

    def test_zero_and_negative_base(self):
        a,b,_,_=pair()
        for base in (0,-1): self.assertIsNone(change(replace(a,value=Decimal(base)),b)['relative_change_percent'])

    def test_cross_vintage_requires_review(self):
        a,b,_,_=pair();a=replace(a,report_year=2024)
        with self.assertRaises(ValueError): change(a,b)

    def test_reverse_period_rejected(self):
        a,b,_,_=pair()
        with self.assertRaises(ValueError): change(b,a)

    def test_basic_iso_date_normalised(self):
        _,_,s,r=pair();s['period_end']='20250630'
        self.assertEqual(reviewed_cell(s,r).period_end,'2025-06-30')

    def test_mixed_date_format_cannot_reverse_comparison(self):
        a,b,_,_=pair()
        with self.assertRaises(ValueError):
            change(replace(a,period_end='2025-09-30'),replace(b,period_end='20250630'))


if __name__=='__main__': unittest.main()
