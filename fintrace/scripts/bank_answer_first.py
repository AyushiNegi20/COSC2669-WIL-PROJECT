"""Resolve missing report context with labelled available alternatives.

This does not infer a metric, a reporting basis or an arithmetic operand.
"""
from copy import deepcopy
import re
from bank_retrieval import ROOT, read
from bank_contract_v12 import metric_tags
from bank_retrieval_v5 import query_plan, normalise_question


def available_context(question):
    text = normalise_question(question)[0]
    plan = query_plan('Explain: ' + text)
    documents = read(ROOT / 'config/banking_sources.json')['documents']
    banks = sorted({d['company'] for d in documents})
    years = sorted({d['report_year'] for d in documents})
    return {'text': text, 'plan': plan, 'banks': plan['companies'] or banks,
            'years': plan['value_years'] or years,
            'defaults': ([f'No bank was specified; showing {" and ".join(banks)} separately.'] if not plan['companies'] else [])
                + ([f'No year was specified; showing available report years {" and ".join(map(str, years))}, not live or current-year results.'] if not plan['value_years'] else [])}


def numeric_alternatives(question, answer):
    if not (metric_tags(question) or re.search(r'\bprofit\b|\bearnings\b', question, re.I)):
        return None
    if re.search(r'\bwhy\b|\bexplain\b|\bdefine\b|\bmeaning\b|what (?:does|do).*mean', question, re.I):
        return None
    context = available_context(question)
    if context['plan']['behavior'] == 'abstain' or not context['defaults']:
        return None
    # Missing years in arithmetic are not safe operands to invent. A yearless
    # change can use the whole available window, but its interpretation is explicit.
    if re.search(r'last year|previous year|today|current|latest|\bnow\b|from\s+[\d,]+\s+to\s+[\d,]+', question, re.I):
        return None
    movement = bool(re.search(r'\b(?:change|growth|grew|grow|increase|decrease|compare|difference)\b', question, re.I))
    if movement and context['plan']['value_years']:
        return None
    if re.search(r'\b(?:minus|plus|subtract|divide|ratio|sum)\b', question, re.I):
        return None
    branches = []
    for bank in context['banks']:
        if movement:
            queries = [f'{context["text"]} For {bank}, compare FY{context["years"][0]} to FY{context["years"][-1]}.']
        elif len(context['plan']['value_years']) > 1:
            queries = [f'{context["text"]} For {bank}.']
        else:
            queries = [f'{context["text"]} For {bank}, FY{year}.' for year in context['years']]
        for query in queries:
            branches.append(answer(query))
    parts = [deepcopy(p) for branch in branches for p in branch['answer'].get('parts', [])]
    useful = any(p.get('claims') for p in parts)
    complete = useful and all(b['answer']['status'] == 'source_bound_answer' for b in branches)
    notes = context['defaults'][:]
    if movement:
        notes.append(f'Interpreting the unspecified comparison window as FY{context["years"][0]} to FY{context["years"][-1]}.')
    missing = [b['answer'].get('message', 'A requested alternative was unavailable.')
               for b in branches if b['answer']['status'] != 'source_bound_answer']
    return {'question': question, 'answer': {
        'status': 'source_bound_answer' if complete else 'partial_answer' if useful else 'unable_to_verify',
        'message': ' '.join(notes), 'parts': parts, 'limitations': list(dict.fromkeys(missing)),
    }, 'interpretation': {'notes': notes, 'subquestions': [b.get('question') for b in branches]},
        'branch_status': [b['answer']['status'] for b in branches]}
