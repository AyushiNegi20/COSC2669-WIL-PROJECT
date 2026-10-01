"""Question-to-evidence contracts. No reference answers or financial values."""
import re
from bank_retrieval_v6 import explicit_metrics
from bank_retrieval_service_v9 import Planner as PreviousPlanner


PROFIT = r'\b(?:net profit(?: after tax)?|profit|NPAT|earnings)\b'
ALIASES = {
    'cash_profit': (r'\bcash\s+(?:NPAT|net profit(?: after tax)?|profit|earnings)(?!\s+per share)', 'cash profit'),
    'statutory_npat': (r'\bstatutory\s+(?:NPAT|net profit(?: after tax)?|profit|earnings)', 'statutory net profit after tax'),
    'basic_cash_eps': (r'\b(?:basic cash (?:earnings per share|EPS)|cash basic (?:earnings per share|EPS))\b', 'basic cash EPS'),
    'dividend_per_share': (r'\bfully franked dividend(?! per share)\b', 'fully franked dividend per share'),
    'operating_income': (r'\b(?:revenue|operating revenue|net operating income|total operating income)\b', 'total operating income'),
    'operating_expenses': (r'\b(?:costs of running the bank|operating costs)\b', 'operating expenses'),
    'credit_impairment': (r'\b(?:loan.loss expense|credit.loss charge)\b', 'credit impairment charge'),
    'gross_loans': (r'\b(?:total lending outstanding|total loans and acceptances)\b', 'gross loans and acceptances'),
    'customer_deposits': (r'\b(?:money deposited by customers|deposits from customers)\b', 'customer deposits'),
    'total_assets': (r'\b(?:all group assets|balance.sheet total of assets)\b', 'total assets'),
}

# A subtype or related quantity must never be silently replaced with its parent.
UNSUPPORTED = [
    (r'\b(?:share|stock) price\b|market cap', 'Market prices are not established by this financial-report corpus.'),
    (r'\b(?:housing|home|mortgage|business|personal) (?:loans?|lending)\b', 'This asks for a lending segment, not total gross loans. Segment lending is outside the validated metric scope.'),
    (r'\b(?:individually|collectively) assessed\b', 'This asks for an impairment component, not the total charge. Component figures are outside the validated metric scope.'),
    (r'\bnet interest income\b', 'Net interest income is a money amount, not net interest margin. The income amount is outside the validated metric scope.'),
    (r'\b(?:profit before|pre.tax profit|profit margin|gross profit|operating profit|EBITDA|EBIT)\b', 'This profit measure is outside the validated metric scope; cash or statutory NPAT is not a substitute.'),
    (r'\b(?:capitalised|capitalized) software\b|effective tax rate|cash and cash equivalents', 'This balance or rate is outside the validated metric scope, even if its page is present.'),
    (r'\b(?:diluted|statutory) (?:EPS|earnings per share)\b', 'Only basic cash EPS is validated. Diluted or statutory EPS cannot be replaced with cash EPS.'),
    (r'\b(?:interim|final) dividend\b', 'Only full-year dividend per share is validated, not a single dividend instalment.'),
    (r'dividends? paid|pay in dividends|total dividend (?:payments|paid)', 'Total cash dividends paid are not dividend per share and are outside the validated metric scope.'),
    (r'risk.weighted assets|average (?:total )?assets|net loans|loan.loss (?:allowance|provision)', 'This requests a different balance or measurement basis from the supported total; no substitute will be used.'),
]


def normalise(text):
    text = re.sub(r'\b(?:NPAT|net profit(?: after tax)?)\s+(?:on (?:a |the )?|on the )?cash basis\b', 'cash profit', text, flags=re.I)
    text = re.sub(r'\b(?:NPAT|net profit(?: after tax)?)\s+(?:on (?:a |the )?|on the )?statutory basis\b', 'statutory net profit after tax', text, flags=re.I)
    for pattern, replacement in ALIASES.values():
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def metric_tags(text):
    # The older broad statutory regex can span a second metric in a list.
    return set(explicit_metrics(normalise(text)))


def preflight(question):
    """Scope guards precede any question expansion or model call."""
    if re.search(r'\b(?:Westpac|ANZ|BHP|Tesla)\b', question, re.I):
        return 'Requested company is outside the CBA/NAB corpus.'
    # Cross-company ranking and equivalence are not supported in the current
    # scope. If both issuers are named in one request, decline rather than
    # assemble a comparison; each bank must be asked about separately.
    if (re.search(r'\b(?:CBA|CommBank|Commonwealth(?:\s+Bank)?)\b', question, re.I)
            and re.search(r'\b(?:NAB|National\s+Australia(?:\s+Bank)?)\b', question, re.I)):
        return ('Cross-company comparison, ranking or equivalence across CBA and NAB is not '
                'supported in the current scope. Ask about one bank at a time.')
    if re.search(r'\b(?:housing|home|mortgage)\b', question, re.I) and re.search(r'\b(?:loans?|lending)\b', question, re.I):
        return 'A housing or mortgage segment cannot be replaced with the Group gross-loan total. Segment lending is not validated.'
    conceptual = bool(re.search(r'\b(?:mean|definition|same|distinction|defined)\b', question, re.I))
    for pattern, reason in UNSUPPORTED:
        if re.search(pattern, question, re.I):
            # A source definition can mention an excluded concept to distinguish it.
            if conceptual and re.search(r'cash profit.*cash flow|cash flow.*cash profit', question, re.I):
                continue
            return reason
    return None


def prepare(question):
    text = normalise(question)
    notes = []
    text = re.sub(r'\bnet income\b', 'profit', text, flags=re.I)
    text = re.sub(r'\bearn\b', 'report as profit', text, flags=re.I)
    if re.search(r'^\s*is\b.*(?:LCR|liquidity coverage ratio).*(?:single|day.end|daily)', text, re.I):
        text = 'Definition of the reporting basis: ' + text
    tags = metric_tags(text)
    ambiguous_profit = bool(re.search(PROFIT, text, re.I)) and not tags.intersection({'cash_profit', 'statutory_npat', 'basic_cash_eps'})
    if ambiguous_profit:
        # This is a labelled expansion, never an assumption that the measures agree.
        text = re.sub(PROFIT, 'cash profit and statutory net profit after tax', text, flags=re.I)
        text = re.sub(r'(?:not|never|haven.t|have not) (?:yet )?(?:chosen|selected|decided)|undecided|not sure which|unsure which', '', text, flags=re.I)
        notes.append('Profit was unspecified. Showing cash profit and statutory NPAT separately, with their disclosed scopes; they are not interchangeable.')
    if 'basic_cash_eps' in metric_tags(text) and not re.search(r'cash|basic', question, re.I):
        notes.append('EPS was unspecified. Only basic cash EPS is supported here; statutory and diluted EPS have not been verified.')
    if 'nim' in metric_tags(text) and not re.search(r'cash|statutory', question, re.I):
        notes.append('NIM was unspecified. Cash and statutory variants are checked separately; only source-bound variants are displayed.')
    # A one-year growth question normally requests the preceding-year comparison.
    # Make the interpretation visible and let the existing period guard reject gaps.
    years = sorted(set(int(y) for y in re.findall(r'(?<!\d)20\d{2}(?!\d)', text)))
    movement = bool(re.search(r'\b(?:change|grew|grow|growth|rose|rise|increase|decrease|fell|fall)\b', text, re.I))
    prose = bool(re.search(r'^\s*(?:why|explain)|what (?:factors|caused|drove)', text, re.I))
    if movement and len(years) == 1 and not prose and not re.search(r'comparative|report|restat', text, re.I):
        text += f' Compare FY{years[0]-1} to FY{years[0]} using percentage change.'
        notes.append('Interpreted growth in the named year as change from the preceding financial year.')
    elif movement and len(years) == 2 and not prose and not re.search(r'no percent|not (?:a )?percent|absolute only', text, re.I):
        text += ' Include percentage change.'
    return text, notes


class Planner(PreviousPlanner):
    def plan(self, question, vector):
        plan = super().plan(question, vector)
        # Publication year is metadata, not an additional requested value year.
        vintage = plan.get('report_year')
        if vintage and re.search(r'\bcomparative\b|\bfor FY\s*20\d{2}\b', question, re.I):
            values_only = re.sub(r'(?:FY\s*)?20\d{2}\s+(?:report|results|publication)', '', question, flags=re.I)
            value_years = sorted(set(int(y) for y in re.findall(r'(?<!\d)20\d{2}(?!\d)', values_only)))
            if len(value_years) == 1:
                plan['value_years'] = value_years
                for request in plan.get('requests', []): request['value_years'] = value_years
                if plan['intent'] == 'compare':
                    plan['intent'] = 'find'
                    for request in plan.get('requests', []): request['intent'] = 'find'
        allowed = metric_tags(question)
        if len(allowed) == 1 and re.search(r'\bstatutory\b', question, re.I):
            for request in plan.get('requests', []):
                if request['metric'] in ('operating_income', 'operating_expenses', 'credit_impairment', 'nim'):
                    request['basis'] = 'statutory'
        if plan['behavior'] == 'answer' and plan['intent'] not in ('define', 'explain', 'reconcile', 'summary'):
            if not allowed or any(r['metric'] not in allowed for r in plan['requests']):
                plan.update(behavior='abstain', reason='The requested measure has no verified mapping to a supported metric. A semantically similar number is not sufficient evidence.', requests=[])
        return plan


def audit_bindings(result):
    """Validate the cell against the request, not just generated text against cells."""
    issues = []
    for part in result['answer'].get('parts', []):
        req = part['request']
        for claim in part.get('claims', []):
            cell = claim['cell']
            for field in ('metric', 'company'):
                if cell[field] != req[field]: issues.append('Bound cell does not match requested ' + field)
            if int(cell['period_end'][:4]) not in req['value_years']:
                issues.append('Bound cell does not match requested value year')
            if req.get('report_year') and cell['report_year'] != req['report_year']:
                issues.append('Bound cell does not match requested report vintage')
            if req.get('scope') and cell['scope'] != req['scope']:
                issues.append('Bound cell does not match requested scope')
            if req.get('basis') and cell['basis'] != req['basis']:
                issues.append('Bound cell does not match requested basis')
            expected = {'cash_profit': 'cash', 'statutory_npat': 'statutory', 'basic_cash_eps': 'basic cash'}.get(req['metric'])
            if expected and cell['basis'] != expected:
                issues.append('Bound cell does not match requested reporting basis')
    return sorted(set(issues))
