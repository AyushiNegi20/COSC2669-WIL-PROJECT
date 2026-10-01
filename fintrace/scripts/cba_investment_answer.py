"""Source-derived CBA investment comparison, not a stored-answer lookup."""
from copy import deepcopy
from decimal import Decimal
import re
from cba_report_library import ROW_LABELS


def eligible(question, context, plan=None):
    from bank_conversational_intent import table_allowed
    return table_allowed(question, context, plan)


def cell(table,label,column):
    source=deepcopy(table['source']); year=table['years'][column]
    metric='investment_'+re.sub(r'[^a-z]+','_',label.lower()).strip('_')
    values=table['rows'][label]
    return {'metric':metric,'company':'CBA','value':values[column],'raw_value':values[column],
        'unit':'AUD million','basis':'reported investment spend','scope':'continuing','period_kind':'annual',
        'period_end':f'{year}-06-30','report_year':source['report_year'],'column':column+1,
        'source':source,'source_id':f"{source['document_id']}:full:p{source['pdf_page']:03}:investment:{metric}",
        'header_ids':[],'record_id':metric,'row_quote':f"{label} | FY{table['years'][0]}: {values[0]} | FY{table['years'][1]}: {values[1]} | AUD million, continuing operations",
        'binding_status':table['validation']}


def answer(question,context,library,plan=None):
    if not eligible(question,context,plan): return None
    tables=[]
    for year in context['years']:
        candidates=[t for t in library.data['investment_tables'] if t['source']['report_year']==year]
        if len(candidates)!=1:
            return {'answer':{'status':'unable_to_verify','message':f'I could not establish an unambiguous validated CBA investment table for FY{year}. No spending amount or ranking is inferred.'},'generation':{'status':'skipped'},'route':'guard'}
        tables.append(candidates[0])
    parts=[]; summaries=[]; sections=[]
    limit = ('These figures describe CBA Group investment spending on a continuing-operations basis, '
             'not lending to industries, total IT operating expenses or an AI-only budget. Technology projects span multiple categories.')
    subset = bool(re.search(r'\b(?:AI|artificial intelligence|cyber\w*|engineering|technology|cloud|retail|business banking|ASB|New Zealand)\b',question,re.I))
    quantified = bool(re.search(r'how much|amount|budget|exact|most|largest|biggest|\bmore\b|\bcompare\b|\bversus\b|\d.*(?:million|billion|%)',question,re.I))
    for table in tables:
        source=table['source'];year=table['years'][0]; earlier=table['years'][1]
        category=ROW_LABELS[3:]
        selected=[label for label in ROW_LABELS if label.lower() in question.lower()]
        selected=list(ROW_LABELS)
        # Show comparable prior/current operands. The summaries below distinguish
        # largest amount, absolute increase and fastest percentage growth.
        for label in selected:
            current,previous=cell(table,label,0),cell(table,label,1)
            new,old=Decimal(current['value']),Decimal(previous['value']);delta=new-old
            calc={'operation':'change','left':str(new),'right':str(old),'absolute_change':str(delta),
                  'unit':'AUD million','relative_change_percent':str(delta/old*100) if old else None,
                  'source_cells':[current,previous],'note':'Annual investment spend: later minus earlier; same row, unit and continuing-operations scope.'}
            def claim(c):
                return {'cell':c,'text':f"CBA {label} for the year ended {c['period_end']}: {c['value']} AUD million, continuing operations.",
                        'evidence':[{'source_id':c['source_id'],'source':c['source'],'quote':c['row_quote']}]}
            parts.append({'claims':[claim(previous),claim(current)],'calculations':[calc],'issues':[]})
        def amount(label,i=0):return Decimal(table['rows'][label][i])
        total,oldtotal=amount('Investment spend'),amount('Investment spend',1)
        maximum=max(amount(k) for k in category)
        leaders=[k for k in category if amount(k)==maximum]
        changes={k:amount(k)-amount(k,1) for k in category}
        maxchange=max(changes.values()); gainers=[k for k,v in changes.items() if v==maxchange]
        growth={k:(amount(k)-amount(k,1))/amount(k,1)*100 for k in category if amount(k,1)>0}
        fastest=max(growth.values()) if growth else None
        fastest_names=[k for k,v in growth.items() if v==fastest]
        intro=f'CBA reported total investment spending of {total:,.0f} AUD million in FY{year}, compared with {oldtotal:,.0f} AUD million in FY{earlier}.'
        delta=total-oldtotal
        intro+=f' That is {"an increase" if delta>0 else "a decrease" if delta<0 else "no change"} of {abs(delta):,.0f} AUD million'
        if oldtotal: intro+=f' ({abs(delta/oldtotal*100):.2f}%, calculated and rounded)'
        intro+='.'
        summaries.append({'text':intro,'citations':[source],'kind':'calculation'})
        if re.search(r'\bexpens\w*|\bcapitali[sz]\w*|\bcharged\b',question,re.I):
            summaries.append({'text':f'Of FY{year} investment spending, {amount("Expensed investment spend"):,.0f} AUD million was expensed and {amount("Capitalised investment spend"):,.0f} AUD million was capitalised. The total investment amount is not all an expense in that year.',
                              'citations':[source],'kind':'numeric'})
        summaries.append({'text':f'The largest disclosed category in FY{year} was {" and ".join(leaders)} at {maximum:,.0f} AUD million. '+
            ('The biggest year-on-year increase was ' + ' and '.join(gainers) + f', up {maxchange:,.0f} AUD million.' if maxchange>0 else 'No disclosed category increased year on year.'),
            'citations':[source],'kind':'calculation'})
        if fastest is not None and fastest>0:
            summaries.append({'text':f'The fastest percentage growth was {" and ".join(fastest_names)} at {fastest:.2f}% (calculated and rounded). Rankings apply only to these three disclosed investment categories.',
                              'citations':[source],'kind':'calculation'})
        for label in category:
            summaries.append({'text':f'{label}: {amount(label,1):,.0f} AUD million in FY{earlier} to {amount(label):,.0f} AUD million in FY{year}.',
                              'citations':[source],'kind':'numeric'})
        if re.search(r'\bshare\b|\bslice\b|\bproportion\b|how much of|what percent',question,re.I):
            for label in category:
                if not total or not oldtotal: continue
                newshare,oldshare=amount(label)/total*100,amount(label,1)/oldtotal*100
                summaries.append({'text':f'{label} represented {newshare:.2f}% of total investment in FY{year}, versus {oldshare:.2f}% in FY{earlier} (calculated from disclosed amounts). Its amount and its share can move differently because the total budget also changes.',
                                  'citations':[source],'kind':'calculation'})
                for column,share in ((0,newshare),(1,oldshare)):
                    numerator,denominator=cell(table,label,column),cell(table,'Investment spend',column)
                    parts.append({'claims':[],'calculations':[{'operation':'share','left':numerator['value'],'right':denominator['value'],
                        'result':str(share),'unit':'percent','source_cells':[numerator,denominator],
                        'note':f'{label} divided by total investment spend, multiplied by 100. Same financial year and scope.'}],'issues':[]})
        if re.search(r'how much of|share.*(?:increase|extra)|proportion.*(?:increase|extra)',question,re.I):
            for label in category:
                if not delta: continue
                contribution=changes[label]/delta*100
                summaries.append({'text':f'{label} contributed {changes[label]:,.0f} AUD million of the {delta:,.0f} AUD million total change, or {contribution:.2f}% of that change. This is share of the change, not the category\'s own growth rate.',
                                  'citations':[source],'kind':'calculation'})
                parts.append({'claims':[],'calculations':[{'operation':'share','left':str(changes[label]),'right':str(delta),
                    'result':str(contribution),'unit':'percent',
                    'source_cells':[cell(table,label,0),cell(table,label,1),cell(table,'Investment spend',0),cell(table,'Investment spend',1)],
                    'note':'(Category current minus prior) / (Total current minus prior) multiplied by 100.'}],'issues':[]})
        # Literal relevant strategy paragraphs stay attributed and retain the
        # original wording. No model is asked to invent a causal explanation.
        thematic=[b for b in table['blocks'] if re.search(r'Bank is continuing|Infrastructure and branch refurbishment initiatives|generative AI',b['quote'],re.I)]
        if thematic:
            quote=thematic[0]
            summaries.append({'text':f'CBA describes its direction as follows: "{quote["quote"]}"','citations':[source],'kind':'quotation'})
        sections.append({'source':source,'heading':'Investment spend: annual columns, continuing operations',
            'excerpts':[{'source_id':f"{source['document_id']}:full:p{source['pdf_page']:03}:investment:table",'quote':
                '\n'.join(f'{k} | FY{year}: {v[0]} | FY{earlier}: {v[1]} | AUD million' for k,v in table['rows'].items())}]+thematic})
    notes=context['defaults']+['Interpreting investment as spending on CBA\'s own business. '+limit]
    causal=bool(re.search(r'\bwhy\b|\bcause|\bprove|\bresponsible for\b',question,re.I))
    if subset and quantified:
        notes.insert(0,'The exact budget or ranking for the named sub-area is not established by these grouped figures. The category totals below are context, not a substitute for that amount.')
        summaries.insert(0,{'text':notes[0], 'citations':[], 'kind':'limitation'})
    if causal:
        notes.append('The table establishes movements, not their cause. The quoted explanation is attributed to CBA.')
    return {'question':question,'route':'numeric','generation':{'status':'skipped','reason':'Checked source table and Decimal arithmetic.'},
        'coverage':{'kind':'checked_cba_investment_table','report_years':context['years']},
        'answer':{'status':'partial_answer' if subset and quantified or causal else 'source_bound_answer',
                  'message':' '.join(notes),'limitations':notes,'important_notes':notes,
                  'parts':parts,'source_excerpts':sections,'summary_statements':summaries,
                  'summary_replaces_detail':True}}
