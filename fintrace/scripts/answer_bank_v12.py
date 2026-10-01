"""Contract-checked answers, labelled alternatives and optional local synthesis."""
import argparse
from copy import deepcopy
import json
import re
from time import perf_counter
from answer_bank_v10 import Backend as PreviousBackend
from answer_bank_v9 import display
from bank_contract_v12 import Planner, preflight, prepare, audit_bindings, metric_tags
from bank_generation_v11 import SynthesisClient, add_generation, SYSTEM
from bank_retrieval import ROOT, read


def stopped(question, message, status='unable_to_verify'):
    return {'question': question, 'answer': {'status': status, 'message': message}}


class EvidenceBackend(PreviousBackend):
    version = 'v12-contract-evidence'

    def __init__(self):
        super().__init__()
        self.retriever.planner = Planner()

    def answer(self, question):
        start = perf_counter()
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError('Invalid question length')
        reason = preflight(question)
        if reason:
            result = stopped(question, reason)
        else:
            text, notes = prepare(question)
            if re.search(r'\blast year\b|\bprevious year\b', text, re.I) and not re.search(r'20\d{2}', text):
                result = stopped(question, 'Which financial year do you mean? The corpus covers FY2024 and FY2025. For profit, I will show cash profit and statutory NPAT separately.', 'clarify')
            else:
                result = self.vintage_answer(text) or self.unperiodised_claim(text) or self.lcr_period_definition(question)
                if result is None:
                    from bank_retrieval_v7 import operation
                    if not re.search(r'20\d{2}', text) and operation(text) not in ('define', 'explain', 'reconcile', 'summary'):
                        result = stopped(question, 'Please specify FY2024 or FY2025. Reporting-basis alternatives will be shown without a separate choice.', 'clarify')
                    else:
                        result = self.margin_alternatives(text) or super().answer(text)
            result['question'] = question
            result['question_contract'] = {'retrieval_question': text, 'notes': notes,
                'metric_mapping': 'explicit aliases only for numerical answers'}
            result['answer'].setdefault('limitations', []).extend(notes)
            # A later report's comparative is not necessarily a restatement.
            # Disclose vintage without asserting the original value changed.
            restated = sorted({(c['company'], int(c['period_end'][:4]), c['report_year'], str(c['value']), c['unit'])
                for part in result['answer'].get('parts', []) for claim in part.get('claims', [])
                for c in [claim.get('cell', {})]
                if c.get('report_year') and c.get('period_end') and int(c['period_end'][:4]) < c['report_year']})
            for company, year, report_year, value, unit in restated:
                result['answer']['limitations'].append(
                    f'{company} FY{year} is taken from the FY{report_year} report\'s comparative column '
                    f'({value} {unit}). This alone does not establish that it was restated; the original disclosure may differ.')
            failures = audit_bindings(result)
            result['binding_validation'] = {'passed': not failures, 'issues': failures}
            if failures:
                result['answer'] = {'status': 'unable_to_verify', 'message': 'Evidence did not match the question. No substituted figure is shown.', 'issues': failures}
        result.update(version=self.version, seconds=perf_counter()-start)
        return result

    def lcr_period_definition(self, question):
        if not re.search(r'^\s*is\b.*(?:LCR|liquidity coverage ratio).*(?:single|day.end|daily)', question, re.I): return None
        banks = re.findall(r'\b(?:CBA|NAB)\b', question, re.I)
        if not banks: return None
        years = re.findall(r'20\d{2}', question)
        query = f'Define {banks[0]} quarterly-average LCR reporting basis '+ ' '.join(years)
        plan, context = self.retriever.retrieve(query)
        if plan['behavior'] != 'answer': return None
        sections = []
        # Glossary ranking can omit a table footnote. Resolve this structural
        # qualifier from the same frozen evidence view, with bank/year filtering.
        records = list(context['records'])
        if self.retriever.engine is not None:
            records += [r for r in self.retriever.engine.records if r['source']['company'] == banks[0].upper()
                        and (not years or r['source']['report_year'] in {int(y) for y in years})
                        and 'lcr' in r['metric_tags'] and re.search(r'quarter', r['body'], re.I)]
        seen = set()
        for record in records:
            if 'lcr' not in record['metric_tags']: continue
            if record['chunk_id'] in seen: continue
            seen.add(record['chunk_id'])
            ids = list(dict.fromkeys(record['unit_ids'] + record.get('dependency_units', [])))
            quotes = [{'source_id': i, 'quote': self.binder.units[i]} for i in ids if i in self.binder.units]
            joined = ' '.join(q['quote'] for q in quotes)
            if not re.search(r'quarter(?:ly)?[ -]average|averaged.*quarter|quarter.*averaged', joined, re.I): continue
            sections.append({'source': record['source'], 'heading': record['label'], 'excerpts': quotes})
            if len(sections) == 2: break
        if not sections: return None
        return {'question': question, 'plan': plan, 'answer': {'status': 'evidence_answer',
            'message': 'The cited disclosure identifies a quarterly average, not a single day-end LCR.',
            'source_excerpts': sections, 'limitations': ['This describes the reporting convention, not a daily liquidity series.']}}

    def margin_alternatives(self, text):
        if metric_tags(text) != {'nim'} or re.search(r'\bcash\b|\bstatutory\b', text, re.I): return None
        if re.search(r'defin|why|explain|what does|mean|single|daily', text, re.I): return None
        parts = []; missing = []
        for basis in ('cash', 'statutory'):
            query = re.sub(r'net interest margin|\bNIM\b', basis + ' net interest margin', text, flags=re.I)
            response = super().answer(query)
            for part in response['answer'].get('parts', []):
                if part['claims'] and all(c['cell']['basis'] == basis for c in part['claims']):
                    parts.append({**part, 'request': {**part['request'], 'basis': basis}})
            if not any(p['request'].get('basis') == basis for p in parts): missing.append(basis)
        if not parts: return None
        return {'question': text, 'answer': {'status': 'partial_answer' if missing or any(p['issues'] for p in parts) else 'source_bound_answer',
            'parts': parts, 'message': 'Net interest margin is shown by reporting basis. No choice is needed before viewing the available figures.',
            'limitations': [f'No {b}-basis NIM could be bound from the retrieved evidence.' for b in missing]}}

    def vintage_answer(self, text):
        """Compare publication versions of one period, not two business years."""
        years = [int(y) for y in re.findall(r'(?<!\d)20\d{2}(?!\d)', text)]
        reported = re.findall(r'(?:FY\s*)?(20\d{2})\s+(?:report|results|publication)', text, re.I)
        version_language = re.search(r'restat|reclassif|original.*(?:comparative|report)|report.*shows.*(?:FY|20)', text, re.I)
        tags = metric_tags(text)
        banks = re.findall(r'\b(?:CBA|NAB)\b', text, re.I)
        if not version_language or len(set(years)) != 2 or len(tags) != 1 or len(set(b.upper() for b in banks)) != 1:
            return None
        earlier, later = sorted(set(years))
        if years.count(earlier) < 2 and not re.search(r'restat|comparative', text, re.I):
            return None  # Two original annual results are not two versions of one year.
        if not reported and not re.search(r'restat|comparative', text, re.I): return None
        from bank_source_cells import LABELS
        bank = banks[0].upper(); metric = next(iter(tags)); parts = []
        for vintage in (earlier, later):
            q = f'What was {bank} {LABELS[metric]} for FY{earlier} in the FY{vintage} report?'
            response = super().answer(q)
            for part in response['answer'].get('parts', []):
                claims = [c for c in part['claims'] if c['cell']['period_end'].startswith(str(earlier)) and c['cell']['report_year'] == vintage]
                if claims:
                    parts.append({**part, 'request': {**part['request'], 'value_years': [earlier], 'report_year': vintage},
                                  'claims': claims, 'calculations': [], 'issues': []})
        complete = len(parts) == 2
        return {'question': text, 'answer': {'status': 'source_bound_answer' if complete else 'partial_answer' if parts else 'unable_to_verify',
            'parts': parts, 'message': f'These are two report versions of FY{earlier}, not a year-on-year fall or rise. The original and later comparative are labelled separately. The figures alone do not establish the reason for the revision.',
            'calculation_coverage': {'required': 0, 'completed': 0},
            'limitations': [] if complete else ['Both report versions could not be bound.']}, 'synthesis_policy': 'retain_version_explanation'}

    def unperiodised_claim(self, text):
        """Match supplied profit operands only within explicitly labelled corpus years.

        A numerical match is diagnostic, not an inference of the user's intended year.
        No growth verdict is issued without compatible source identities.
        """
        if re.search(r'20\d{2}', text) or not re.search(r'from\s+[\d,]+\s+to\s+[\d,]+', text, re.I): return None
        tags = metric_tags(text)
        if tags != {'cash_profit', 'statutory_npat'}: return None
        banks = re.findall(r'\b(?:CBA|NAB)\b', text, re.I)
        if len(set(b.upper() for b in banks)) != 1: return None
        from decimal import Decimal
        bank = banks[0].upper()
        years = sorted({d['report_year'] for d in read(ROOT/'config/banking_sources.json')['documents'] if d['company'] == bank})
        parts = []
        for label in ('cash profit', 'statutory net profit after tax'):
            q = f'What were {bank} {label} from continuing operations for '+ ' and '.join(f'FY{y}' for y in years)+'?'
            branch = super().answer(q)
            parts.extend(branch['answer'].get('parts', []))
        response = {'question': text, 'answer': {'parts': parts}}
        operands = re.search(r'from\s+([\d,]+)\s+to\s+([\d,]+)', text, re.I).groups()
        matches = []
        cells = [c['cell'] for p in response['answer'].get('parts', []) for c in p['claims']]
        for operand in operands:
            matches.append([c for c in cells if Decimal(c['value']) == Decimal(operand.replace(',', ''))])
        mismatch = all(matches) and all(a['basis'] != b['basis'] or a['scope'] != b['scope'] for a in matches[0] for b in matches[1])
        message = ('The supplied amounts match different reporting bases or scopes in the available reports. They must not be used together as a like-for-like growth calculation. ' if mismatch else 'The supplied amounts do not establish a compatible growth comparison. ')
        response['answer']['message'] = message + 'No years were specified. The available financial years are shown explicitly below as possible references, not as an assumption about your intended period.'
        for p in response['answer'].get('parts', []): p['calculations'] = []
        response['answer']['status'] = 'partial_answer'
        response['answer']['calculation_coverage'] = {'required': 1, 'completed': 0}
        response['answer'].setdefault('limitations', []).append('A matching amount alone does not identify the intended reporting period.')
        return response


def validate_generated_labels(result):
    """Fail closed on numeric metric relabelling, even if model self-review passed."""
    from bank_generation_v11 import evidence_cards, numbers
    registry = {c['id']: c for c in evidence_cards(result['answer'])}
    statements = result['answer'].get('generated_explanation', {}).get('statements', [])
    covered = set()
    for statement in statements:
        cards = [registry[eid] for eid in statement['evidence_ids']]
        cells = []
        for card in cards:
            if card['kind'] == 'bound_figure': cells.append(card['content']['cell'])
            elif card['kind'] == 'python_calculation': cells.extend(card['content']['source_cells'])
        if not cells or not numbers(statement['text']): continue
        if preflight(statement['text']):
            raise ValueError('Generated numerical statement introduced an unsupported metric or qualifier')
        allowed = {c['metric'] for c in cells}
        actual = metric_tags(statement['text'])
        if len(allowed) != 1 or actual != allowed:
            raise ValueError('Generated number must explicitly name the single metric in its cited cells')
        covered.update(actual)
        bases = {c['basis'] for c in cells}
        if len(bases) != 1:
            raise ValueError('Generated numeric statement combines different reporting bases')
        if allowed == {'nim'} and not re.search(r'\b'+re.escape(next(iter(bases)))+r'\b', statement['text'], re.I):
            raise ValueError('Generated NIM must explicitly label its reporting basis')
    required = {c['cell']['metric'] for p in result['answer'].get('parts', []) for c in p['claims']}
    if statements and required and not required.issubset(covered):
        raise ValueError('Generated explanation omitted a requested financial measure')


class ContractSynthesisClient(SynthesisClient):
    def chat(self, system, payload, schema, output_tokens):
        if system == SYSTEM:
            system += '\nFor numerical answers, use one financial metric per statement and explicitly name its exact metric and basis. Cite only cards for that metric. For ambiguous profit, give separate cash and statutory statements with their scopes. Never relabel a total as a component.\n'
        return super().chat(system, payload, schema, output_tokens)


class Backend:
    version = 'v12-contract-generative'

    def __init__(self, evidence_backend=None, client=None):
        self.evidence_backend = evidence_backend if evidence_backend is not None else EvidenceBackend()
        self.client = client if client is not None else ContractSynthesisClient()

    @property
    def binder(self): return self.evidence_backend.binder

    def answer(self, question):
        start = perf_counter()
        evidence = self.evidence_backend.answer(question)
        if evidence.get('synthesis_policy'):
            result = deepcopy(evidence)
            result['generation'] = {'status': 'skipped', 'reason': 'Version comparison uses a deterministic explanation; figures retain their separate publication identities.'}
        else:
            result = add_generation(evidence, self.client)
        try:
            validate_generated_labels(result)
        except ValueError as error:
            metadata = result.get('generation', {})
            result = deepcopy(evidence)
            result['generation'] = {**metadata, 'status': 'fallback', 'reason': str(error)}
            result['answer']['message'] = 'Generated wording failed metric checks. Showing the source-bound answer.'
        result.update(version=self.version, seconds=perf_counter()-start)
        return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('question')
    p.add_argument('--json', action='store_true'); p.add_argument('--evidence-only', action='store_true')
    a = p.parse_args(); result = (EvidenceBackend() if a.evidence_only else Backend()).answer(a.question)
    print(json.dumps(result, indent=2) if a.json else display(result))
