"""Subject and entity-scope screening, not proof that an answer is complete.

These patterns select evidence, never map one financial measure into another.
Run before selection and before a timeout fallback can display quotations.
"""
import re

SUBJECTS = (
    (r'\b(?:net interest margin|NIM)\b', r'\b(?:net interest margin|NIM)\b'),
    (r'\bnet interest income\b', r'\bnet interest income\b'),
    (r'\bcost[ -]to[ -]income\b', r'\bcost[ -]to[ -]income\b|\bexpense[ -]to[ -]income\b'),
    (r'\b(?:return on (?:average )?equity|ROE)\b', r'\breturn on (?:average )?equity\b|\bROE\b'),
    (r'\b(?:capital position|capital strength|capital adequacy|capital ratio|CET1|tier [12])\b',
     r'\b(?:capital (?:position|adequacy|ratio|buffer)|CET1|common equity tier|tier [12] capital|regulatory capital)\b'),
    (r'\b(?:cash profit|statutory profit|net profit|NPAT|profit|cash earnings)\b',
     r'\b(?:profit|NPAT|cash earnings)\b'),
    (r'\b(?:dividend|dividends)\b',r'\bdividends?\b'),
    (r'\b(?:loans?|lending)\b',r'\bloans?\b|\blending\b'),
    (r'\bcustomer deposits\b',r'\bcustomer deposits\b|\bdeposits from customers\b'),
    (r'\b(?:staff|personnel) (?:costs?|expenses?)\b',r'\b(?:staff|personnel) (?:costs?|expenses?)\b|\bwage\w*\b|\bsalar\w*\b'),
    (r'\boperating (?:costs?|expenses?)\b',r'\boperating (?:costs?|expenses?)\b'),
    (r'\b(?:credit|loan) impairment\b',r'\b(?:credit|loan) impairment\b'),
    (r'\b(?:software|intangible)\b.*\bamorti[sz]\w*\b|\bamorti[sz]\w*\b.*\b(?:software|intangible)\b',
     r'\b(?:software|intangible)\b.*\bamorti[sz]\w*\b|\bamorti[sz]\w*\b.*\b(?:software|intangible)\b'),
)


def relevance(question, text):
    """Return (allowed, reason). A pass remains a heuristic relevance screen."""
    requested=[p for q,p in SUBJECTS if re.search(q,question,re.I)]
    if requested and not any(re.search(p,text,re.I|re.S) for p in requested):
        return False,'The passage does not discuss a requested financial subject.'
    if re.search(r'\bcapital position\b',question,re.I) and re.search(r'strengthen|weaken|improv|deterior|change',question,re.I):
        capital=r'(?:CET1|common equity tier 1|[Tt]ier 1 capital|capital ratio)'
        movement=r'(?:increased|decreased|declined|fell|rose|improved|reduced|increase of|decrease of|reduction of)'
        clause=r'(?:[^.]|\.(?=\d))'
        if not re.search(capital+clause+r'{0,180}\b'+movement+r'\b|\b'+movement+clause+r'{0,100}'+capital,text,re.I):
            return False,'Regulatory requirements alone do not establish a change in the bank capital position.'
    # A related-party or remuneration disclosure is not a Group lending total.
    restricted=r'\bKMP\b|key management personnel|related parties|non.executive directors|Group Executives'
    if re.search(r'\bloans?|\blending',question,re.I) and re.search(restricted,text,re.I) and not re.search(restricted,question,re.I):
        return False,'Related-party lending is not Group lending.'
    if re.search(r'\b(?:profit|NPAT|cash earnings)\b',question,re.I):
        if re.search(r'\b(?:app|application|download|device)\b',text,re.I) and not re.search(
                r'\b(?:profit|NPAT|cash earnings)\b.{0,80}(?:\$\s*\d|\d[\d,.]*\s*(?:million|billion|%))',text,re.I):
            return False,'An application footnote does not establish reported profit.'
    return True,'Subject/scope screen passed; completeness still requires review.'
