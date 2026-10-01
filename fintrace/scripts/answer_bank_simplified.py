"""Source templates for numbers; checked local generation for report explanations.

The v12 evidence backend is reused unchanged. No new fact store or financial
constants are introduced. Numeric answers do not call the generation client.
"""
import argparse
from copy import deepcopy
import json
import re
from time import perf_counter
from answer_bank_v12 import EvidenceBackend, ContractSynthesisClient
from answer_bank_v9 import display
from bank_generation_v11 import add_generation


def split_mixed(question):
    """Bounded split of an explicit numeric request followed by an explanation.

    Do not infer a second company/period from pronouns or discard an explicit
    second subject. The full suffix is retained for retrieval and the model.
    """
    match = re.search(r'\s*(?:,?\s+and\s+|;\s*)(why\b|explain\b|what (?:factors|drove|caused)\b)', question, re.I)
    if not match: return None
    numeric = question[:match.start()].rstrip(' ,;?')
    from bank_query_routing import checked_numeric_request
    if not checked_numeric_request(numeric):
        return None
    suffix = question[match.start():].lstrip(' ,;')
    suffix = re.sub(r'^and\s+', '', suffix, flags=re.I)
    # Preserve only the shared request context, not an instruction to calculate
    # during prose generation. The numerical branch remains the sole calculator.
    subject = re.sub(r'^(?:how much did|by how much did|what (?:is|are|was|were)|calculate|compare|tell me|show me|give me)\s+', '', numeric, flags=re.I)
    narrative = 'Explain the reported reasons concerning '+subject+'. '+suffix
    return numeric+'?', narrative


def has_narrative_request(question):
    return bool(re.search(r'\bwhy\b|\bexplain\b|\bdefine\b|\bdefinition\b|what (?:factors|drove|caused|does.*mean)', question, re.I))


# Reasoning / behavioural questions that should be answered from retrieved prose
# and fail-closed synthesis, not refused by the numeric contract. Deliberately
# excludes plain numeric lookups ("what was", "how much") and direction words
# (rise/fall) that the numeric branch already answers with labelled figures.
REASONING = re.compile(
    r'\bwhy\b|\bexplain\b|\breasons?\b|\bdrivers?\b'
    r'|what (?:factors|drove|caused)|what\b.*\bmean\b'
    r'|what (?:does|is|are)\b.*\b(?:mean|means|measure|measures|refer|defined|definition)\b'
    r'|\bhow (?:did|has|have|does)\b'
    r'|\bdid\b.*\b(?:reduce|cut|lower|invest|spend|prioritise|prioritize|focus)\b'
    r'|\bwhat (?:is|are|was|were)\b.*\bdoing\b',
    re.I)

# Direction / premise questions ("did staff expenses fall?") that the numeric
# contract cannot bind. Used only as a fallback after a refusal, so the numeric
# branch still answers profit direction with labelled figures where it can.
PREMISE = re.compile(
    r'\b(?:did|was|were|has|have|does)\b.*\b(?:fall|fell|fallen|rise|rose|risen|drop|dropped|declin\w*'
    r'|grow|grew|grown|increas\w*|decreas\w*|reduc\w*|cut|lower\w*|rais\w*|chang\w*|higher|improv\w*)\b',
    re.I)


def is_reasoning_request(question):
    from bank_query_routing import checked_numeric_request
    # "How did the ratio change?" asks for arithmetic, not a causal story.
    return not checked_numeric_request(question) and bool(REASONING.search(question))


class Backend:
    version = 'simplified-candidate-1'

    def __init__(self, evidence_backend=None, client=None):
        self.evidence_backend = evidence_backend if evidence_backend is not None else EvidenceBackend()
        self.client = client  # Lazy: even client construction is unnecessary for numbers.

    @property
    def binder(self): return self.evidence_backend.binder

    def finish(self, evidence, question):
        result = deepcopy(evidence)
        answer = result['answer']
        # An explanation must have its own retrieved prose. Do not let a model
        # invent a cause from numeric operands alone, including mixed requests.
        if answer['status'] == 'evidence_answer' and answer.get('source_excerpts') and not answer.get('parts'):
            if self.client is None: self.client = ContractSynthesisClient()
            result = add_generation(result, self.client)
            result['route'] = 'narrative'
        else:
            result['route'] = 'numeric' if answer.get('parts') else 'guard'
            result['generation'] = {'status': 'skipped', 'reason': 'Numbers, calculations and guards use source templates; no generative model was called.'}
            if answer.get('parts') and has_narrative_request(question) and not evidence.get('synthesis_policy'):
                answer['status'] = 'partial_answer'
                answer.setdefault('limitations', []).append('The figures are available, but the requested explanation was not retrieved. No cause has been inferred from the numbers.')
        return result

    def answer(self, question):
        start = perf_counter()
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError('Invalid question length')
        split = split_mixed(question)
        if split:
            numeric_q, narrative_q = split
            numeric = self.finish(self.evidence_backend.answer(numeric_q), numeric_q)
            narrative = self.finish(self.evidence_backend.answer(narrative_q), narrative_q)
            result = deepcopy(numeric); answer = result['answer']; explanation = narrative['answer']
            prose = explanation.get('source_excerpts', []) if narrative['route'] == 'narrative' else []
            if prose: answer['source_excerpts'] = deepcopy(prose)
            if explanation.get('generated_explanation'):
                answer['generated_explanation'] = deepcopy(explanation['generated_explanation'])
            answer['message'] = '\n\n'.join(x for x in (answer.get('message'),
                'Report explanation: '+explanation.get('message', 'No supported explanation was found.')) if x)
            answer.setdefault('limitations', []).extend(explanation.get('limitations', []))
            complete = (answer['status'] == 'source_bound_answer' and bool(prose)
                        and narrative['generation'].get('status') == 'generated'
                        and explanation['status'] == 'evidence_answer')
            if not complete:
                answer['status'] = 'partial_answer' if answer.get('parts') or prose else 'unable_to_verify'
                answer['limitations'].append('At least one part of the combined request could not be fully answered.')
            result['route'] = 'mixed'
            result['generation'] = deepcopy(narrative['generation'])
            result['subquestions'] = {'numeric': numeric_q, 'narrative': narrative_q}
            result['branch_status'] = {'numeric': numeric['answer']['status'], 'narrative': explanation['status']}
        elif is_reasoning_request(question):
            # Route reasoning questions to retrieved prose + fail-closed synthesis
            # instead of refusing them at the numeric contract. Numbers are never
            # invented: the model only sees retrieved excerpts and its output is
            # support-checked; if retrieval finds nothing, fall back to the plain answer.
            narrative_q = 'Explain the reported reasons concerning ' + question
            result = self.finish(self.evidence_backend.answer(narrative_q), narrative_q)
            if result['answer']['status'] == 'evidence_answer':
                result['route'] = 'reasoning'
                result['reasoning_question'] = question
            else:
                result = self.finish(self.evidence_backend.answer(question), question)
        else:
            result = self.finish(self.evidence_backend.answer(question), question)
            # If a direction/premise question was refused by the numeric contract
            # (e.g. a non-metric line item like staff expenses), retry as prose.
            # Out-of-scope numeric lookups (ROE, cost-to-income) do not match
            # PREMISE, so they still abstain.
            if (result['answer']['status'] in ('clarify', 'unable_to_verify')
                    and PREMISE.search(question)):
                narrative_q = 'Explain the reported reasons concerning ' + question
                narrative = self.finish(self.evidence_backend.answer(narrative_q), narrative_q)
                if narrative['answer']['status'] == 'evidence_answer':
                    narrative['route'] = 'reasoning_fallback'
                    narrative['reasoning_question'] = question
                    result = narrative
        result.update(question=question, version=self.version, seconds=perf_counter()-start)
        return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('question'); p.add_argument('--json', action='store_true')
    args = p.parse_args(); result = Backend().answer(args.question)
    print(json.dumps(result, indent=2) if args.json else display(result))
