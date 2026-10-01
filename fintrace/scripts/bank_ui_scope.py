"""Optional UI context, kept separate from financial interpretation and evidence."""
import re


def resolve_scope(question, selection=None):
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError('Question must contain 1-2000 characters')
    if selection is None:
        selection = {}
    if not isinstance(selection, dict) or set(selection) - {'company', 'year'}:
        raise ValueError('Scope must contain only company and year')
    company, year = selection.get('company', 'all'), selection.get('year', 'all')
    if company not in ('all', 'CBA', 'NAB') or year not in ('all', '2024', '2025'):
        raise ValueError('Choose All, CBA or NAB and All, 2024 or 2025')
    selected = {'company': company, 'year': year}
    text = question.strip()
    banks = []
    if re.search(r'\bcba\b|\bcommonwealth\b|\bcommbank\b', text, re.I):
        banks.append('CBA')
    if re.search(r'\bnab\b|\bnational australia bank\b', text, re.I):
        banks.append('NAB')
    all_banks = bool(re.search(r'\b(?:both|all)(?:\s+(?:available|the|of the|two))?\s+(?:banks|companies)\b', text, re.I))
    other_bank = bool(re.search(r'\b(?:anz|westpac|macquarie|bendigo|tesla|bhp)\b', text, re.I))
    years = sorted(set(re.findall(r'\b(?:FY\s*)?((?:19|20)\d{2})\b', text, re.I)))
    years = sorted(set(years + ['20' + y for y in re.findall(r'\bfy\s*(\d{2})\b', text, re.I)]))
    all_years = bool(re.search(r'\b(?:both|all)(?:\s+(?:available|the|of the|two|financial|report))?\s+years\b', text, re.I))
    relative_year = bool(re.search(r'\b(?:current|latest|today|now|last year|previous year|next year|this year)\b', text, re.I))
    notes, additions = [], []
    if banks or all_banks or other_bank:
        effective_company = banks[0] if len(banks) == 1 and not all_banks and not other_bank else 'all'
        company_label = 'Company as specified in the question' if other_bank else ('CBA and NAB' if all_banks or len(banks) == 2 else banks[0])
        if company != 'all' and (company != effective_company or other_bank):
            notes.append('The company named in your question takes precedence over the company filter.')
    else:
        effective_company = company
        company_label = 'CBA and NAB' if company == 'all' else company
        if company != 'all':
            additions.append(company)
    if banks == ['CBA'] and not other_bank and re.search(r'\bcommbank\b', text, re.I) and not re.search(r'\bcba\b|\bcommonwealth\b', text, re.I):
        additions.append('CBA')
    if years or all_years or relative_year:
        effective_year = years[0] if len(years) == 1 and years[0] in ('2024', '2025') and not all_years and not relative_year else 'all'
        year_label = 'Period as specified in the question' if relative_year else ('FY2024 and FY2025' if all_years else ' and '.join('FY' + y for y in years))
        if year != 'all' and (year != effective_year or relative_year):
            notes.append('The period in your question takes precedence over the year filter.')
    else:
        effective_year = year
        year_label = 'FY2024 and FY2025' if year == 'all' else 'FY' + year
        if year != 'all':
            additions.append('FY' + year)
    # Never delete or replace user wording. In particular, unsupported names,
    # dates, reporting bases and report-version instructions remain visible
    # to the existing backend guards. These are defaults, not source cutoffs.
    effective_question = text
    if additions:
        context = ', '.join(additions)
        # The existing mixed-answer route copies the numeric subject into its
        # explanation branch. Put shared context there, not only after "why".
        mixed = re.search(r'\s*(?:,?\s+and\s+|;\s*)(why\b|explain\b|what (?:factors|drove|caused)\b)', text, re.I)
        from bank_query_routing import checked_numeric_request
        numeric_start = mixed and checked_numeric_request(text[:mixed.start()])
        if mixed and numeric_start:
            effective_question = text[:mixed.start()].rstrip(' ,;?') + ' for ' + context + text[mixed.start():]
        else:
            effective_question += '\nFor ' + context + '.'
    if len(effective_question) > 2000:
        raise ValueError('Please shorten the question slightly to leave room for the selected company and year.')
    return {'selected': selected,
            'effective': {'company': effective_company, 'year': effective_year},
            'summary': company_label + ' / ' + year_label,
            'notes': notes, 'effective_question': effective_question}
