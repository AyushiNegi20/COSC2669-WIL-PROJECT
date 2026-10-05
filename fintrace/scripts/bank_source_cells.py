"""Bind retrieved rows to literal date columns. No answer keys or stored values."""
from calendar import monthrange
from dataclasses import dataclass,asdict
from datetime import date
from decimal import Decimal
import hashlib
import re
from bank_retrieval import source_units
from bank_retrieval_v4 import norm
from bank_calculations import parse_number
from bank_answer import numeric_tokens

EPS_METRICS = {'basic_cash_eps', 'diluted_cash_eps', 'basic_statutory_eps', 'diluted_statutory_eps'}
FLOW={'cash_profit','statutory_npat','operating_income','operating_expenses','credit_impairment','nim','dividend_per_share'} | EPS_METRICS
DEFAULT_SCOPE={'cash_profit':'continuing','statutory_npat':'including_discontinued','basic_cash_eps':'continuing',
    'operating_income':'continuing','operating_expenses':'continuing','credit_impairment':'continuing','nim':'continuing'}
LABELS={'cash_profit':'cash profit','statutory_npat':'statutory net profit after tax',
    'basic_cash_eps':'basic cash EPS','dividend_per_share':'dividend per share',
    'diluted_cash_eps':'diluted cash EPS', 'basic_statutory_eps':'basic statutory EPS',
    'diluted_statutory_eps':'diluted statutory EPS',
    'operating_income':'total operating income','operating_expenses':'operating expenses',
    'credit_impairment':'credit impairment charge','nim':'net interest margin',
    'total_assets':'total Group assets','gross_loans':'gross loans and acceptances',
    'customer_deposits':'customer deposits','cet1':'CET1 capital ratio','lcr':'LCR'}


@dataclass(frozen=True)
class BoundCell:
    metric:str
    company:str
    value:str
    raw_value:str
    unit:str
    basis:str
    scope:str
    period_kind:str
    period_end:str
    report_year:int
    column:int
    source_id:str
    header_ids:tuple
    record_id:str
    source:dict
    row_quote:str
    binding_status:str='rule_bound_development_not_human_certified'

    def payload(self): return asdict(self)


def column_date(text):
    if re.search(r'\bvs?\b|%',text,re.I): return None
    match=re.search(r'(?:(\d{1,2})\s+)?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2}|\d{2})\b',text,re.I)
    if not match: return None
    month=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(match[2].lower())+1
    year=int(match[3]);year=year+2000 if year<100 else year
    day=int(match[1]) if match[1] else monthrange(year,month)[1]
    return date(year,month,day).isoformat()


def row_identity(record,metric,page):
    row=norm(record.get('row_label',''));label=norm(record['label']);body=norm(record['body'])
    scope='Group';basis='reported';native=norm(page['native_text'])
    if metric not in record['metric_tags'] and not (metric in EPS_METRICS and 'basic_cash_eps' in record['metric_tags']): return None
    if metric=='cash_profit':
        if not re.fullmatch(r'cash (?:net profit after tax m|net profit after tax|profit|earnings)(?: \d)?',row): return None
        basis='cash'
    elif metric=='statutory_npat':
        if not re.search(r'^statutory net profit after tax|^net profit attributable to owners',row): return None
        basis='statutory'
    elif metric=='basic_cash_eps':
        if 'basic' not in label or 'cash' not in label or 'diluted' in label: return None
        basis='basic cash'
    elif metric in EPS_METRICS:
        style = 'diluted' if metric.startswith('diluted') else 'basic'
        accounting = 'statutory' if 'statutory' in metric else 'cash'
        # The literal row must identify EPS, style and accounting basis. A
        # nearby statutory section or generic "EPS" row is not enough.
        if not re.search(r'earnings per share|\beps\b', label): return None
        if not all(word in row for word in (style, accounting)): return None
        if ('diluted' in row) != (style == 'diluted'): return None
        basis = style + ' ' + accounting
    elif metric=='dividend_per_share':
        if not row.startswith('dividend per share') or re.search(r'interim|final',row): return None
        return 'ordinary dividend','Group'
    elif metric=='total_assets':
        # NAB's primary results has a single Group balance-sheet section; its annual
        # report with parallel Company columns is deliberately excluded in bind().
        nab_group_section=record['source']['company']=='NAB' and any(
            re.fullmatch(r'\d+ balance sheet',norm(b.get('text',''))) for b in page['blocks'] if b['type']=='section_header')
        if row!='total assets' or not (re.search(r'group|consolidated',native) or nab_group_section): return None
        return 'consolidated balance sheet','Group'
    elif metric=='operating_income':
        if not re.fullmatch(r'(?:total|net) operating income(?: \d)?',row): return None
        basis='cash'
    elif metric=='operating_expenses':
        if not re.fullmatch(r'(?:total )?operating expenses(?: \d)?',row): return None
        basis='cash'
    elif metric=='credit_impairment':
        if not re.fullmatch(r'(?:loan|credit) impairment (?:expense|charge)(?: \d)?',row): return None
        basis='cash'
    elif metric=='nim':
        if not row.startswith('net interest margin'): return None
        if 'statutory basis' in label: basis='statutory'
        elif 'cash' in label or 'cash basis unless stated otherwise' in native: basis='cash'
        else: return None
    elif metric=='gross_loans':
        if not re.search(r'^gross loans and acceptances',row): return None
        return 'gross before impairment allowances','Group'
    elif metric=='customer_deposits':
        if not re.fullmatch(r'(?:total )?customer deposits(?: \d)?',row): return None
        return 'customer deposits','Group'
    elif metric=='cet1':
        if not re.search(r'common equity tier 1|^cet 1 capital ratio',row): return None
        if not re.search(r'apra|level 2 group capital',label): return None
        return 'APRA / Level 2 Group','Group'
    elif metric=='lcr':
        if not re.search(r'liquidity coverage ratio|^(?:quarterly average )?lcr',row): return None
        if not re.search(r'quarterly average|quarter average',body+' '+native): return None
        return 'reported quarterly average','Group'
    else: return None
    if 'including discontinued' in label: scope='including_discontinued'
    elif 'continuing operations' in label: scope='continuing'
    elif metric=='statutory_npat' and 'attributable to owners' in row: scope='including_discontinued'
    elif record['source']['company']=='NAB' and metric in ('cash_profit','operating_income','operating_expenses','credit_impairment','nim'):
        # Only the Group performance result/ratios tables, not divisional results.
        if 'group performance results' not in native: return None
        scope='continuing'
    elif metric in ('operating_income','operating_expenses','credit_impairment') and 'cash basis' in body:
        scope='continuing'
    if (metric in DEFAULT_SCOPE or metric in EPS_METRICS) and scope=='Group': return None
    return basis,scope


class CellBinder:
    def __init__(self):
        self.units,self.pages=source_units()
        self.blocks={b['id']:b for p in self.pages.values() for b in p['blocks'] if b['type']=='table'}

    def bind(self,record,metric):
        if record['kind']!='financial_row' or record['quality']['status']=='quarantined': return []
        if '_ar' in record['source']['document_id']: return []  # Group/Company parallel annual-report tables need a separate profile.
        block=self.blocks[record['table_id']];rows=block['rows'];row=rows[record['row']]
        # A component labelled simply 'Operating expenses' is not the total when
        # the same table separately adds restructuring or other adjustments.
        if metric=='operating_expenses' and not norm(record['row_label']).startswith('total '):
            if any(norm(r[0]).startswith('total operating expenses') for r in rows if r): return []
        page=self.pages[record['table_id'].rsplit(':',1)[0]]
        identity=row_identity(record,metric,page)
        if not identity: return []
        basis,scope=identity;result=[]
        # Header rows are actual structural dependencies, not guessed fixed positions.
        headers=[(int(u.rsplit(':r',1)[1]),u) for u in record['dependency_units'] if u.startswith(record['table_id']+':r')]
        date_headers=[(i,u) for i,u in headers if any(column_date(c) for c in rows[i][1:])]
        if len(date_headers)!=1: return []
        di,du=date_headers[0]
        native_numbers=numeric_tokens(re.sub(r'\(\s+','(',page['native_text']))
        for col,raw in enumerate(row[1:],1):
            if col>=len(rows[di]): continue
            end=column_date(rows[di][col])
            if not end or int(end[:4]) not in (2024,2025): continue
            try: value=parse_number(raw)
            except ValueError: continue
            if str(value.normalize()) not in native_numbers: continue
            groups=[]
            for i,_ in headers:
                if i>=di: continue
                prior=[c for c in rows[i][1:col+1] if c.strip()]
                if prior: groups.append(norm(prior[-1]))
            group=' '.join(groups)
            if metric in FLOW:
                if 'half year' in group: kind='half_year'
                elif 'full year' in group or re.search(r'\byear to\b',group): kind='annual'
                else: continue
            else: kind='quarterly_average' if metric=='lcr' else 'as_at'
            # Inspect the row's own measure context and column unit, not unrelated values.
            hints=record['label']+' '+rows[di][col]
            if (metric in EPS_METRICS or metric=='dividend_per_share') and re.search(r'cents',hints,re.I): unit='cents/share'
            elif metric in ('nim','cet1','lcr') and ('%' in raw or '%' in hints or metric=='cet1'): unit='percent'
            elif re.search(r'\$\s*bn|\bbillions?\b',hints,re.I): unit='AUD billion'
            elif re.search(r'\$\s*m\b|\bmillions?\b',hints,re.I): unit='AUD million'
            else: continue
            target=f"{record['table_id']}:r{record['row']}"
            result.append(BoundCell(metric,record['source']['company'],str(value),raw,unit,basis,scope,kind,end,
                record['source']['report_year'],col,target,tuple(u for _,u in headers),record['chunk_id'],record['source'],self.units[target]))
        return result

    def select(self,records,request,question):
        metric=request['metric'];candidates=[]
        restriction=period_restriction(question,request['company'])
        if restriction: return [],[restriction]
        for r in records:
            if r['source']['company']==request['company']: candidates+=self.bind(r,metric)
        scope=request['scope'] or DEFAULT_SCOPE.get(metric)
        candidates=[c for c in candidates if (not scope or c.scope==scope)
            and (not request['report_year'] or c.report_year==request['report_year'])
            and (metric not in FLOW or c.period_kind=='annual')]
        if metric=='nim':
            requested_basis='statutory' if 'statutory' in norm(question) else 'cash'
            candidates=[c for c in candidates if c.basis==requested_basis]
        years=request['value_years']
        if not years: return [],['Please specify FY2024 or FY2025.']
        # Prefer one common vintage for compatible comparisons; never merge originals silently.
        common=set.intersection(*[{c.report_year for c in candidates if int(c.period_end[:4])==y} for y in years])
        preferred=request['report_year'] or (max(common) if len(years)>1 and common else None)
        selected=[];issues=[]
        for year in years:
            options=[c for c in candidates if int(c.period_end[:4])==year]
            vintage=preferred or (year if any(c.report_year==year for c in options) else max((c.report_year for c in options),default=0))
            options=[c for c in options if c.report_year==vintage]
            # Exclude a mid-year as-at column for an annual financial-year request.
            options=[c for c in options if c.period_end[5:]==('06-30' if c.company=='CBA' else '09-30')]
            identities={(c.value,c.unit,c.basis,c.scope,c.period_kind,c.period_end) for c in options}
            if len(identities)!=1:
                issues.append(f'{request["company"]} FY{year}: '+('conflicting source cells' if identities else 'no unambiguous supported cell'))
            else: selected.append(options[0])
        return selected,issues


def period_restriction(question,company):
    """Keep the annual demo from silently substituting a financial-year end."""
    s=norm(question)
    if re.search(r'half year|halfyear|\bh\s*[12]\b|six months|interim|\bq\s*[1-4]\b',s):
        return 'This demo binds full-year results and financial-year-end balances only; half-year and quarter requests are not enabled.'
    months=re.findall(r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b',s)
    expected='jun' if company=='CBA' else 'sep'
    if any(m[:3]!=expected for m in months):
        return 'The requested date is outside the supported financial-year-end columns; no substitute date has been used.'
    for d in re.findall(r'\b(\d{1,2})\s+(?:jun(?:e)?|sep(?:tember)?)\b',s):
        if d!='30': return 'Only the disclosed financial-year-end date is supported, not a different day.'
    for y,m,d in re.findall(r'\b(20\d{2})[-/](\d{2})[-/](\d{2})\b',question):
        if (m,d)!=(('06','30') if company=='CBA' else ('09','30')):
            return 'The requested date is outside the supported financial-year-end columns; no substitute date has been used.'
    return None


def calculate_change(cells):
    if len(cells)!=2: raise ValueError('A change needs exactly two bound cells')
    first,last=sorted(cells,key=lambda c:c.period_end)
    for field in ('company','metric','basis','scope','period_kind','unit','report_year'):
        if getattr(first,field)!=getattr(last,field): raise ValueError('Incompatible '+field)
    if first.period_end==last.period_end: raise ValueError('Distinct periods required')
    before,after=Decimal(first.value),Decimal(last.value);delta=after-before
    result={'operation':'change','earlier':first.value,'later':last.value,'absolute_change':str(delta),
        'unit':first.unit,'formula':'later - earlier','source_cells':[first.payload(),last.payload()],
        'arithmetic':'Python Decimal','binding_status':'rule_bound_development_not_human_certified'}
    if first.unit=='percent': result.update(percentage_points=str(delta),basis_points=str(delta*100))
    else: result['relative_change_percent']=str(delta/before*100) if before>0 else None
    return result
