"""Demo backend: bound numerical answers and explicitly extractive prose evidence."""
import argparse
from decimal import Decimal
import json
import re
from time import perf_counter
from bank_retrieval import ROOT,read,save,sha
from bank_retrieval_service import RetrievalService
from bank_source_cells import CellBinder,LABELS,calculate_change
from bank_answer import CONFIG,guard_response


def number(value): return format(Decimal(value),',f')


def unsupported_operation(question):
    s=question.lower()
    if re.search(r'\bminus\b|\bsubtract\b|\bdivided by\b|\bratio of\b|\bsum of\b|\bmultipl(?:y|ied)\b|\bcagr\b|\bannualised\b|\bannualized\b',s):
        return 'This demo calculates chronological year-on-year change only (later minus earlier). Arbitrary ordered arithmetic and derived ratios are not enabled.'
    if re.search(r'\bconvert\b|\busd\b|\bus dollars\b|\bnzd\b',s):
        return 'Currency and unit conversion are not enabled. Ask for the figure in its disclosed unit.'
    if re.search(r'\bwhich (?:bank|company).*(?:higher|larger|bigger|better)|\brank\b',s):
        return 'Automatic bank rankings are not enabled. Ask for both disclosed figures and compare their periods and reporting bases.'
    return None


def cell_claim(cell,binder):
    qualifiers={'continuing':'continuing operations','including_discontinued':'including discontinued operations','Group':'Group'}
    return {'text':f'{cell.company} {LABELS[cell.metric]}: {number(cell.value)} {cell.unit}; {cell.period_kind.replace("_"," ")} ending {cell.period_end}, {cell.basis}, {qualifiers[cell.scope]}.',
        'cell':cell.payload(),'evidence':[{'source_id':uid,'quote':binder.units[uid],'source':cell.source}
            for uid in dict.fromkeys([cell.source_id]+list(cell.header_ids))],
        'method':'deterministic_template_from_bound_source_cell'}


def excerpts(records,units,question,intent):
    """Verbatim source extracts, not model-generated explanations or causal claims."""
    chosen=[];seen=set();s=question.lower()
    eligible=[r for r in records if r['kind'] in ('passage','definition')]
    if intent=='reconcile': eligible=records
    # An explicit conceptual distinction needs its literal disclosure ahead of glossary shorthand.
    if re.search(r'cash.flow|cash.accounting',s):
        eligible.sort(key=lambda r:not bool(re.search(r'not a measure based on cash accounting|cash flows or liquidity',r['body'],re.I)))
    for record in eligible:
        if len(chosen)>=12: break
        # Render complete source units, retaining qualifiers rather than cutting a sentence.
        fresh=[u for u in record['unit_ids'] if u not in seen]
        if not fresh: continue
        texts=[{'source_id':u,'quote':units[u]} for u in fresh]
        seen.update(fresh)
        chosen.append({'source':record['source'],'heading':record['label'],'excerpts':texts})
    return chosen


class Backend:
    def __init__(self):
        self.retriever=RetrievalService();self.binder=CellBinder()

    def answer(self,question):
        start=perf_counter()
        if not question.strip() or len(question)>read(CONFIG)['max_question_characters']: raise ValueError('Invalid question length')
        restriction=unsupported_operation(question)
        if restriction:
            return {'question':question,'answer':{'status':'unable_to_verify','message':restriction},'seconds':perf_counter()-start}
        plan,context=self.retriever.retrieve(question)
        if plan['behavior']!='answer':
            return {'question':question,'plan':plan,'answer':guard_response(plan),'seconds':perf_counter()-start}
        if re.search(r'accurate to say|check (?:this|the) claim|verify (?:this|the) claim',question,re.I):
            return {'question':question,'plan':plan,'answer':{'status':'unable_to_verify',
                'message':'Automated claim verdicts are not enabled in this demo. Ask for the figures and their change instead.'},'seconds':perf_counter()-start}
        if plan['intent'] in ('define','explain','reconcile','summary'):
            source_excerpts=excerpts(context['records'],self.binder.units,question,plan['intent'])
            return {'question':question,'plan':plan,'answer':{
                'status':'evidence_answer' if source_excerpts else 'unable_to_verify',
                'mode':'extractive_source_evidence',
                'message':"According to the company's report, the relevant disclosures are below. These are source excerpts, not an independently inferred explanation.",
                'source_excerpts':source_excerpts,
                'limitations':['Excerpts may contain additional context; full question coverage is not automatically certified.']},
                'seconds':perf_counter()-start}
        parts=[]
        for request in plan['requests']:
            wanted=set(context['request_coverage'][request['id']]['included_ids'])
            records=[r for r in context['records'] if r['chunk_id'] in wanted]
            if not request['metric']:
                parts.append({'request':request,'claims':[],'issues':['No supported numerical metric identified.']});continue
            cells,issues=self.binder.select(records,request,question)
            desired_unit='AUD billion' if re.search(r'\bin (?:aud )?billions?\b',question,re.I) else 'AUD million' if re.search(r'\bin (?:aud )?millions?\b',question,re.I) else None
            if desired_unit and any(c.unit!=desired_unit for c in cells):
                issues.append('Showing the disclosed unit only; the requested unit conversion is not enabled.')
            claims=[cell_claim(c,self.binder) for c in cells]
            calculations=[]
            wants_change=len(request['value_years'])==2 and (plan['intent']=='compare' or plan['constraints']['requires_new_calculation'])
            if wants_change and not issues:
                try: calculations.append(calculate_change(cells))
                except ValueError as error: issues.append('Calculation withheld: '+str(error))
            if plan['constraints']['requires_new_calculation'] and not wants_change:
                issues.append('Please give exactly two comparable financial years for a change calculation.')
            parts.append({'request':request,'claims':claims,'calculations':calculations,'issues':issues})
        useful=any(p['claims'] for p in parts)
        complete=parts and all(p['claims'] and not p['issues'] for p in parts)
        status='source_bound_answer' if complete else 'partial_answer' if useful else 'unable_to_verify'
        return {'question':question,'plan':plan,'answer':{'status':status,'mode':'source_cell_templates',
            'parts':parts,'warning':'Development source binding, not independently human-certified financial advice.'},
            'retrieval':{'tokens':context['tokens'],'omissions':context['omissions']},'seconds':perf_counter()-start}


def display(result):
    answer=result['answer'];lines=[f"Status: {answer['status']}"]
    if answer.get('message'): lines.append(answer['message'])
    for part in answer.get('parts',[]):
        for claim in part['claims']:
            lines.append(claim['text']);cell=claim['cell'];source=cell['source']
            lines.append(f"  Source: {source['document_title']}, PDF page {source['pdf_page']}, column {cell['column']} ({cell['period_end']}).")
        for calc in part.get('calculations',[]):
            lines.append(f"  Change: {number(calc['later'])} - {number(calc['earlier'])} = {number(calc['absolute_change'])} {calc['unit']}.")
            if 'basis_points' in calc: lines.append(f"  {number(calc['percentage_points'])} percentage points / {number(calc['basis_points'])} basis points.")
            elif calc.get('relative_change_percent') is not None:
                lines.append(f"  Relative change: {Decimal(calc['relative_change_percent']):.2f}% (rounded; full precision retained in JSON).")
        lines+=['  '+issue for issue in part['issues']]
    for section in answer.get('source_excerpts',[]):
        source=section['source'];lines.append(f"\n{source['document_title']} | PDF page {source['pdf_page']} | {section['heading']}")
        lines.extend(e['quote'] for e in section['excerpts'])
    if answer.get('warning'): lines.append(answer['warning'])
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('question',nargs='?');parser.add_argument('--interactive',action='store_true')
    parser.add_argument('--json',action='store_true');parser.add_argument('--save-as');args=parser.parse_args()
    if not args.question and not args.interactive: parser.error('Give a question or --interactive')
    backend=Backend()
    if args.interactive:
        print('FinTrace local demo. CBA and NAB, FY2024/FY2025. Type exit to finish.')
        while True:
            try: question=input('\nAsk FinTrace: ').strip()
            except (EOFError,KeyboardInterrupt): break
            if question.lower() in ('exit','quit'): break
            if not question: continue
            try: print(display(backend.answer(question)))
            except (ValueError,OSError) as error: print('Unable to answer:',error)
        return
    result=backend.answer(args.question)
    if args.save_as:
        if not re.fullmatch('[a-z0-9_-]+',args.save_as): parser.error('Invalid run ID')
        path=ROOT/'reports/answer_v8'/f'{args.save_as}.json'
        if path.exists(): parser.error('Do not overwrite previous runs')
        save(path,result)
    print(json.dumps(result,indent=2) if args.json else display(result))


if __name__=='__main__': main()
