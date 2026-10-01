"""Wording tolerance without financial-value or measure substitution.

Known financial requests use the checked evidence backend irrespective of their
opening verb. The model remains useful for unfamiliar narrative questions.
"""
import re
from bank_contract_v12 import metric_tags

# Explicit spelling repairs only. Never fuzzy-match an unknown metric, bank,
# year, unit, reporting basis or project name to a supported neighbour.
SPELLING = {
    'proift': 'profit', 'proft': 'profit', 'profitt': 'profit',
    'statutroy': 'statutory', 'statutry': 'statutory',
    'earings': 'earnings', 'intrest': 'interest', 'divident': 'dividend',
    'cusotmer': 'customer', 'depostis': 'deposits',
}


def normalise_query(question):
    changes = []
    def replace(pattern, replacement):
        nonlocal question
        def apply(match):
            value = replacement(match) if callable(replacement) else replacement
            if value != match.group():
                changes.append({'original': match.group(), 'normalised': value})
            return value
        question = re.sub(pattern, apply, question, flags=re.I)
    replace(r'\b(?:' + '|'.join(SPELLING) + r')\b', lambda m: SPELLING[m.group().lower()])
    replace(r'\bcommbank\b', 'CBA')
    # Expand short financial years before scope checks, including unsupported
    # years. FY26 must not silently become a default FY2024/FY2025 lookup.
    replace(r'\bFY\s*(\d{2})\b', lambda m: 'FY20' + m[1])
    replace(r"\bwhat['\u2019]?s\b", 'what is')
    replace(r'^\s*(?:(?:hey|hi)[, ]+)?(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:please\s+)?(?=(?:tell|show|give|list|what|how|compare|calculate|explain|define)\b)', '')
    # Interpret only a whole, unqualified earnings question as profit. Do not
    # turn money from a named product, disposal or cash-flow activity into NPAT.
    plain_money=re.fullmatch(r'how much money (?:did|does|has) (CBA|NAB) (?:make|made|earn|earned)'
        r'((?:\s+(?:in|during|for)\s+(?:the\s+)?(?:FY)?20\d{2}(?:\s+financial year)?)?)\s*[?.]?',question,re.I)
    if plain_money:
        interpreted=f'What was {plain_money[1]} profit{plain_money[2]}?'
        changes.append({'original':question,'normalised':interpreted,'assumption':'Money made is interpreted as profit; reporting bases remain labelled.'})
        question=interpreted
    replace(r'\bpay shareholders per share\b','report as dividend per share')
    replace(r'\bdividend did (CBA|NAB) pay per share\b',lambda m:m[1]+' dividend per share')
    # A single FY2025 movement normally compares with FY2024. Make that
    # interpretation visible, and never infer a half-year/calendar comparison.
    years=set(re.findall(r'20\d{2}',question))
    movement=re.search(r'\b(?:grow|grew|growth|rise|rose|fall|fell|increase|decrease|move|moved|change|compare)\b',question,re.I)
    narrative=re.search(r'\b(?:why|explain|reason|driver|factor|mean|define|forecast|predict|will)\w*\b',question,re.I)
    if (years=={'2025'} and known_measure(question) and movement and not narrative
            and not re.search(r'\b(?:quarter|half.year|six months|calendar|monthly|signed|subtract|minus)\b',question,re.I)):
        interpreted=re.sub(r'\bthe year before\b|\bprevious year\b','FY2024',question,flags=re.I)
        interpreted+=' Calculate the change from FY2024 to FY2025.'
        changes.append({'original':question,'normalised':interpreted,'assumption':'Annual movement interpreted as FY2024 to FY2025.'})
        question=interpreted
    return question, changes


def generic_loan_lookup(question):
    # Positive allow-list for a whole unqualified question. Named borrower,
    # subsidiary, net, segment and related-party requests must not enter this
    # labelled-alternative shortcut.
    return bool(re.fullmatch(r'(?:what (?:was|were|is|are)\s+)?(?:CBA|NAB)(?:[\u2019\x27]s)?\s+total loans'
        r'(?:\s+(?:at the end of|at the end|in|for|as at)\s+(?:the\s+)?(?:FY)?20\d{2})?\s*[?.]?',question,re.I))


def known_measure(question):
    return bool(metric_tags(question) or re.search(r'\b(?:profit|NPAT|earnings|net income)\b', question, re.I))


def explanation_subject(question):
    """Literal subject matching for prose relevance, never a numerical alias."""
    if not re.search(r'\bwhy\b|\breasons?\b|\bdrivers?\b|\bfactors?\b|\bexplain\b', question, re.I):
        return None
    subjects = (
        r'\boperating (?:expenses?|costs?)\b',
        r'\b(?:credit impairment|loan impairment|credit.loss) (?:charges?|expenses?)\b',
        r'\bnet interest income\b', r'\bother operating income\b',
        r'\b(?:staff|personnel) (?:expenses?|costs?)\b',
        r'\b(?:information technology|IT|technology)(?: services?)? (?:expenses?|costs?)\b',
    )
    found = [p for p in subjects if re.search(p, question, re.I)]
    return found[0] if len(found) == 1 else None


def definition_request(question):
    from answer_bank_release import conceptual
    if conceptual(question):
        return True
    if re.search(r'\bdefin(?:e|ition)\b|\bmeaning\b|\bstand(?:s)? for\b|\bwhat\b.*\bmean\b', question, re.I):
        return True
    # An unqualified "what is NIM?" asks for meaning, not a guessed amount.
    return (known_measure(question)
            and bool(re.match(r'^\s*what (?:is|are)\b', question, re.I))
            and not re.search(r'\b(?:FY\s*)?20\d{2}\b|\b(?:CBA|NAB|Commonwealth|National Australia)\b', question, re.I)
            and not re.search(r'\b(?:change|growth|amount|value|figure|total)\b', question, re.I))


def checked_numeric_request(question):
    """A route choice, never permission to skip basis/scope/source checks."""
    question, _ = normalise_query(question)
    if not known_measure(question) or definition_request(question):
        return False
    # Narrative intent takes precedence, including mixed requests handled by
    # split_mixed. A numeric change ("how did NIM change?") is not a why question.
    if re.search(r'\b(?:why|mean\w*|defin\w*|explain\w*|reason\w*|driv\w*|factor\w*|'
                 r'cause\w*|prove\w*|telling|imply|indicate|suggest|contribut\w*|'
                 r'better|best|good|bad|enough|healthy|sustainable|same|equivalent|'
                 r'distinction|summari\w*|summary|overview|strategy|outlook|reconcil\w*)\b', question, re.I):
        return False
    if re.search(r'\bhow\b', question, re.I) and not re.search(
            r'\bhow (?:much|many|far)\b|\b(?:change\w*|grow\w*|grew|rise|rose|increase\w*|decrease\w*|fall|fell|mov\w*)\b', question, re.I):
        return False
    return True
