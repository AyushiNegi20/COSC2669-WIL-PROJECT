"""Bounded interpretation repairs over the frozen simplified candidate.

No answer values, reference pages or evaluation keys are runtime inputs.
Source binding, retrieval ranking and arithmetic remain unchanged.
"""
import argparse
from copy import deepcopy
import json
import re
from time import perf_counter

from answer_bank_simplified import Backend as SimplifiedBackend
from answer_bank_v12 import EvidenceBackend as FrozenEvidence, stopped
from answer_bank_v10 import Backend as NarrativeEvidence
from answer_bank_v9 import display
from bank_contract_v12 import UNSUPPORTED, metric_tags, normalise
from bank_narrative_routing import narrative_decision, narrative_evidence
from bank_answer_first import numeric_alternatives
from bank_research_answer import ResearchClient, render_research


# Distinct financial quantities, not aliases for nearby supported totals.
EXCLUSIONS = UNSUPPORTED + [
    (r'\b(?:underlying|adjusted|normalised|normalized) (?:profit|NPAT|earnings)(?!\s+per share)\b',
     'This named adjusted or underlying measure is not a validated cash/statutory profit alias. No neighbouring profit figure is substituted.'),
    (r'\b(?:credit|debt|issuer) ratings?\b',
     'Credit ratings are outside the supported financial measures; these reports do not establish a current rating.'),
    (r'\b(?:income )?tax (?:expense|charge|paid|benefit)\b',
     'Tax expense, tax benefits and tax paid are outside the validated metric scope.'),
    (r'\b(?:how much tax|tax\s+(?:did|does|has|was)\b.*?\b(?:pay|paid)|tax payments?)\b',
     'Tax paid is outside the validated numerical scope. This does not mean the reports contain no tax information; no tax-expense or profit figure is substituted.'),
]
OTHER_COMPANY = r'\b(?:Westpac|ANZ|BHP|Tesla)\b'
CBA_NAME = r'\b(?:CBA|CommBank|Commonwealth(?:\s+Bank)?)\b'
NAB_NAME = r'\b(?:NAB|National\s+Australia(?:\s+Bank)?)\b'
STATEMENT = r'\b(?:income statements?|statements? of (?:profit (?:or|and) loss|comprehensive income))\b'
BASIS_METRICS = {'operating_income', 'operating_expenses', 'credit_impairment', 'nim'}


def cross_company(question):
    """True when a single request names both issuers. Cross-company ranking and
    equivalence are outside the current scope; each bank is asked separately."""
    return bool(re.search(CBA_NAME, question, re.I) and re.search(NAB_NAME, question, re.I))


def conceptual(question):
    """Conceptual comparisons are not numerical differences or growth requests."""
    if len(set(re.findall(r'(?<!\d)20\d{2}(?!\d)', question))) > 1:
        return False
    if re.search(r'\b(?:calculate|by how much|how much|percentage change|grew|growth|increased|decreased)\b', question, re.I):
        return False
    return bool(re.search(r'^\s*(?:define\b|what (?:does|do)\b.*mean|what is meant\b|'
                          r'(?:does|do)\b.{0,160}\b(?:mean|refer to|represent)\b|'
                          r'(?:what(?:\x27s| is)|explain) (?:the )?(?:difference|distinction)\b|'
                          r'(?:is|are)\b.*(?:same as|equivalent|same thing)|'
                          r'how (?:does|do)\b.*differ)|\bdefinition of\b', question, re.I))


def excluded_terms(question):
    found = []
    for pattern, reason in EXCLUSIONS:
        for match in re.finditer(pattern, question, re.I):
            found.append({'term': match.group(), 'reason': reason, 'span': match.span(), 'pattern': pattern})
    return found


def supported_remainder(question, exclusions):
    """Only split a shared-context list, never discard a calculation operand.

    Different bank/year clauses and prose are deliberately not reconstructed.
    They need explicit separate questions rather than guessed context.
    """
    if not re.search(r'\band\b|,|&', question, re.I): return None
    if re.search(r'\b(?:compare|difference|change|growth|why|ratio|minus|plus|sum|divide|divided|subtract|calculate|explain|versus|vs)\b', question, re.I): return None
    banks = re.findall(r'\bCBA\b|\bNAB\b|Commonwealth Bank(?: of Australia)?|National Australia Bank', question, re.I)
    years = re.findall(r'(?<!\d)20\d{2}(?!\d)', question)
    if len(banks) != 1 or len(years) != 1: return None
    chars = list(question)
    for item in exclusions:
        start, end = item['span']; chars[start:end] = ' ' * (end-start)
    remainder = ''.join(chars)
    if not metric_tags(remainder): return None
    remainder = re.sub(r'\s+', ' ', remainder).strip()
    remainder = re.sub(r'\b(?:and|&)\s*(?=FY|20\d{2}|in\b|for\b|[?.]|$)', '', remainder, flags=re.I)
    return remainder


def statement_request(question):
    """Preserve the explicitly requested accounting statement basis."""
    if not re.search(STATEMENT, question, re.I): return question, None
    if re.search(r'\bcash\b|\badjusted\b|\bunderlying\b', question, re.I):
        return None, 'The question combines an accounting-statement reference with an adjusted/cash basis. Ask for the statement figure and cash figure separately; neither is assumed to substitute for the other.'
    tags = metric_tags(question)
    if tags.intersection(BASIS_METRICS):
        # Multiple metrics with shared statement basis are outside this small repair.
        if len(tags) != 1:
            return None, 'Please request each income-statement measure separately so its statutory basis can be checked.'
        return 'Statutory basis. ' + question, 'The requested income statement is treated as statutory, not a cash-results KPI.'
    return question, None


def validate_statement(result, question):
    if not re.search(STATEMENT, question, re.I): return result
    cells = [c['cell'] for p in result['answer'].get('parts', []) for c in p.get('claims', [])]
    if any(c['metric'] in BASIS_METRICS and c['basis'] != 'statutory' for c in cells):
        return stopped(question, 'The retrieved figure is not on the requested statutory statement basis. No cash-basis substitute is shown.')
    return result


class EvidenceBackend:
    def __init__(self, core=None):
        self.use_cba_reports = core is None
        self.core = core if core is not None else FrozenEvidence()

    @property
    def binder(self): return self.core.binder

    def definition(self, question, exclusions):
        # Explicitly conceptual, so do not ask for a year or turn a distinction
        # into subtraction. Use the existing narrative retriever and literal units.
        query = 'Explain the definition and distinction: ' + normalise(question)
        full_sections = []
        if self.use_cba_reports:
            from bank_answer_first import available_context
            context = available_context(question)
            from bank_report_library import get_library
            for bank in context['banks']:
                for year in context['years']:
                    full_sections.extend(get_library().search(question, year, top_k=2, purpose='definition', company=bank))
        if full_sections:
            result = {'question': question, 'full_report_search': True, 'answer': {
                'status': 'evidence_answer', 'message': 'Definitions are grounded in the bank disclosures, not inferred from a nearby KPI.',
                'source_excerpts': full_sections,
                'limitations': ['These retrieved definitions are report-specific and do not establish equivalence unless the cited disclosure supports it.']}}
        elif not re.search(r'\b(?:CBA|NAB)\b|Commonwealth Bank|National Australia Bank', question, re.I):
            # A general concept can be sourced from both banks without asking
            # the user to choose. Keep bank provenance on every excerpt.
            branches = [NarrativeEvidence.answer(self.core, query + f' In {bank} reports.') for bank in ('CBA', 'NAB')]
            sections = [s for branch in branches for s in branch['answer'].get('source_excerpts', [])]
            result = {'question': question, 'answer': {
                'status': 'evidence_answer' if sections else 'unable_to_verify',
                'message': 'Definitions are drawn from the separately labelled bank disclosures. Do not assume that similarly named measures are equivalent.',
                'source_excerpts': sections,
                'limitations': ['Definitions are report-specific; this is not a numerical lookup.']}}
        else:
            result = NarrativeEvidence.answer(self.core, query)
        answer = result['answer']
        if answer.get('parts'):
            return stopped(question, 'No sourced definition was found. Numerical results cannot establish whether these concepts are equivalent.')
        sections = answer.get('source_excerpts', [])
        quotes = ' '.join(e['quote'] for s in sections for e in s['excerpts'])
        missing = [x['term'] for x in exclusions if not re.search(x['pattern'], quotes, re.I)]
        if missing:
            result = stopped(question, 'The retrieved disclosures do not define all the requested concepts: ' + ', '.join(dict.fromkeys(missing)) + '. No equivalence or substitute is inferred.')
        result['question'] = question
        result['definition_request'] = True
        return result

    def answer(self, question):
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError('Invalid question length')
        if re.search(OTHER_COMPANY, question, re.I):
            return stopped(question, 'Requested company is outside the CBA/NAB corpus.')
        if cross_company(question):
            return stopped(question, 'Cross-company comparison, ranking or equivalence across CBA and NAB is not '
                                     'supported in the current scope. Ask about one bank at a time.')
        exclusions = excluded_terms(question)
        if conceptual(question):
            return self.definition(question, exclusions)
        if exclusions:
            remainder = supported_remainder(question, exclusions)
            reasons = list(dict.fromkeys(x['reason'] for x in exclusions))
            if remainder is None:
                return stopped(question, ' '.join(reasons))
            result = deepcopy(self.answer(remainder))
            answer = result['answer']
            useful = bool(answer.get('parts') or answer.get('source_excerpts'))
            if useful: answer['status'] = 'partial_answer'
            answer['message'] = 'Only the supported portion is shown. ' + ' '.join(reasons)
            answer.setdefault('limitations', []).extend(reasons)
            answer['unanswered_parts'] = list(dict.fromkeys(x['term'] for x in exclusions))
            result['question'] = question
            result['supported_subquestion'] = remainder
            return result
        narrative = narrative_decision(question)
        if narrative is not None:
            if narrative['status'] != 'search':
                return stopped(question, narrative['message'], narrative['status'])
            full_search=None
            if self.use_cba_reports:
                from bank_report_library import get_library
                full_search=lambda query,year,**options:get_library().search(query,year,**options)
            return narrative_evidence(question, narrative,
                                      lambda query: NarrativeEvidence.answer(self.core, query), full_search=full_search)
        alternatives = numeric_alternatives(question, self.answer)
        if alternatives is not None:
            return alternatives
        query, note = statement_request(question)
        if query is None: return stopped(question, note)
        result = validate_statement(deepcopy(self.core.answer(query)), question)
        if note:
            result['answer'].setdefault('limitations', []).append(note)
        result['question'] = question
        return result


class Backend(SimplifiedBackend):
    version = 'fintrace-answer-first-development'

    def __init__(self, evidence_backend=None, client=None):
        super().__init__(evidence_backend if evidence_backend is not None else EvidenceBackend(), client)
        self.research_client = None

    def answer(self, question):
        start = perf_counter()
        result = super().answer(question)
        result.update(version=self.version, seconds=perf_counter()-start)
        return result

    def research(self, question, topic, subject=None, source_documents=None):
        """Execute a bounded topic hint; original wording still drives retrieval."""
        from bank_report_library import get_library
        decision = narrative_decision(question, topic_hint=topic)
        if decision is None or decision['status'] != 'search':
            return stopped(question, decision['message'] if decision else 'No supported research interpretation was found.')
        if subject:
            decision['search_subject'] = subject
        if source_documents:
            decision['source_documents'] = sorted(source_documents)
        evidence = narrative_evidence(question, decision,
            lambda query: NarrativeEvidence.answer(self.evidence_backend.core, query),
            full_search=lambda query,year,**options:get_library().search(query,year,**options))
        return self.finish(evidence, question)

    def finish(self, evidence, question):
        if evidence.get('narrative_request') and evidence['answer'].get('source_excerpts'):
            if self.research_client is None:
                self.research_client = ResearchClient()
            return render_research(evidence, self.research_client)
        return super().finish(evidence, question)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('question'); parser.add_argument('--json', action='store_true')
    args = parser.parse_args(); result = Backend().answer(args.question)
    print(json.dumps(result, indent=2) if args.json else display(result))
