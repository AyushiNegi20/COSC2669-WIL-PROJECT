"""Developer-authored metamorphic cases; not an independent answer key."""

METRICS = {
    'cash_profit': 'cash profit', 'statutory_npat': 'statutory net profit after tax',
    'operating_income': 'total operating income', 'operating_expenses': 'operating expenses',
    'credit_impairment': 'credit impairment charge', 'nim': 'net interest margin',
    'basic_cash_eps': 'basic cash EPS', 'dividend_per_share': 'dividend per share',
    'total_assets': 'total assets', 'gross_loans': 'gross loans and acceptances',
    'customer_deposits': 'customer deposits', 'cet1': 'CET1', 'lcr': 'LCR',
}


def families():
    for bank in ('CBA', 'NAB'):
        for year in (2024, 2025):
            for metric, label in METRICS.items():
                yield {
                    'id': f'{bank}_{year}_{metric}', 'metric': metric, 'bank': bank,
                    'year': year, 'baseline': f'What was {bank} {label} in FY{year}?',
                    'variants': [f'what is {bank} {label} in year {year}',
                                 f'{bank} FY{str(year)[2:]} {label}?',
                                 f'Could you please tell me {bank} {label} for {year}?'],
                }
    for bank in ('CBA', 'NAB'):
        for metric in ('cash_profit', 'basic_cash_eps', 'nim', 'gross_loans'):
            label = METRICS[metric]
            yield {
                'id': f'{bank}_change_{metric}', 'metric': metric, 'bank': bank,
                'calculation': True,
                'baseline': f'Calculate the change in {bank} {label} from FY2024 to FY2025.',
                'variants': [f'How did {bank} {label} change from FY2024 to FY2025?',
                             f'Please work out the change in {bank} {label} between FY24 and FY25.'],
            }


def controls():
    for bank in ('CBA', 'NAB'):
        for label in ('net interest income', 'housing lending', 'underlying profit',
                      'statutory EPS', 'individually assessed credit impairment charge'):
            yield {'id': f'{bank}_unsupported_{label.replace(" ", "_")}', 'kind': 'guard',
                   'question': f'please tell me {bank} {label} in FY2025'}
        yield {'id': f'{bank}_future', 'kind': 'guard',
               'question': f'What will {bank} profit be next year?'}
        yield {'id': f'{bank}_period', 'kind': 'guard',
               'question': f'{bank} cash profit FY2026?'}
        yield {'id': f'{bank}_short_future_year', 'kind': 'guard',
               'question': f'{bank} cash profit FY26?'}
        yield {'id': f'{bank}_typo', 'kind': 'lookup', 'metrics': ['cash_profit', 'statutory_npat'],
               'bank': bank, 'year': 2025, 'question': f'whats {bank} proift fy25'}
        yield {'id': f'{bank}_typo_basis', 'kind': 'lookup', 'metrics': ['statutory_npat'],
               'bank': bank, 'year': 2024, 'question': f'{bank} statutroy profit fy24?'}
    yield {'id': 'other_bank', 'kind': 'guard', 'question': 'What is Westpac profit in 2025?'}
    yield {'id': 'alias_override', 'kind': 'lookup', 'metrics': ['cash_profit', 'statutory_npat'],
           'bank': 'CBA', 'year': 2025, 'question': 'whats commbank profit fy25',
           'scope': {'company': 'NAB', 'year': '2024'}}
    yield {'id': 'filter_context', 'kind': 'lookup', 'metrics': ['cash_profit', 'statutory_npat'],
           'bank': 'NAB', 'year': 2024, 'question': 'tell me profit',
           'scope': {'company': 'NAB', 'year': '2024'}}
    yield {'id': 'follow_bank', 'kind': 'lookup', 'metrics': ['cash_profit', 'statutory_npat'],
           'bank': 'NAB', 'year': 2025, 'question': 'And NAB?',
           'previous_question': 'what is CBA profit in year 2025'}
    yield {'id': 'follow_year', 'kind': 'lookup', 'metrics': ['cash_profit', 'statutory_npat'],
           'bank': 'CBA', 'year': 2024, 'question': 'And in 2024?',
           'previous_question': 'what is CBA profit in year 2025'}
    yield {'id': 'new_subject', 'kind': 'lookup', 'metrics': ['cash_profit', 'statutory_npat'],
           'bank': 'CBA', 'year': 2025, 'question': 'what is CBA profit in year 2025',
           'previous_question': 'Where is NAB putting more money in 2024?'}


NARRATIVE = [
    {'id': 'cba_definition', 'kind': 'definition', 'question': 'Could you explain what cash profit means in CBA FY2025?'},
    {'id': 'nab_definition', 'kind': 'definition', 'question': 'What does NAB cash earnings mean in FY2025?'},
    {'id': 'cba_reason', 'kind': 'narrative', 'question': 'Why did CBA staff expenses increase in FY2025?'},
    {'id': 'nab_reason', 'kind': 'narrative', 'question': 'Please explain why NAB staff expenses increased in FY2025.'},
    {'id': 'cba_mixed', 'kind': 'mixed', 'metrics': ['cash_profit', 'statutory_npat'], 'bank': 'CBA', 'year': 2025,
     'question': 'What is CBA profit in FY2025 and explain the reported reasons for the change.'},
    {'id': 'nab_mixed', 'kind': 'mixed', 'metrics': ['cash_profit', 'statutory_npat'], 'bank': 'NAB', 'year': 2025,
     'question': 'Tell me NAB profit in FY2025 and explain the reported reasons for the change.'},
]
