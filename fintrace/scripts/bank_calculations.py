"""Decimal arithmetic for explicitly reviewed source cells, never LLM arithmetic.

This module does not certify a table header mapping or manufacture review approval.
The answer model cannot set the review fields. Automatic operand selection remains
disabled until a separate source/column/basis validation workflow exists.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
import re


UNITS={
    'AUD million':('AUD',Decimal('1000000')),
    'AUD billion':('AUD',Decimal('1000000000')),
    'AUD':('AUD',Decimal(1)),
    'cents/share':('AUD/share',Decimal('.01')),
    'AUD/share':('AUD/share',Decimal(1)),
    'percent':('percent',Decimal(1)),
}


@dataclass(frozen=True)
class ReviewedCell:
    value: Decimal
    unit: str
    company: str
    metric: str
    basis: str
    scope: str
    period_kind: str
    period_end: str
    report_year: int
    source_id: str
    column: int
    source_text_sha256: str
    reviewer: str


def parse_number(value):
    text=value.strip()
    number=r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?'
    if not re.fullmatch(r'(?:-?'+number+r'|\('+number+r'\))%?',text):
        raise ValueError('Cell is not an unambiguous number; blanks/dashes are not zero')
    text=text.rstrip('%').replace(',','')
    if text.startswith('('): text='-'+text[1:-1]
    try: number=Decimal(text)
    except InvalidOperation as error: raise ValueError('Invalid source number') from error
    if not number.is_finite(): raise ValueError('Non-finite source number')
    return number


def reviewed_cell(selection,registry):
    """A caller-supplied reviewed selection must bind to the current source text."""
    if selection.get('review_status')!='approved' or not selection.get('reviewer','').strip():
        raise ValueError('Operand needs explicit source/header/basis review')
    source_id=selection['source_id']
    if source_id not in registry or ':r' not in source_id:
        raise ValueError('Operand must be a retrieved table row')
    source=registry[source_id]
    if source['quality']['status']=='quarantined': raise ValueError('Quarantined cell')
    digest=hashlib.sha256(source['text'].encode()).hexdigest()
    if selection['source_text_sha256']!=digest: raise ValueError('Reviewed source text changed')
    column=selection['column']
    cells=source['text'].split('|')
    if type(column) is not int or not 0<column<len(cells): raise ValueError('Invalid numeric column')
    required=('company','metric','basis','scope','period_kind','period_end','unit')
    if any(not isinstance(selection.get(k),str) or not selection[k].strip() for k in required):
        raise ValueError('Review metadata is incomplete')
    if selection['company']!=source['source']['company']: raise ValueError('Wrong company')
    if selection['unit'] not in UNITS: raise ValueError('Unsupported unit')
    if selection['period_kind'] not in ('annual','as_at','quarterly_average','half_year'):
        raise ValueError('Unsupported period kind')
    fields={k:selection[k] for k in required}
    fields['period_end']=date.fromisoformat(selection['period_end']).isoformat()
    return ReviewedCell(value=parse_number(cells[column]),
        **fields,
        report_year=source['source']['report_year'],source_id=source_id,column=column,
        source_text_sha256=digest,reviewer=selection['reviewer'])


def change(earlier,later,*,cross_vintage_review=None):
    for key in ('company','metric','basis','scope','period_kind'):
        if getattr(earlier,key)!=getattr(later,key): raise ValueError('Incompatible '+key)
    if date.fromisoformat(earlier.period_end)>=date.fromisoformat(later.period_end):
        raise ValueError('Periods must be distinct and chronological')
    if earlier.report_year!=later.report_year:
        if not cross_vintage_review or cross_vintage_review.get('status')!='approved' or not cross_vintage_review.get('reviewer') or not cross_vintage_review.get('reason'):
            raise ValueError('Cross-vintage comparison requires an explicit comparability review')
    unit1,scale1=UNITS[earlier.unit];unit2,scale2=UNITS[later.unit]
    if unit1!=unit2: raise ValueError('Incompatible unit dimensions')
    before=earlier.value*scale1;after=later.value*scale2
    delta=after-before
    result={'operation':'change','earlier':str(before),'later':str(after),
            'absolute_change':str(delta),'normalised_unit':unit1,
            'formula':'later - earlier',
            'sources':[{'source_id':x.source_id,'column':x.column,'period_end':x.period_end,
                        'text_sha256':x.source_text_sha256,'reviewer':x.reviewer} for x in (earlier,later)],
            'basis':earlier.basis,'scope':earlier.scope,'arithmetic_checked':True,
            'semantic_review':'caller_supplied_not_independently_certified'}
    if unit1=='percent':
        result.update(percentage_point_change=str(delta),basis_point_change=str(delta*100))
    elif before>0:
        result.update(relative_change_percent=str(delta/before*100),
                      relative_formula='(later - earlier) / earlier * 100')
    else:
        result['relative_change_percent']=None
        result['relative_change_reason']='Relative growth is not reported for a zero or negative base.'
    return result
