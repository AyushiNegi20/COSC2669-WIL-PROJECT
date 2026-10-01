"""Bounded intent repairs over frozen v9. No answer keys or financial constants."""
import argparse
from copy import deepcopy
import json
import re
from time import perf_counter
from answer_bank_v9 import Backend as V9Backend, display
from bank_retrieval_v6 import explicit_metrics
from bank_retrieval_service_v10 import RetrievalService


def interpret(question):
    """Conservative wording normalisation. Keep original question for audit."""
    s=question.lower();tags=set(explicit_metrics(question));notes=[];text=question
    arithmetic=bool(re.search(r'calculate|subtract|minus|quantify|work out|by how much',s))
    contrast=bool(re.search(r'cash[ -]flows?|cash accounting|cash (?:that )?(?:flowed|flowing|coming|comes|came) (?:in|into)',s))
    conceptual=contrast and 'cash_profit' in tags and not arithmetic
    if conceptual:
        text='Explain the definition and distinction: '+text+' Cash profit versus cash flows and cash accounting.'
        notes.append('Interpreted as a conceptual cash-profit/cash-flow distinction, not subtraction.')
    elif re.search(r'statutory',s) and re.search(r'accounting standards|reporting basis',s) and not arithmetic:
        text='Explain statutory profit reporting basis: '+text
        notes.append('Interpreted statutory reporting basis as a definition question.')
    # Remove only a trailing explicitly negated daily target. A positive request
    # for the lowest daily value must still reach the existing refusal guard.
    if 'lcr' in tags and re.search(r'quarter(?:ly|[ -]average|.*average)|average.*quarter',s):
        revised=re.sub(r',?\s+(?:rather than|instead of|not)\s+(?:a |the )?(?:single[ -]day(?:\x27s)?|daily)\b[^.!?]*[.!?]?\s*$', '', text, flags=re.I)
        if revised!=text:
            text=revised;notes.append('Kept the requested quarterly average and excluded the explicitly negated daily target.')
    prose=conceptual or bool(re.search(r'^\s*(?:why|explain|define)|\bwhat (?:does|do|is meant|factors|caused)|\bdefinition\b',s))
    undecided=bool(re.search(r'(?:not|never|haven.t|have not) (?:yet )?(?:chosen|selected|decided)|undecided|not sure which|unsure which',s))
    ambiguous=bool(re.search(r'\bprofit\b|\bearnings\b',s)) and not tags.intersection({'cash_profit','statutory_npat','basic_cash_eps'})
    if not prose and (ambiguous or undecided and re.search(r'\bprofit\b',s)):
        return {'question':question,'notes':notes,'clarify':'Do you mean cash profit (the bank\x27s management-adjusted result), statutory profit (the accounting result), or both? Please also specify the bank and financial year if missing.'}
    return {'question':text,'notes':notes,'clarify':None}


def focus_excerpts(sections,question,intent):
    """Drop clearly different glossary entries; never rewrite the quoted units."""
    if intent=='reconcile': return sections
    requested=set(explicit_metrics(question));kept=[]
    contrast=bool(re.search(r'cash[ -]flows?|cash accounting',question,re.I)) and 'cash_profit' in requested
    if contrast:
        direct=[s for s in sections if any(re.search(r'not a measure based on cash accounting|cash flows or liquidity',e['quote'],re.I) for e in s['excerpts'])]
        if direct: return direct
    if re.search(r'statutory',question,re.I) and re.search(r'accounting standards|reporting basis',question,re.I):
        direct=[s for s in sections if any(re.search(r'statutory',e['quote'],re.I) and re.search(r'accounting standards',e['quote'],re.I) for e in s['excerpts'])]
        if direct: return direct
    for section in sections:
        heading_tags=set(explicit_metrics(section['heading']))
        body=' '.join(e['quote'] for e in section['excerpts'])
        body_tags=set(explicit_metrics(body))
        if requested and heading_tags and not heading_tags.intersection(requested) and not body_tags.intersection(requested): continue
        if intent=='define' and requested and not heading_tags.intersection(requested) and not body_tags.intersection(requested): continue
        # PACC is not one of the supported metrics, so its glossary heading has
        # no tag. It must not become a definition of cash profit by association.
        if re.search(r'profit after capital charge|\bPACC\b',section['heading'],re.I) and not re.search(r'profit after capital charge|\bPACC\b',question,re.I): continue
        kept.append(section)
    return kept


class Backend(V9Backend):
    version='v10-demo'

    def __init__(self):
        super().__init__()
        self.retriever=RetrievalService()

    def answer(self,question):
        start=perf_counter()
        if not isinstance(question,str) or not question.strip() or len(question)>2000: raise ValueError('Invalid question length')
        decision=interpret(question)
        if decision['clarify']:
            return {'question':question,'answer':{'status':'clarify','message':decision['clarify']},'seconds':perf_counter()-start,'version':self.version}
        result=deepcopy(super().answer(decision['question']))
        result['question']=question;result['version']=self.version
        result['interpretation']={'retrieval_question':decision['question'],'notes':decision['notes']}
        if result['answer'].get('source_excerpts'):
            original=result['answer']['source_excerpts']
            result['answer']['source_excerpts']=focus_excerpts(original,decision['question'],result.get('plan',{}).get('intent'))
            result['answer']['excerpt_filter']={'before':len(original),'after':len(result['answer']['source_excerpts']),'method':'Exclude unrelated named glossary entries; preserve literal source units.'}
            if not result['answer']['source_excerpts']:
                result['answer'].update(status='unable_to_verify',message='No directly relevant source excerpt remained after relevance checks. Please narrow the question.')
        if decision['notes']: result['answer'].setdefault('limitations',[]).extend(decision['notes'])
        result['seconds']=perf_counter()-start
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('question');p.add_argument('--json',action='store_true');a=p.parse_args()
    r=Backend().answer(a.question);print(json.dumps(r,indent=2) if a.json else display(r))
