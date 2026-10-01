"""Source-bound demo with explicit operation, representation and completeness."""
import argparse
import json
import re
from time import perf_counter
from decimal import Decimal
from bank_retrieval import ROOT,read,save
from bank_answer import CONFIG,guard_response
from bank_source_cells import CellBinder,BoundCell,LABELS
from answer_bank_v8 import cell_claim,excerpts,number
from bank_operations_v9 import operation_plan,presentation,calculate
from bank_retrieval_service_v9 import RetrievalService


class Backend:
    def __init__(self):
        self.retriever=RetrievalService();self.binder=CellBinder()

    def numerical_records(self, context, request):
        """Exact indexed-row lookup for a known metric, before strict binding.

        Top-k semantic similarity must not decide whether a required annual
        column exists. This does not index new PDFs or trust a tagged number:
        CellBinder still validates row identity, native digits, basis, period,
        vintage and conflicts. Narrative retrieval remains ranked and bounded.
        """
        engine = getattr(self.retriever, 'engine', None)
        indexed = getattr(engine, 'records', None)
        if isinstance(indexed, list):
            return sorted((r for r in indexed
                if r['kind'] == 'financial_row'
                and r['source']['company'] == request['company']
                and request['metric'] in r['metric_tags']), key=lambda r: r['chunk_id'])
        wanted = set(context['request_coverage'][request['id']]['included_ids'])
        return [r for r in context['records'] if r['chunk_id'] in wanted]

    def answer(self,question):
        start=perf_counter()
        if not isinstance(question,str) or not question.strip() or len(question)>read(CONFIG)['max_question_characters']:
            raise ValueError('Invalid question length')
        op=operation_plan(question)
        if op['kind']=='unsupported':
            return {'question':question,'answer':{'status':'unable_to_verify','message':op['reason']},'seconds':perf_counter()-start}
        plan,context=self.retriever.retrieve(question)
        if plan['behavior']!='answer':
            return {'question':question,'plan':plan,'answer':guard_response(plan),'seconds':perf_counter()-start}
        if re.search(r'accurate to say|check (?:this|the) claim|verify (?:this|the) claim',question,re.I):
            return {'question':question,'answer':{'status':'unable_to_verify','message':'Automated claim verdicts are not enabled; ask for sourced figures and calculations.'},'seconds':perf_counter()-start}
        if op['kind']=='none' and plan['intent'] in ('define','explain','reconcile','summary'):
            extracts=excerpts(context['records'],self.binder.units,question,plan['intent'])
            return {'question':question,'plan':plan,'answer':{
                'status':'evidence_answer' if extracts else 'unable_to_verify','mode':'extractive_source_evidence',
                'message':"According to the company's report, the disclosures below are source excerpts, not independently proven causal explanations.",
                'source_excerpts':extracts,'limitations':['Full question coverage is not automatically certified.']},'seconds':perf_counter()-start}
        parts=[];all_cells=[]
        for request in plan['requests']:
            records=self.numerical_records(context,request)
            if not request['metric']:
                parts.append({'request':request,'claims':[],'calculations':[],'issues':['No supported numerical metric identified.']});continue
            cells,issues=self.binder.select(records,request,question)
            all_cells+=cells
            desired_unit='AUD billion' if re.search(r'\bin (?:aud )?billions?\b',question,re.I) else 'AUD million' if re.search(r'\bin (?:aud )?millions?\b',question,re.I) else None
            if desired_unit and any(c.unit!=desired_unit for c in cells):
                issues.append('Showing the disclosed unit only; requested unit conversion is not enabled.')
            claims=[]
            for cell in cells:
                claim=cell_claim(cell,self.binder);shown=presentation(cell,op)
                claim['presentation']=shown
                if shown['representation']=='expense_magnitude':
                    claim['text']=f"{cell.company} {LABELS[cell.metric]} (expense magnitude): {number(shown['value'])} {cell.unit}; {cell.period_end}, {cell.basis}, {cell.scope}. {shown['note']} Original signed value: {number(cell.value)}."
                claims.append(claim)
            calculations=[]
            wants_change=op['kind'] in ('change','year_difference')
            # A plain two-year comparison retains the existing chronological convention.
            if op['kind']=='none' and plan['intent']=='compare' and len(request['value_years'])==2:
                wants_change=True
            if wants_change:
                if len(request['value_years'])!=2: issues.append('This change requires exactly two comparable financial years.')
                elif not issues:
                    try: calculations.append(calculate(cells,{**op,'kind':'change'} if op['kind']=='none' else op))
                    except ValueError as error: issues.append('Calculation withheld: '+str(error))
            if len(cells)!=len(request['value_years']): issues.append('Not every requested year has a bound value.')
            parts.append({'request':request,'claims':claims,'calculations':calculations,'issues':issues})
        overall=[]
        if op['kind']=='profit_gap':
            if not parts or any(p['issues'] for p in parts): overall.append('Profit-gap calculation withheld because an operand is missing or ambiguous.')
            else:
                try: parts[0]['calculations'].append(calculate(all_cells,op))
                except ValueError as error: overall.append('Profit-gap calculation withheld: '+str(error))
        useful=any(p['claims'] for p in parts)
        complete=bool(parts) and all(p['claims'] and not p['issues'] for p in parts) and not overall
        # A calculation request cannot be marked complete just because operands exist.
        expected=1 if op['kind']=='profit_gap' else len(parts) if op['kind'] in ('change','year_difference') else 0
        completed=sum(len(p['calculations']) for p in parts)
        if completed<expected:
            complete=False;overall.append(f'Completed {completed} of {expected} requested calculations.')
        status='source_bound_answer' if complete else 'partial_answer' if useful else 'unable_to_verify'
        return {'question':question,'plan':plan,'operation_request':op,'answer':{
            'status':status,'mode':'source_cell_templates','parts':parts,'issues':overall,
            'calculation_coverage':{'required':expected,'completed':completed},
            'warning':'Development source binding, not independently human-certified financial advice.'},
            'retrieval':{'tokens':context['tokens'],'omissions':context['omissions'],
                'numeric_binding_search':'All indexed financial rows matching the requested bank and metric, followed by strict cell binding; not top-k retrieval accuracy.'},'seconds':perf_counter()-start}


def display(result):
    answer=result['answer'];lines=[f"Status: {answer['status']}"]
    if answer.get('message'): lines.append(answer['message'])
    for part in answer.get('parts',[]):
        for claim in part['claims']:
            lines.append(claim['text']);cell=claim['cell'];source=cell['source']
            lines.append(f"  Source: {source['document_title']}, PDF page {source['pdf_page']}, column {cell['column']} ({cell['period_end']}).")
        for calc in part.get('calculations',[]):
            change_unit='percentage points' if calc['unit']=='percent' else calc['unit']
            lines.append(f"  Calculation: {number(calc['left'])} - {number(calc['right'])} = {number(calc['absolute_change'])} {change_unit}.")
            lines.append('  Operands: '+' minus '.join(calc['operand_labels']))
            lines.append('  '+calc['note'])
            if any(p['representation']=='expense_magnitude' for p in calc['presentations']):
                lines.append(f"  Expense magnitudes used; original signed source difference: {number(calc['source_signed_difference'])} {calc['unit']}.")
            if 'basis_points' in calc:
                lines.append(f"  {number(calc['percentage_points'])} percentage points / {number(calc['basis_points'])} basis points.")
            elif calc.get('relative_change_percent') is not None:
                lines.append(f"  Relative change: {Decimal(calc['relative_change_percent']):.2f}% (rounded; full precision in JSON).")
        lines+=['  '+issue for issue in part['issues']]
    lines+=answer.get('issues',[])
    for section in answer.get('source_excerpts',[]):
        source=section['source'];lines.append(f"\n{source['document_title']} | PDF page {source['pdf_page']} | {section['heading']}")
        lines.extend(e['quote'] for e in section['excerpts'])
    lines+=answer.get('limitations',[])
    if answer.get('warning'): lines.append(answer['warning'])
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('question',nargs='?');parser.add_argument('--interactive',action='store_true')
    parser.add_argument('--json',action='store_true');args=parser.parse_args()
    if not args.question and not args.interactive: parser.error('Give a question or --interactive')
    backend=Backend()
    if args.interactive:
        print('FinTrace v9 local demo. CBA/NAB FY2024/FY2025. Type exit to finish.')
        while True:
            try: q=input('\nAsk FinTrace: ').strip()
            except (EOFError,KeyboardInterrupt): break
            if q.lower() in ('exit','quit'): break
            if not q: continue
            try: print(display(backend.answer(q)))
            except (ValueError,OSError) as error: print('Unable to answer:',error)
    else:
        result=backend.answer(args.question)
        print(json.dumps(result,indent=2) if args.json else display(result))


if __name__=='__main__': main()
