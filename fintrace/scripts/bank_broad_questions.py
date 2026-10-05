"""Labelled alternatives for whole, unqualified numerical questions.

No financial values, answer keys or page coordinates are stored here. Explicit
subtypes, entity scopes, narrative requests and unsupported periods do not match
the bounded grammar and retain the existing checked routes.
"""
from copy import deepcopy
import re

from bank_operations_v9 import calculate, operation_plan, presentation
from bank_retrieval_v6 import request_scopes
from bank_source_cells import EPS_METRICS


def subject(question):
    # The UI appends this exact context-only line when filters fill missing
    # bank/year information. Remove the wrapper, not any user qualifier.
    text = re.sub(r'\nFor (?:CBA|NAB|FY2024|FY2025)(?:, (?:FY2024|FY2025))?\.$', '', question, flags=re.I)
    text = re.sub(r'\b(?:CBA|NAB)(?:[\u2019\x27]s)?\b', '', text, flags=re.I)
    text = re.sub(r'\b(?:in|for|during|from|to|as at|at the end of)?\s*(?:FY\s*)?20\d{2}\b', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip(' ?.!,')
    for measure, pattern in (
        ('eps', r'(?:(?:what (?:was|were|is|are)|show|give|list)(?: me)?\s+)?(?:basic |diluted )?(?:cash |statutory )?(?:EPS|earnings per share)(?: (?:from )?continuing operations| including discontinued operations)?'),
        ('income', r'(?:(?:what (?:was|were|is|are)|show|give|list)(?: me)?\s+)?income|how much income (?:did|does|has) (?:earn|earned|make|made)'),
        ('loans', r'(?:(?:what (?:was|were|is|are)|show|give|list)(?: me)?\s+)?(?:total )?loans'),
        ('margin', r'(?:(?:what (?:was|were|is|are)|show|give|list)(?: me)?\s+)?margin|how (?:did|has) margin change'),
    ):
        if re.fullmatch(pattern, text, re.I): return measure
    return None


def merge(question, branches, note, partial=False):
    parts = [deepcopy(p) for b in branches for p in b['answer'].get('parts', [])]
    useful = any(p.get('claims') for p in parts)
    complete = bool(branches) and all(b['answer']['status']=='source_bound_answer' for b in branches)
    limits = [n for b in branches for n in b['answer'].get('limitations', [])]
    return {'question': question, 'route': 'numeric', 'generation': {'status': 'skipped'},
            'answer': {'status': 'source_bound_answer' if useful and complete and not partial else 'partial_answer' if useful else 'unable_to_verify',
                       'parts': parts, 'message': note, 'important_notes': [note],
                       'limitations': list(dict.fromkeys(limits))},
            'alternatives_policy': 'literal_source_bound_variants_not_metric_equivalence'}


def eps_answer(question, context, core):
    from answer_bank_v8 import cell_claim
    evidence = core.evidence_backend.core
    records = [r for r in evidence.retriever.engine.records if r['kind']=='financial_row'
               and r['source']['company']==context['banks'][0]
               and 'basic_cash_eps' in r.get('metric_tags', [])]
    requested_basis = 'statutory' if re.search(r'\bstatutory\b', question,re.I) else 'cash' if re.search(r'\bcash\b',question,re.I) else None
    requested_style = 'diluted' if re.search(r'\bdiluted\b',question,re.I) else 'basic' if re.search(r'\bbasic\b',question,re.I) else None
    op = operation_plan(question)
    from bank_retrieval_v6 import report_vintage
    vintage = report_vintage(question, context['years'], 'find')
    parts = []
    for metric in sorted(EPS_METRICS):
        if requested_basis and requested_basis not in metric: continue
        if requested_style and not metric.startswith(requested_style): continue
        wanted = request_scopes(question, 'basic_cash_eps')
        candidates = [c for r in records for c in evidence.binder.bind(r, metric)
                      if int(c.period_end[:4]) in context['years']]
        scopes = wanted if wanted != [None] else sorted({c.scope for c in candidates})
        for scope in scopes:
            req = {'id': metric+'-'+scope, 'company': context['banks'][0], 'metric': metric,
                   'scope': scope, 'value_years': context['years'], 'report_year': vintage}
            cells, issues = evidence.binder.select(records,req,question)
            if not cells: continue
            claims = []
            for cell in cells:
                claim = cell_claim(cell,evidence.binder)
                claim['presentation'] = presentation(cell,op)
                claims.append(claim)
            calculations = []
            if op['kind'] in ('change','year_difference'):
                try: calculations.append(calculate(cells,op))
                except ValueError as error: issues.append(str(error))
            parts.append({'request':req,'claims':claims,'calculations':calculations,'issues':issues})
    # No guessed diluted result and no relabelling cash EPS as statutory EPS.
    from bank_contract_v12 import audit_bindings
    issues = audit_bindings({'answer': {'parts': parts}})
    if issues:
        return {'question':question,'route':'numeric','generation':{'status':'skipped'},
                'answer':{'status':'unable_to_verify','message':'EPS source bindings did not match the request. No substituted figure is shown.','issues':issues}}
    limits=['No missing EPS variant is inferred. Unbound variants remain a coverage limitation.']
    for part in parts:
        for claim in part['claims']:
            cell=claim['cell']; year=int(cell['period_end'][:4])
            if cell['report_year']>year:
                limits.append(f"{cell['company']} FY{year} is taken from the FY{cell['report_year']} report's comparative column. This alone does not establish that it was restated; the original disclosure may differ.")
    complete = bool(parts) and all(not p['issues'] for p in parts)
    return {'question':question,'route':'numeric','generation':{'status':'skipped'},
            'answer':{'status':'source_bound_answer' if complete else 'partial_answer' if parts else 'unable_to_verify',
                'message':('EPS variants are shown separately by basic/diluted, cash/statutory basis and operational scope. Only variants bound to literal source rows are included; this is not a promise that every EPS variant has been verified.' if parts else 'I could not bind the requested EPS variant to a checked source row. Basic/diluted and cash/statutory EPS are distinct; no neighbouring EPS figure is substituted. The full reports may contain additional disclosures.'),
                'parts':parts,'limitations':list(dict.fromkeys(limits))},
            'alternatives_policy':'literal_source_bound_eps_variants'}


def answer(question, context, core):
    measure = subject(question)
    if not measure or len(context['banks'])!=1 or not context['years'] or not set(context['years'])<={2024,2025}: return None
    if measure=='eps': return eps_answer(question,context,core)
    if measure=='loans':
        query = re.sub(r'\b(?:total )?loans\b','gross loans and acceptances',question,flags=re.I)
        return merge(question,[core.answer(query)],
            'For the broad loans question, showing the disclosed Group gross loans and acceptances, before impairment allowances. This is not net loans or a housing/business lending segment.')
    if measure=='margin':
        query = re.sub(r'\bmargin\b','net interest margin',question,flags=re.I)
        if len(context['years'])==2 and re.search(r'\bchange\b',question,re.I): query += ' Calculate the change.'
        return merge(question,[core.answer(query)],
            'Margin can mean different measures. The verified alternative below is net interest margin, not profit margin. A change in this rate is shown in percentage points, not relative percentage growth.',partial=True)
    # Income is broader than any one KPI. Show labelled available totals rather
    # than claiming that an income component is the bank's entire income.
    bank=context['banks'][0]
    years=' and '.join('FY'+str(y) for y in context['years'])
    branches=[core.answer(f'What was {bank} total operating income in {years}?')]
    if bank=='NAB':
        from bank_statement_tables import answer as statement_answer
        for metric in ('statutory net operating income','net interest income'):
            result=statement_answer(f'What was NAB {metric} in {years}?',context)
            if result: branches.append(result)
    return merge(question,branches,
        'Income was unspecified. Showing separately labelled available operating-income measures. Net interest income is a component, not another total to add. Cash/statutory income and profit are different measures; this is not an exhaustive list of all income disclosures.',partial=True)
