"""Bounded follow-ups and readable, source-backed paragraphs.

No answer keys, report constants or model-generated arithmetic are used here.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re

LABELS = {
    'cash_profit': 'cash profit', 'statutory_npat': 'statutory profit after tax',
    'operating_income': 'total operating income', 'operating_expenses': 'operating expenses',
    'credit_impairment': 'credit impairment charge', 'nim': 'net interest margin',
    'basic_cash_eps': 'basic cash earnings per share', 'dividend_per_share': 'dividend per share',
    'diluted_cash_eps': 'diluted cash earnings per share',
    'basic_statutory_eps': 'basic statutory earnings per share',
    'diluted_statutory_eps': 'diluted statutory earnings per share',
    'total_assets': 'total assets', 'gross_loans': 'gross loans and acceptances',
    'customer_deposits': 'customer deposits', 'cet1': 'CET1 capital ratio', 'lcr': 'liquidity coverage ratio',
}
BANK = r'\b(?:CBA|NAB|Commonwealth Bank(?: of Australia)?|National Australia Bank)\b'
YEAR = r'\b(?:FY\s*)?((?:19|20)\d{2})\b'


def followup(question, previous=None):
    """Only explicit short bank/year follow-ups inherit the prior user request."""
    if previous is not None and (not isinstance(previous, str) or len(previous) > 2000):
        raise ValueError('Previous question must be a string of at most 2000 characters')
    if not isinstance(question, str):
        raise ValueError('Question must be text')
    short = re.fullmatch(r'\s*(?:and\s+|what about\s+|how about\s+|same (?:for|in)\s+)(?:in\s+|for\s+)?'
                         r'(CBA|NAB|(?:FY\s*)?20\d{2})\s*[?.!]?\s*', question, re.I)
    if not short or not previous:
        return question, []
    value = short[1].upper()
    if value in ('CBA', 'NAB'):
        if not re.search(BANK, previous, re.I):
            return question, []
        # A multi-bank comparison is not a single-bank subject to replace.
        names = re.findall(BANK, previous, re.I)
        if len(set(n.upper() for n in names)) != 1:
            return question, []
        resolved = re.sub(BANK, value, previous, flags=re.I)
    else:
        years = set(re.findall(YEAR, previous, re.I))
        if len(years) != 1:
            return question, []
        year = re.search(r'20\d{2}', value)[0]
        resolved = re.sub(YEAR, 'FY' + year, previous, flags=re.I)
    if len(resolved) > 2000:
        raise ValueError('The resolved follow-up is too long')
    return resolved, ['Following up on your previous question: ' + resolved]


def number(value):
    try:
        numeric = Decimal(str(value))
        if not numeric.is_finite(): raise InvalidOperation
        return format(numeric, ',f')
    except InvalidOperation:
        return str(value)


def citations(cells):
    sources = {}
    for cell in cells:
        source = cell.get('source')
        if source and source.get('document_id') and source.get('pdf_page'):
            sources[(source['document_id'], source['pdf_page'])] = deepcopy(source)
    return list(sources.values())


def paragraphs(result):
    """Render existing verified cells/calculations. This function never binds data."""
    answer = result['answer']
    if answer.get('summary_replaces_detail'):
        return deepcopy(answer['summary_statements'])
    output = []
    for part in answer.get('parts', []):
        sentences, cells = [], []
        for claim in part.get('claims', []):
            cell = claim['cell']
            cells.append(cell)
            measure = LABELS.get(cell['metric'], cell['metric'].replace('_', ' '))
            value = claim.get('presentation', {}).get('value', cell['value'])
            unit = cell.get('unit', '')
            amount = number(value) + ('%' if unit == 'percent' else ' ' + unit)
            try: period = date.fromisoformat(cell['period_end']).strftime('%d %B %Y').lstrip('0')
            except (ValueError, KeyError): period = cell.get('period_end', 'the reported period')
            kind = {'annual': 'for the year ended', 'as_at': 'as at', 'quarterly_average': 'as a quarterly average ending'}.get(cell.get('period_kind'), 'for the period ending')
            basis = cell.get('basis', '').replace('_', ' ')
            scope = {'continuing': 'continuing operations', 'including_discontinued': 'including discontinued operations'}.get(cell.get('scope'), cell.get('scope', '').replace('_', ' '))
            qualification = ', '.join(v for v in (basis + ' basis' if basis else '', scope) if v)
            verb = 'were' if cell['metric'] in ('operating_expenses', 'total_assets', 'gross_loans', 'customer_deposits') else 'was'
            sentences.append(f"{cell['company']}'s {measure} {verb} {amount} {kind} {period}" + (f' ({qualification}).' if qualification else '.'))
            if claim.get('presentation', {}).get('representation') == 'expense_magnitude':
                sentences.append('This shows the expense magnitude; the signed source value remains available in the workings.')
        if sentences:
            output.append({'text': ' '.join(sentences), 'citations': citations(cells), 'kind': 'numeric'})
        for calc in part.get('calculations', []):
            delta = Decimal(str(calc['absolute_change']))
            direction = 'an increase' if delta > 0 else 'a decrease' if delta < 0 else 'no change'
            unit = 'percentage points' if calc['unit'] == 'percent' else calc['unit']
            source_cells = calc.get('source_cells', [])
            context = LABELS.get(source_cells[0].get('metric'), 'the measure') if source_cells else 'the measure'
            if calc.get('operation') == 'profit_gap':
                operands = ' minus '.join(LABELS.get(c.get('metric'), c.get('metric', 'measure')) for c in source_cells)
                text = f"The requested {operands or 'profit'} difference is {number(delta)} {unit}."
            elif calc.get('operation') == 'year_difference':
                text = f"For {context}, the difference in the requested operand order is {number(delta)} {unit}."
            else:
                bank = source_cells[0].get('company', '') if source_cells else ''
                periods = f" from {source_cells[1]['period_end']} to {source_cells[0]['period_end']}" if len(source_cells) == 2 else ''
                text = f"For {bank} {context}, the comparison{periods} gives {direction} of {number(abs(delta))} {unit}."
            if calc.get('relative_change_percent') is not None and calc['unit'] != 'percent':
                percent = Decimal(str(calc['relative_change_percent']))
                text += f' The relative change is {percent:+.2f}% (rounded).'
            if calc['unit'] == 'percent':
                if calc.get('basis_points') is not None:
                    text += f" That is {number(Decimal(str(calc['basis_points'])))} basis points (signed change)."
                text += ' This is a percentage-point change, not relative percentage growth.'
            output.append({'text': text, 'citations': citations(source_cells), 'kind': 'calculation'})
    generated = answer.get('generated_explanation', {}).get('statements', [])
    for statement in generated:
        sources = citations([{'source': c['source']} for c in statement.get('citations', [])])
        output.append({'text': statement['text'], 'citations': sources, 'kind': 'narrative'})
    if not generated and answer.get('source_excerpts'):
        # Source excerpts are explicitly attributed, never passed off as generated reasoning.
        for section in answer['source_excerpts'][:3]:
            quote = next((e['quote'] for e in section['excerpts'] if 10 <= len(e['quote'].split()) and len(e['quote']) <= 1800), None)
            if quote:
                source = section['source']
                output.append({'text': f"{source['company']}'s FY{source['report_year']} report states: \"{quote}\"",
                               'citations': [deepcopy(source)], 'kind': 'quotation'})
    return output


def present(result):
    result = deepcopy(result)
    answer = result['answer']
    prose = paragraphs(result)
    qualifications = list(dict.fromkeys([answer.get('message', '')] + answer.get('issues', []) + answer.get('limitations', []) +
                         [i for p in answer.get('parts', []) for i in p.get('issues', [])]))
    qualifications = [q for q in qualifications if q]
    if not prose:
        message = answer.get('message') or 'I could not establish an answer from the available evidence.'
        if answer['status'] == 'clarify':
            if 'Name a measure' in message or 'requested measure is not clear' in message:
                message = ('I could not connect this request to a supported figure or relevant report passage. '
                           'You can ask about a reported result, a change, or the bank\'s explanation. '
                           'Which part of the reports would you like to explore?')
            answer['message'] = message
        prose.append({'text': message, 'citations': [], 'kind': 'limit'})
        qualifications = [q for q in qualifications if q != answer.get('message') and 'Name a measure' not in q]
    important = list(answer.get('important_notes', [])) + list(answer.get('issues', [])) + [i for p in answer.get('parts', []) for i in p.get('issues', [])]
    research = result.get('narrative_request', {})
    if result.get('full_report_search'):
        important.append('CBA and NAB prose search includes all six reports\' extractable text. Retrieved passages are not an exhaustive review; unvalidated tables and image-only content are not calculation-ready.')
    elif research.get('topic') == 'performance':
        important.append('This is a supported example from selected report pages, not a ranking of every financial change.')
    elif research.get('comparative') or research.get('amount_requested'):
        important.append('The retrieved commentary does not establish the largest investment, spending increase or sector allocation. Comparable amounts have not been verified.')
    elif research:
        important.append('This covers the relevant evidence retrieved from selected pages, not a complete review of every report.')
    # Keep substantive limitations, but do not repeat the generated answer,
    # coverage notice and model disclaimer in several different UI sections.
    if research:
        shown = [p['text'] for p in prose]
        compact = []
        for q in qualifications:
            for item in q.split('\n\n'):
                if any(item.startswith(text) for text in shown): continue
                if item.startswith(('Generated wording has automated', 'CBA search includes', 'CBA full-report prose was searched', 'CBA and NAB prose search includes', 'Full-report prose was searched',
                                    'Only selected report pages were searched', 'Narrative search covers')): continue
                if item and item not in compact and item not in important: compact.append(item)
        qualifications = compact
    else:
        qualifications = [q for q in qualifications if q not in important]
    result['presentation'] = {'paragraphs': prose, 'qualifications': qualifications,
                              'important_notes': list(dict.fromkeys(important)),
                              'arithmetic': 'deterministic', 'source_values_unchanged': True}
    return result
