"""Bounded operation planning and arithmetic. No financial answer keys."""
from copy import deepcopy
from decimal import Decimal
import re
from bank_retrieval_v6 import explicit_metrics
from bank_source_cells import DEFAULT_SCOPE

EXPENSES={'operating_expenses','credit_impairment','statutory_operating_expenses',
          'statutory_credit_impairment','statutory_income_tax_expense'}


def operation_plan(question):
    s=re.sub(r'[-–]',' ',question.lower())
    result={'kind':'none','order':None,'expense_magnitude':False,'relative_percent':False}
    if re.search(r'\bdivided by\b|\bratio of\b|\bsum of\b|\bmultipl(?:y|ied)\b|\bcagr\b|\bannualis?ed\b',s):
        return {**result,'kind':'unsupported','reason':'Derived ratios, sums and compound-growth calculations are not enabled.'}
    if re.search(r'\bconvert\b|\busd\b|\bus dollars\b|\bnzd\b',s):
        return {**result,'kind':'unsupported','reason':'Currency conversion is not enabled and no exchange rate has been retrieved or validated for this calculation. No USD or NZD result has been inferred.'}
    if re.search(r'\bwhich (?:bank|company).*(?:higher|larger|bigger|better)|\brank\b',s):
        return {**result,'kind':'unsupported','reason':'Automatic bank ranking is not enabled; reporting dates and bases must be compared explicitly.'}
    requested=bool(re.search(r'calculate|quantify|work out|by how much|how much.*(?:grew|grow|rise|rose|fell|fall|increase|decrease)|how far|difference|movement|change|increase in|minus|subtract|less the',s))
    # A prose "why" question is not itself a request for arithmetic.
    if re.search(r'^\s*(?:why|explain)|what (?:made|factors|caused)',s) and not re.search(r'calculate|quantify|work out',s):
        requested=False
    result['relative_percent']=bool(re.search(r'percent(?:age)? (?:change|growth|increase)|growth (?:rate|percent)|percentage',s)) and not bool(re.search(r'not (?:a )?percent|no percent',s))
    result['expense_magnitude']=not bool(re.search(r'signed (?:change|values|deductions)|source.signed|preserve.*sign',s))
    metrics=set(explicit_metrics(question))
    if requested and {'cash_profit','statutory_npat'}<=metrics and len(set(re.findall(r'20\d{2}',s)))==1:
        # Same-period cross-basis arithmetic is a named exception, not a generic
        # permission to subtract unrelated financial metrics.
        if re.search(r'statutory.*(?:minus|less|exceeds).*cash',s):
            return {**result,'kind':'profit_gap','order':['statutory_npat','cash_profit']}
        if re.search(r'cash.*(?:minus|less|exceeds).*statutory',s):
            return {**result,'kind':'profit_gap','order':['cash_profit','statutory_npat']}
        return {**result,'kind':'unsupported','reason':'Specify cash minus statutory, or statutory minus cash, for the same-period profit gap.'}
    if re.search(r'\bminus\b|\bsubtract\b|\bless\b',s):
        if len(metrics)>1:
            return {**result,'kind':'unsupported','reason':'Cannot subtract different measures or incompatible units. The only supported cross-basis operation is a same-period cash/statutory profit gap; this is not a net-assets calculation.'}
        ordered=None
        m=re.search(r'(.+?)\b(?:minus|less)\b(.+)',s)
        if m:
            left=re.findall(r'(?:fy\s*)?(20\d{2})',m[1]);right=re.findall(r'(?:fy\s*)?(20\d{2})',m[2])
            if left and right: ordered=[int(left[-1]),int(right[0])]
            elif re.search(r'later|newer',m[1]) and re.search(r'earlier|older',m[2]): ordered='later_first'
            elif re.search(r'earlier|older',m[1]) and re.search(r'later|newer',m[2]): ordered='earlier_first'
        m=re.search(r'subtract (.*?) from (.*)',s)
        if m:
            first=re.findall(r'20\d{2}',m[1]);second=re.findall(r'20\d{2}',m[2])
            if first and second: ordered=[int(second[0]),int(first[-1])]
        if not ordered:
            return {**result,'kind':'unsupported','reason':'The subtraction order is unclear. Specify two financial years and which value to subtract from which.'}
        return {**result,'kind':'year_difference','order':ordered}
    if requested: result['kind']='change'
    return result


def finish_plan(question,plan):
    p=deepcopy(plan);op=operation_plan(question);p['operation_request']=op;p['version']='v9'
    if p['behavior']!='answer': return p
    if op['kind']=='unsupported':
        p.update(behavior='abstain',reason=op['reason'],requests=[]);return p
    s=question.lower()
    global_continuing=bool(re.search(r'continuing operations only|keep discontinued .*out of both|both.*continuing operations|continuing operations.*(?:cash|statutory)',s))
    conflicting=bool(re.search(r'including discontinued|after discontinued',s))
    if global_continuing and not conflicting:
        for request in p['requests']:
            if request['metric'] in ('cash_profit','statutory_npat','basic_cash_eps'):
                request['scope']='continuing'
    if op['kind'] in ('change','year_difference','profit_gap'):
        tags=explicit_metrics(question) or p['metrics']
        if tags and any(r['metric'] is None for r in p['requests']):
            p['requests']=[{**r,'metric':tag,'id':f'request-{i}-{tag}'} for i,r in enumerate(p['requests']) for tag in tags]
        p['intent']='compare'
        for request in p['requests']:
            request['intent']='compare'
            if global_continuing and not conflicting and request['metric'] in DEFAULT_SCOPE:
                request['scope']='continuing'
        p['constraints']['requires_new_calculation']=True
    return p


def compatible(cells,cross_basis=False):
    if len(cells)!=2: raise ValueError('Exactly two source cells are required')
    fields=['company','scope','period_kind','unit','report_year']
    fields+=['period_end'] if cross_basis else ['metric','basis']
    for field in fields:
        if getattr(cells[0],field)!=getattr(cells[1],field): raise ValueError('Incompatible '+field)
    if cross_basis:
        if {c.metric for c in cells}!={'cash_profit','statutory_npat'}: raise ValueError('Only the named profit-basis gap is supported')
    elif cells[0].period_end==cells[1].period_end: raise ValueError('Distinct periods required')


def presentation(cell,op):
    value=Decimal(cell.value)
    if cell.metric in EXPENSES and op['expense_magnitude'] and op['kind']!='none':
        return {'value':str(abs(value)),'representation':'expense_magnitude',
                'note':'Positive expense magnitude; the source presents a deduction in brackets.' if value<0 else 'Positive expense amount as disclosed.',
                'transformation':'abs(source_value)' if value<0 else 'identity','source_value':cell.value}
    return {'value':cell.value,'representation':'source_signed','note':'Original source sign preserved.','transformation':'identity','source_value':cell.value}


def calculate(cells,op):
    cross=op['kind']=='profit_gap';compatible(cells,cross)
    if cross:
        lookup={c.metric:c for c in cells};left,right=[lookup[k] for k in op['order']]
        note='Numerical cash/statutory gap only; this is not an explanation of its adjustments.'
    else:
        earlier,later=sorted(cells,key=lambda c:c.period_end)
        if op['kind']=='year_difference':
            order=op['order']
            if isinstance(order,list):
                lookup={int(c.period_end[:4]):c for c in cells}
                if len(set(order))!=2 or set(order)!=set(lookup): raise ValueError('Requested years do not match the bound operands')
                left,right=[lookup[y] for y in order]
            else: left,right=(earlier,later) if order=='earlier_first' else (later,earlier)
        else: left,right=later,earlier
        note='Explicit operand order preserved.' if op['kind']=='year_difference' else 'Chronological change: later minus earlier.'
        if left.metric in EXPENSES and op['expense_magnitude'] and Decimal(left.value)*Decimal(right.value)<0:
            raise ValueError('Expense/recovery sign reversal needs review; absolute values would hide its meaning')
    lp,rp=presentation(left,op),presentation(right,op)
    a,b=Decimal(lp['value']),Decimal(rp['value']);delta=a-b
    out={'operation':op['kind'],'left':str(a),'right':str(b),'absolute_change':str(delta),'unit':left.unit,
         'formula':'left - right','operand_labels':[f'{c.company} {c.metric} {c.period_end}' for c in (left,right)],
         'source_cells':[left.payload(),right.payload()],'presentations':[lp,rp],
         'source_signed_difference':str(Decimal(left.value)-Decimal(right.value)),
         'arithmetic':'Python Decimal','note':note}
    if left.unit=='percent': out.update(percentage_points=str(delta),basis_points=str(delta*100))
    elif op['relative_percent']:
        out['relative_change_percent']=str(delta/b*100) if b>0 else None
    return out
