"""Additional NAB statement rows, read from issuer PDFs rather than answer keys.

Two extractors must agree on every row and year column. Financial performance
tables must also reconcile. This is bounded numerical coverage, not permission
to treat every page's text as calculation-ready.
"""
from functools import lru_cache
from hashlib import sha256
from decimal import Decimal
import re

from bank_calculations import parse_number
from bank_source_cells import BoundCell
from bank_operations_v9 import calculate, operation_plan, presentation

ROWS = {
    'statutory_net_interest_income': 'Net interest income',
    'statutory_other_operating_income': 'Other operating income',
    'statutory_operating_income': 'Net operating income',
    'statutory_operating_expenses': 'Operating expenses',
    'statutory_credit_impairment': 'Credit impairment charge',
    'statutory_profit_before_tax': 'Profit before income tax',
    'statutory_income_tax_expense': 'Income tax expense',
    'statutory_continuing_profit': 'Net profit for the year from continuing operations',
    'statutory_discontinued_loss': 'Net loss after tax for the year from discontinued operations',
    'statutory_total_profit': 'Net profit for the year',
    'profit_attributable_to_non_controlling_interests': 'Profit attributable to non-controlling interests',
    'statutory_owners_profit': 'Net profit attributable to owners of the Company',
}
EPS_ROWS = {
    'basic_statutory_eps': 'Statutory earnings per share - basic (cents)',
    'diluted_statutory_eps': 'Statutory earnings per share - diluted (cents)',
}
SEGMENT_ROWS = {
    'underlying_profit': 'Underlying profit / (loss)',
    'cash_earnings': 'Cash earnings / (loss)',
    'hedging_adjustment': 'Hedging and fair value volatility',
    'other_non_cash_adjustments': 'Other non-cash earnings items',
    'continuing_owners_profit': 'Net profit / (loss) for the year from continuing operations',
    'discontinued_owners_loss': 'Net loss from discontinued operations attributable to owners of the Company',
    'statutory_owners_profit': 'Net profit / (loss) attributable to owners of the Company',
}
NUMBER = r'(?:\(?-?\d[\d,]*(?:\.\d+)?\)?)'
DISTINCT_SCOPE = (r'\bparent\b|\bCompany separately\b|\bBusiness and Private Banking\b|'
                 r'\bPersonal Banking\b|\bNew Zealand\b|\bCorporate and Institutional Banking\b|'
                 r'\bCorporate Functions\b|\bhalf.year\b|\bquarter\b|\bcalendar\b')


def rows_from(text, labels, columns):
    output = {}
    for metric, label in labels.items():
        pattern = re.escape(label).replace(r'\ ', r'\s+')
        if metric == 'statutory_other_operating_income':
            pattern = r'Other\s+(?:operating\s+)?income'
        if metric in EPS_ROWS:
            style = 'basic' if metric == 'basic_statutory_eps' else 'diluted'
            alternate = re.escape('Statutory earnings per share (cents) - '+style).replace(r'\ ',r'\s+')
            pattern = '(?:'+pattern+'|'+alternate+')'
        # Footnote markers belong to the label, never to a year/value column.
        found = re.findall(pattern + r'(?:\s*\(\d\))?\s+' +
                           r'\s+'.join('('+NUMBER+')' for _ in range(columns)), text, re.I)
        if not found or len(set(found)) != 1:
            raise ValueError('Missing or ambiguous statement row: '+label)
        output[metric] = [str(parse_number(v)) for v in found[0]]
    return output


def parse_table(primary, secondary, kind):
    heading = r'Financial performance\s+Group' if kind == 'performance' else r'5 Year Key Performance Indicators\s+Group'
    columns = 2 if kind == 'performance' else 5
    results = []
    for text in (primary, secondary):
        match = re.search(heading + r'\s+' + r'\s+'.join(r'(20\d{2})' for _ in range(columns)), text, re.I)
        if not match:
            raise ValueError('Statement Group/year headers unavailable')
        years = [int(y) for y in match.groups()]
        if any(a-b != 1 for a,b in zip(years, years[1:])):
            raise ValueError('Unexpected year column order')
        tail = text[match.end():]
        if kind == 'performance' and not re.match(r'\s*\$m\s+\$m', tail, re.I):
            raise ValueError('Million-dollar units unavailable')
        rows = rows_from(tail, ROWS if kind == 'performance' else EPS_ROWS, columns)
        results.append((years, rows))
    if results[0] != results[1]:
        raise ValueError('PDF extractors disagree on table rows or columns')
    years, rows = results[0]
    if kind == 'performance':
        equations = (
            ('statutory_operating_income', ('statutory_net_interest_income','statutory_other_operating_income')),
            ('statutory_profit_before_tax', ('statutory_operating_income','statutory_operating_expenses','statutory_credit_impairment')),
            ('statutory_continuing_profit', ('statutory_profit_before_tax','statutory_income_tax_expense')),
            ('statutory_total_profit', ('statutory_continuing_profit','statutory_discontinued_loss')),
            ('statutory_total_profit', ('statutory_owners_profit','profit_attributable_to_non_controlling_interests')),
        )
        for col in range(columns):
            for total, parts in equations:
                if Decimal(rows[total][col]) != sum(Decimal(rows[p][col]) for p in parts):
                    raise ValueError('Statement totals do not reconcile: '+total)
    return years, rows


def parse_segment(primary, secondary):
    parsed=[]
    for text in (primary,secondary):
        header=re.search(r'Segment information\s+(?:\(cont\.\)\s*)?(20\d{2})(?:\s*\(\d\))?\s+Business',text,re.I)
        if not header:raise ValueError('Segment year header not established')
        prefix=text[header.end():text.find('Reportable segment information')]
        if not re.search(r'Total\s+Group',prefix) or len(re.findall(r'\$m',prefix)) != 6:
            raise ValueError('Six segment columns with final Total Group not established')
        rows={}
        for metric,label in SEGMENT_ROWS.items():
            pattern=re.escape(label).replace(r'\ ',r'\s+')
            # pypdf can split the literal word "to" across text objects. Only
            # normalise that label whitespace; never alter numeric cell text.
            pattern=pattern.replace(r'\s+to\s+',r'\s+t\s*o\s+')
            hits=re.findall(pattern+r'\s+'+r'\s+'.join('('+NUMBER+'|-)'+'' for _ in range(6)),text,re.I)
            if len(set(hits)) != 1:raise ValueError('Uncertain segment row: '+label)
            raw=hits[0]
            if raw[-1]=='-':raise ValueError('A dash is not a numeric Group total')
            values=[parse_number(x) for x in raw if x!='-']
            if sum(values[:-1]) != values[-1]:raise ValueError('Segment components do not match Group total')
            rows[metric]=str(values[-1])
        if Decimal(rows['cash_earnings'])+Decimal(rows['hedging_adjustment'])+Decimal(rows['other_non_cash_adjustments']) != Decimal(rows['continuing_owners_profit']):
            raise ValueError('Cash to continuing statutory reconciliation failed')
        if Decimal(rows['continuing_owners_profit'])+Decimal(rows['discontinued_owners_loss']) != Decimal(rows['statutory_owners_profit']):
            raise ValueError('Continuing to total owners reconciliation failed')
        parsed.append((int(header[1]),rows))
    if parsed[0]!=parsed[1]:raise ValueError('Extractors disagree on segment table')
    return parsed[0]


@lru_cache(maxsize=1)
def tables():
    import pymupdf
    from pypdf import PdfReader
    from bank_report_library import get_library, specs, ROOT
    library = get_library()
    output = []
    for spec in specs():
        if spec['company'] != 'NAB' or 'Annual Report' not in spec['title']:
            continue
        path = ROOT/'data/raw'/spec['file']
        if sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            raise ValueError('Statement source checksum changed')
        candidates = [p for p in library.data['records'] if p['source']['document_id'] == spec['id']]
        reader = PdfReader(path)
        with pymupdf.open(path) as doc:
            for page in candidates:
                if re.search(r'Segment information',page['text'],re.I) and all(label in re.sub(r'\s+',' ',page['text']) for label in ('Underlying profit / (loss)','Reportable segment information')):
                    index=page['source']['pdf_page']-1
                    year,rows=parse_segment(reader.pages[index].extract_text(),doc[index].get_text())
                    output.append({'source':page['source'],'years':[year], 'rows':{k:[v] for k,v in rows.items()},
                                   'unit':'AUD million','kind':'segment'})
                for kind, heading in (('performance',r'Financial performance\s+Group'),
                                      ('eps',r'5 Year Key Performance Indicators\s+Group')):
                    if not re.search(heading, page['text'], re.I): continue
                    index = page['source']['pdf_page']-1
                    # Native reading order has one numeric cell per line in
                    # these tables; header and exact row labels define grouping.
                    years, rows = parse_table(reader.pages[index].extract_text(), doc[index].get_text(), kind)
                    if years[0] != spec['report_year']: raise ValueError('Wrong table report year')
                    output.append({'source': page['source'], 'years': years, 'rows': rows,
                                   'unit': 'cents/share' if kind == 'eps' else 'AUD million','kind':kind})
    return output


def requested_metrics(question):
    if re.search(r'\bwhy\b|\bexplain\b|\bdefine\b|\breconcile\b|\bmeaning\b|\bhow does\b',question,re.I): return []
    if re.search(r'\bcash\b|\bunderlying\b|\badjusted\b', question,re.I): return []
    found = []
    if re.search(r'\bnet interest income\b',question,re.I): found.append('statutory_net_interest_income')
    if re.search(r'\bstatutory\b|income.statement',question,re.I):
        if re.search(r'\b(?:net|total) operating income\b',question,re.I): found.append('statutory_operating_income')
        if re.search(r'\boperating expenses?\b',question,re.I): found.append('statutory_operating_expenses')
        if re.search(r'\bcredit impairment charge\b',question,re.I): found.append('statutory_credit_impairment')
        if re.search(r'\b(?:earnings per share|EPS)\b',question,re.I):
            if re.search(r'\bbasic\b',question,re.I): found.append('basic_statutory_eps')
            if re.search(r'\bdiluted\b',question,re.I): found.append('diluted_statutory_eps')
    if re.search(r'\bprofit before (?:income )?tax\b',question,re.I): found.append('statutory_profit_before_tax')
    if re.search(r'\bincome tax expense\b',question,re.I): found.append('statutory_income_tax_expense')
    return found


def answer(question, context):
    from bank_contract_v12 import metric_tags
    if re.search(DISTINCT_SCOPE,question,re.I): return None
    special = reconciliation_answer(question, context)
    if special is not None: return special
    if (context['banks']==['NAB'] and re.search(r'\bunderlying profit\b',question,re.I)
            and not re.search(r'\bwhy\b|\bexplain\b|\bdefine\b|\bwhat does\b|\bcompare\b|\bchange\b|\bincrease\b|\bdecrease\b|\bcalculate\b|\bparent\b|\bmargin\b|\bratio\b|\bper share\b|\bafter tax\b',question,re.I)):
        residual=re.sub(r'\bunderlying profit\b','',question,flags=re.I)
        if metric_tags(residual): return None
        return segment_answer(question,context,False)
    metrics = requested_metrics(question)
    if not metrics or context['banks'] != ['NAB']: return None
    allowed_tags={'operating_income','operating_expenses','credit_impairment','basic_cash_eps'}
    # "Statutory earnings per share" is EPS, not statutory NPAT. Remove only
    # that complete phrase before looking for additional, unanswered measures.
    residual = re.sub(r'\bstatutory\s+(?:earnings\s+per\s+share|EPS)\b', '', question, flags=re.I)
    if metric_tags(residual)-allowed_tags: return None
    # A Group table is not a parent-company or segment table. Explicit note
    # requests need that note's evidence, not a nearby summary-table substitute.
    if re.search(r'\bparent\b|\bCompany separately\b|\bNote\s+\d+|\boriginal(?:ly)?\b|\bsegment\b|\bhalf.year\b|\bquarter\b|\bcalendar\b',question,re.I): return None
    years = context['years']
    if not years or not set(years) <= {2024,2025}: return None
    op = operation_plan(question)
    if op['kind'] == 'unsupported': return None
    parts = []
    for metric in metrics:
        eligible = [t for t in tables() if metric in t['rows'] and set(years) <= set(t['years'])
                    and t['source']['report_year'] == max(years)]
        if len(eligible) != 1: return None
        table = eligible[0]; source = table['source']; label = {**ROWS, **EPS_ROWS}[metric]
        row = label + ' | ' + ' | '.join(f'FY{y}: {v}' for y,v in zip(table['years'],table['rows'][metric]))
        row += ' | '+table['unit']+' | NAB Group statutory basis'
        cells=[]; claims=[]
        for year in sorted(years):
            col=table['years'].index(year); uid=f"{source['document_id']}:full:p{source['pdf_page']:03}:statement:{metric}"
            cell=BoundCell(metric,'NAB',table['rows'][metric][col],table['rows'][metric][col],table['unit'],
                'statutory','Group','annual',f'{year}-09-30',source['report_year'],col+1,uid,(),uid,source,row,
                'two_pdf_extractors_agree; financial_performance_totals_reconciled' if metric in ROWS else 'two_pdf_extractors_agree_on_Group_EPS_year_columns')
            cells.append(cell)
            claims.append({'text':f'NAB {label}: {cell.value} {cell.unit} in FY{year}, statutory Group basis.',
                           'cell':cell.payload(),'presentation':presentation(cell,op),
                           'evidence':[{'source_id':uid,'source':source,'quote':row}]})
        calculations=[]; issues=[]
        if op['kind'] in ('change','year_difference'):
            try: calculations.append(calculate(cells,op))
            except ValueError as error: issues.append(str(error))
        parts.append({'claims':claims,'calculations':calculations,'issues':issues})
    notes=['Additional statement rows were checked against two PDF extractors. Source-reported signs and Group/statutory scope are retained.']
    if len(years)>1: notes.append('Both years come from the later annual report, retaining its comparative presentation. An earlier original disclosure can differ.')
    return {'question':question,'route':'numeric','generation':{'status':'skipped','reason':'Checked source table and Python Decimal arithmetic.'},
            'answer':{'status':'partial_answer' if any(p['issues'] for p in parts) else 'source_bound_answer',
                      'parts':parts,'limitations':notes},'coverage':{'kind':'additional_statutory_statement_rows'}}


def literal_result(question, table, texts, method):
    source=table['source']
    return {'question':question,'route':'numeric','generation':{'status':'skipped','reason':method},
            'coverage':{'kind':method},'answer':{'status':'source_bound_answer',
                'summary_replaces_detail':True,
                'summary_statements':[{'text':t,'citations':[source],'kind':'calculation'} for t in texts],
                'source_excerpts':[{'source':source,'heading':method,'excerpts':[{
                    'source_id':f"{source['document_id']}:full:p{source['pdf_page']:03}:checked_table",
                    'quote':'\n'.join(k.replace('_',' ')+': '+', '.join(f'FY{y}: {v}' for y,v in zip(table['years'],values))+' '+table['unit']
                                      for k,values in table['rows'].items())}]}],
                'limitations':['Group figures, with source report year and period retained. Two extractors agree and the disclosed accounting totals reconcile.']}}


def segment_answer(question,context,reconcile):
    if context['banks']!=['NAB'] or len(context['years'])!=1:return None
    if not reconcile and re.search(r'\bstatutory\b',question,re.I):return None
    notes=re.findall(r'\bNote\s+(\d+)',question,re.I)
    if notes and set(notes)!={'2'}:return None
    if re.search(r'\bparent\b|\bPersonal Banking\b|\bBusiness and Private\b|\bNew Zealand\b|\bCorporate and Institutional\b|\bhalf.year\b|\bquarter\b',question,re.I):return None
    year=context['years'][0]
    found=[t for t in tables() if t.get('kind')=='segment' and t['years']==[year] and t['source']['report_year']==year]
    if len(found)!=1:return None
    t=found[0];v={k:values[0] for k,values in t['rows'].items()}
    if reconcile:
        text=(f"NAB Group FY{year}: cash earnings {v['cash_earnings']}, hedging and fair-value adjustment {Decimal(v['hedging_adjustment']):+f}, "
              f"and other non-cash items {Decimal(v['other_non_cash_adjustments']):+f} sum to {v['continuing_owners_profit']} attributable to owners from continuing operations. "
              f"Adding the signed discontinued-operations adjustment {Decimal(v['discontinued_owners_loss']):+f} gives statutory profit attributable to owners of {v['statutory_owners_profit']}. "
              'All figures are AUD million; adjustments retain their source signs. Both equations have been checked with Decimal arithmetic.')
    else:text=f"NAB Group underlying profit in FY{year} was {v['underlying_profit']} AUD million, as disclosed in Note 2's Total Group column. This is not statutory NPAT or cash earnings."
    return literal_result(question,t,[text],'checked_segment_reconciliation' if reconcile else 'checked_underlying_profit')


def reconciliation_answer(question,context):
    if context['banks']!=['NAB'] or len(context['years'])!=1:return None
    if re.search(r'\bparent\b|\bhalf.year\b|\bquarter\b',question,re.I):return None
    if re.search(r'\breconcil\w*\b',question,re.I) and re.search(r'\bcash earnings\b',question,re.I) and re.search(r'\bstatutory\b',question,re.I):
        return segment_answer(question,context,True)
    if (re.search(r'\bwhy\b|\bdifference\b|\breconcil\w*\b',question,re.I)
            and re.search(r'\bprofit (?:for the year|attributable to non.controlling)',question,re.I)
            and re.search(r'\bowners\b',question,re.I)):
        year=context['years'][0]
        found=[t for t in tables() if t.get('kind')=='performance' and t['source']['report_year']==year]
        if len(found)!=1:return None
        t=found[0];i=t['years'].index(year)
        total=t['rows']['statutory_total_profit'][i];owners=t['rows']['statutory_owners_profit'][i]
        nci=t['rows']['profit_attributable_to_non_controlling_interests'][i]
        return literal_result(question,t,[f'NAB Group FY{year} net profit for the year includes profit attributable to non-controlling interests. '
            f'{total} - {nci} = {owners} AUD million attributable to owners of the Company. These are different ownership scopes, not contradictory profit figures.'],
            'checked_ownership_reconciliation')
    return None
