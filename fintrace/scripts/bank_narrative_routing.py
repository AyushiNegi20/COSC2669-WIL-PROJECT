"""Everyday strategy questions, separate from validated numerical measures.

No financial values, expected pages or evaluation answers are used here.
Topic matching is a conservative relevance filter, not proof of completeness.
"""
from copy import deepcopy
from itertools import zip_longest
import re

from bank_retrieval_v5 import query_plan
from bank_answer_first import available_context
from bank_contract_v12 import metric_tags
from bank_evidence_relevance import relevance


def matches(pattern, text):
    return bool(re.search(pattern, text, re.I))


def it_cost_request(question):
    # The pronoun 'it' is not an IT department. Require the acronym in a cost
    # phrase, or the explicit subject, rather than a case-insensitive bare word.
    return matches(r'\binformation technology\b|\btechnology (?:services? )?(?:expenses?|costs?|bill)\b|\bit (?:services? )?(?:expenses?|costs?|bill)\b', question)


INVEST = r'\binvest(?:ing|ment|ments|ed|s)?\b|\bput(?:ting)? (?:more )?money\b'
STRATEGY = r'\bstrateg(?:y|ies|ic)\b|\bpriorit(?:y|ies|ise|ize|ising|izing)\b|\bfocus(?:ed|ing)?\b|\binitiatives?\b'
SPENDING = r'\bspend(?:ing|s)?\b|\bown (?:business|operations|investment)\b|\btechnology\b|\bdigital\b|\bartificial intelligence\b|\bAI\b|\bcyber\w*\b'
LENDING = r'\blend(?:ing|s)?\b|\bloans?\b|\bfinanc(?:ing|e)\b|\bcredit exposure\b'
COMPARATIVE = r'\bmore\b|\bmost\b|\blargest\b|\bbiggest\b|\brank(?:ing)?\b|\bhigher\b|\bincreas\w*\b|\bgrew\b|\bgrowth\b|\bcompar\w*\b'
AMOUNT = r'\bhow much\b|\bamounts?\b|\bcalculate\b|\bpercent(?:age)?\b|\bby how much\b|\bfigures?\b|\b\d+(?:\.\d+)?\s*%'
PERFORMANCE = (r'\bfinancial performance\b|\b(?:financial|earnings|results?) (?:highlights?|overview|summary)\b|'
               r'\b(?:major|key|notable|significant|important) (?:financial )?(?:changes?|results?|developments?)\b|'
               r'\bhow (?:did|has|have)\b.{0,65}\bperform(?:ed)?\b|'
               r'\b(?:overview|summary|summarise|summarize|review)\b.{0,65}\b(?:results|performance|earnings)\b')
PERFORMANCE_MEASURE = r'\bprofit\b|\bearnings\b|\bincome\b|\bmargin\b|\bexpenses?\b|\bcosts?\b|\bimpairment\b|\bdividends?\b|\breturn on equity\b|\bcapital\b|\bCET1\b|\bliquidity\b'
MOVEMENT = r'\bincreas\w*\b|\bdecreas\w*\b|\bgrowth\b|\bgrew\b|\bhigher\b|\blower\b|\brose\b|\bfell\b|\bdeclin\w*\b|\bimprov\w*\b|\breduc\w*\b|\bflat\b|\bstable\b'


def narrative_decision(question, topic_hint=None):
    """Recognise broad prose intent without treating every unknown metric as prose."""
    investing = matches(INVEST, question)
    strategy = matches(STRATEGY, question)
    spending = matches(SPENDING, question)
    lending = matches(LENDING, question)
    sector = matches(r'\bsectors?\b|\bindustr(?:y|ies)\b', question)
    portfolio_question = lending and not metric_tags(question) and matches(r'\bcategor(?:y|ies)\b|\btypes?\b|\bwhere\b|\bportfolio\b',question)
    general = matches(r'\brisks?\b|\bchallenges?\b|\bopportunities\b|\boutlook\b|\bsustainab\w*\b|\bscams?\b|\bfraud\b|\bprivacy\b|\bfinancial crime\b', question)
    # Broad result review is a research task, not a request for an unknown
    # numerical metric. Keep explicit metric lookups on their existing path.
    performance = (matches(PERFORMANCE, question) and not metric_tags(question)) or topic_hint == 'performance'
    if not (topic_hint or investing or strategy or spending or lending and sector or portfolio_question or general or performance):
        return None

    # Use existing company/period/privacy guards before any new clarification.
    base = query_plan('Explain: ' + question)
    if base['behavior'] == 'abstain':
        return {'status': 'unable_to_verify', 'message': base['reason']}
    if matches(r'\b(?:should|can) I\b.*\binvest|\b(?:buy|sell)\b.*\b(?:shares?|stocks?)\b', question):
        return {'status': 'unable_to_verify', 'message': 'I can explain bank disclosures, but cannot recommend where you should invest.'}
    context = available_context(question)
    report_years = re.findall(r'\b(?:FY)?(20\d{2})\s+(?:annual report|report|financial.performance (?:table|discussion))\b', question, re.I)
    if len(set(report_years)) == 1:
        # A prior-year comparative in a named report is not a request to search
        # two different report vintages for unrelated restatement disclosures.
        context['years'] = [int(report_years[0])]
    ambiguous = investing and not (spending or lending or strategy)
    topics = ['performance'] if performance else ['spending', 'lending'] if ambiguous else [
        'lending' if lending and not spending else 'spending' if spending else 'general' if general else 'strategy']
    if topic_hint in ('spending', 'lending', 'performance', 'general'):
        topics = [topic_hint]
        ambiguous = False
    if topics == ['lending'] and matches(r'\bimpairment\b|\bcredit losses\b|\barrears\b|\bdelinquen\w*\b', question):
        # Credit-risk commentary is not a list of lending destinations. Otherwise
        # the destination-only generation guard deletes the requested subject.
        topics = ['general']
    comparative = matches(COMPARATIVE, question)
    notes = context['defaults'][:]
    if performance:
        notes.append('This highlights a reported financial change, not necessarily the largest or most important change across the full report.')
    elif ambiguous:
        notes.append('Investment can mean the bank\'s own spending or its lending activity. Both interpretations are considered separately.')
    elif lending and topics == ['lending']:
        notes.append('Interpreting this as bank lending activity. Lending categories and borrower industry sectors are not necessarily the same.')
    requests = []
    for bank in context['banks']:
        for year in context['years']:
            for topic in topics:
                focus = {'lending': 'loan portfolio composition, lending categories and borrower industry sectors',
                         'spending': 'own investment spending, technology and business initiatives',
                         'strategy': 'strategy and investment priorities', 'general': question,
                         'performance': 'annual financial results: changes in profit, income, expenses and the reported reasons'}[topic]
                requests.append({'topic': topic, 'company': bank, 'year': year,
                    'query': f'Explain {bank} FY{year} reported {focus}.',
                    'followup': f'Explain {bank} FY{year} disclosures relevant to: {question}'})
    return {'status': 'search', 'requests': requests, 'notes': notes,
            'comparative': comparative, 'amount_requested': matches(AMOUNT, question),
            'question': question, 'topic': topics[0], 'company': context['banks'][0],
            'year': context['years'][0], 'query': requests[0]['query']}


def relevant_sections(sections, decision, question):
    """Keep literal, scoped excerpts; never turn topic frequency into a ranking."""
    pattern = {'lending': LENDING, 'spending': INVEST + '|' + SPENDING + r'|\bexpenses?\b|\bcosts?\b|\bstaff\b',
               'strategy': STRATEGY + '|' + INVEST,
               'performance': PERFORMANCE_MEASURE,
               'general': r'\w'}[decision['topic']]
    focus_patterns = [p for p in (
        r'\bartificial intelligence\b|\bAI\b', r'\bcyber\w*\b',
        r'\btechnology\b|\bdigital\b', r'\bclimate\b|\bdecarbon\w*\b',
        r'\bscams?\b|\bfraud\b',
        r'\bbranches\b|\bbranch\b',
    ) if matches(p, question)]
    if matches(r'\bstaff\b|\bpersonnel\b|\bwages?\b|\bsalar\w*\b|\bpayroll\b',question):
        focus_patterns=[r'\bstaff\b|\bpersonnel\b|\bwages?\b|\bsalar\w*\b|\blabour\b|\bpayroll\b']
    # Preserve the requested expense category. An overall operating-expense
    # explanation is not evidence for every individual cost line it contains.
    cost_subject = None
    if matches(r'\b(?:expenses?|costs?|bill)\b', question):
        if it_cost_request(question):
            cost_subject = r'\b(?:information technology|IT|technology)(?: services?)? (?:expenses?|costs?)\b'
        elif matches(r'\bstaff\b|\bpersonnel\b|\bwages?\b|\bsalar\w*\b', question):
            cost_subject = r'\b(?:staff|personnel) (?:expenses?|costs?)\b'
    from bank_query_routing import explanation_subject
    subject = explanation_subject(question)
    from answer_bank_release import excluded_terms
    distinct_terms = excluded_terms(question)
    kept = []
    seen = set()
    chars = 0
    for section in sections:
        source = section['source']
        if source['company'] != decision['company'] or source['report_year'] != decision['year']:
            continue
        # Do not label half-year fee commentary as a full-year portfolio answer.
        if matches(r'half year|six months', section.get('heading', '')) and not matches(r'half.year|six months', question):
            continue
        fresh = []
        for e in section['excerpts']:
            body = e['quote']
            if not relevance(question,body)[0]:
                continue
            if distinct_terms and not any(matches(t['pattern'], body) for t in distinct_terms):
                continue
            if subject and not matches(r'^\s*(?:Group\s+)?' + subject + r'.{0,100}\b(?:increas\w*|decreas\w*|grew|fell|rose|was|were|reflect\w*|driven|due)\b', body):
                continue
            if e['source_id'] in seen or not matches(pattern, body):
                continue
            if focus_patterns and not any(matches(p, body) for p in focus_patterns):
                continue
            if cost_subject and not matches(cost_subject, body):
                continue
            if decision['topic'] == 'performance':
                if not matches(MOVEMENT, body) or matches(r'\bremuneration\b|\bincentive\b|\bvesting\b', body):
                    continue
            if decision['topic'] == 'lending':
                if matches(r'\bgrew\b|\bgrow\w*\b|\bexpand\w*\b|\bincreas\w*\b', question):
                    # A lower LVR or better loan-origination system does not
                    # establish growth in a customer lending category.
                    if not matches(r'\b(?:loans?|lending|balances|consumer finance)\b.{0,65}\b(?:grew|growth|increas\w*|expand\w*)\b|\b(?:increas\w*|growth|expand\w*)\b.{0,65}\b(?:loans?|lending|consumer finance)\b', body):
                        continue
                if matches(r'\bimpairment\b|\barrears\b|\bdelinquen\w*\b|\bcredit losses\b', body) and not matches(r'\brisk\b|\bimpairment\b|\barrears\b', question):
                    continue
                # Funding a portfolio and earning fees are not descriptions of
                # its lending destinations. Keep mixed passages only if they
                # also explicitly discuss loans or industry composition.
                if matches(r'fees?|deposits?|funding|non-lending', body) and not matches(r'\bloans?\b|\bindustr(?:y|ies)\b|\bsectors?\b', body):
                    continue
            fresh.append(e)
        size = sum(len(e['quote']) for e in fresh)
        # Keep complete units, not arbitrary clipped sentences. Fewer excerpts
        # can be retained when a section is large; this is reported as partial.
        if not fresh or size > 5500 or chars + size > 5500:
            continue
        kept.append({**deepcopy(section), 'excerpts': deepcopy(fresh)})
        seen.update(e['source_id'] for e in fresh)
        chars += size
        if len(kept) == 4:
            break
    return kept


def prefer_complete_driver_context(sections, question):
    """A complete, explicitly requested driver list beats incidental mentions.

    Restrict this reduction to one named subject and an explanation request.
    Multi-subject questions keep the broader packet. Never infer the list is an
    exhaustive answer to a report-wide question.
    """
    if not matches(r'\bwhy\b|\breasons?\b|\bdrivers?\b|\bexplain\b', question):
        return sections
    patterns = (r'\bloan impairment expenses?\b', r'\bcredit impairment charges?\b', r'\bstaff expenses?\b',
                r'\boperating expenses?\b', r'\bnet interest income\b',
                r'\binformation technology services expenses?\b')
    requested = [p for p in patterns if matches(p, question)]
    if len(requested) != 1:
        return sections
    for section in sections:
        excerpts = section.get('excerpts', [])
        if len(excerpts) == 1 and excerpts[0].get('component_source_ids'):
            intro = excerpts[0]['quote'].split('•', 1)[0]
            if matches(requested[0], intro):
                return [section]
    if sections and not matches(r'\bboth\b|\bcompare\b|\bcash\b.*\bstatutory\b|\bstatutory\b.*\bcash\b',question):
        # One direct, complete driver paragraph is preferable to repeating the
        # same story from cash and statutory reports without distinguishing them.
        direct=[s for s in sections if any(matches(requested[0],e['quote'].split('.',1)[0])
                and matches(r'\bdue to\b|\bdriven\b|\breflect\w*\b',e['quote']) for e in s.get('excerpts',[]))]
        if direct:return direct[:1]
    return sections


def narrative_evidence(question, decision, retrieve, full_search=None):
    def matching_documents(items):
        allowed = decision.get('source_documents')
        return [s for s in items if not allowed or s['source'].get('document_id') in allowed]

    sections = []
    coverage = []
    searches = []
    seen = set()
    budget = 0
    scoped_candidates = []
    for request in decision.get('requests', [decision]):
        selected = []
        if full_search is not None and request['company'] in ('CBA','NAB'):
            # Preserve the complete positive request; only strip an explicitly
            # rejected alternative. A model-selected noun can omit qualifiers.
            search_question=re.split(r'\brather than\b',question,maxsplit=1,flags=re.I)[0]
            # Lists need a wider candidate pool than single-fact questions.
            # The existing relevance, scope and final evidence budgets still
            # apply. Do not insert expected categories or evaluation answers.
            broad_list = matches(r'\blist\b|\bkinds?\b|\btypes?\b|\bcategories\b', question)
            from bank_query_routing import explanation_subject
            subject = explanation_subject(search_question)
            options={'top_k':30 if broad_list else 10}
            if subject: options['purpose'] = 'explanation'
            if request['company']=='NAB': options['company']='NAB'
            candidates=full_search(search_question,request['year'],**options)
            selected=prefer_complete_driver_context(matching_documents(relevant_sections(candidates,request,search_question)),search_question)
            searches.append({'query':search_question,'scope':request['company']+' full-report prose','relevant_sections':len(selected),
                             'ranked_sources':[{'source':s['source'],'score':s.get('retrieval_score')} for s in candidates]})
        # One primary search and at most one targeted follow-up per scope.
        for query in dict.fromkeys([request['query'], request.get('followup', request['query'])]):
            # Full-report search has already ranked a wider corpus. Re-running
            # the legacy retriever merely to reach two snippets duplicates the
            # same paragraph under another extractor ID and loads another model.
            if selected:break
            result = retrieve(query)
            candidates = matching_documents(relevant_sections(result['answer'].get('source_excerpts', []), request, question))
            searches.append({'query': query, 'relevant_sections': len(candidates)})
            selected += candidates
            if len(selected) >= 2:
                break
        scoped_candidates.append((request, selected[:4]))
        coverage.append({'company': request['company'], 'year': request['year'], 'topic': request['topic'], 'sections': 0})
    # Pack one passage from each requested scope before taking a second. A
    # comparison must not spend the entire context budget on its first year.
    seen_quotes = set()
    for round_sections in zip_longest(*(items for _, items in scoped_candidates)):
        for index, section in enumerate(round_sections):
            if section is None:
                continue
            request = scoped_candidates[index][0]
            def quote_key(e):
                return (section['source'].get('company'), section['source'].get('report_year'),
                        section['source'].get('document_id'), section['source'].get('pdf_page'),
                        re.sub(r'\s+', ' ', e['quote']).strip())
            fresh = [e for e in section['excerpts'] if e['source_id'] not in seen and quote_key(e) not in seen_quotes]
            size = sum(len(e['quote']) for e in fresh)
            if not fresh or size + budget > 5500:
                continue
            sections.append({**section, 'excerpts': fresh,
                             'research_scope': {k: request[k] for k in ('company', 'year', 'topic')},
                             'heading': f"{request['company']} FY{request['year']} / {request['topic']}: " + section['heading']})
            seen.update(e['source_id'] for e in fresh)
            seen_quotes.update(quote_key(e) for e in fresh)
            budget += size
            coverage[index]['sections'] += 1
    performance = decision['topic'] == 'performance'
    limitations = [
        'Only selected report pages were searched, not the entire report. This is a supported example, not an exhaustive ranking of financial changes.',
        'Reporting bases remain distinct: cash earnings and statutory profit are not interchangeable. Reasons are attributed to the report, not independently established causes.',
    ] if performance else [
        'Narrative search covers selected indexed pages, not every page of all six reports. The excerpts are not a complete inventory of the bank\'s priorities.',
        'Reported priorities and initiatives do not by themselves establish spending amounts, year-on-year increases or a ranking of investment areas.',
    ]
    if not sections:
        answer = {'status': 'unable_to_verify', 'message':
            'I could not retrieve sufficiently relevant commentary for this question from the selected indexed pages. '
            'This does not establish that the full reports contain no answer. No unsupported change or ranking has been inferred.',
            'limitations': limitations}
    else:
        answer = {'status': 'partial_answer',
            'mode': 'report_narrative', 'source_excerpts': sections, 'limitations': limitations,
            'message': 'The source excerpts below describe reported financial changes.' if performance else 'The source excerpts below discuss the bank\'s reported priorities or initiatives.'}
        if not performance and (decision['comparative'] or decision.get('amount_requested')):
            answer['message'] += (' They do not establish which area received the most money or the largest increase. '
                                  'This demo has not verified comparable spending or sector-lending amounts, so that part remains unanswered.')
    full=any(s.get('scope','').endswith('full-report prose') for s in searches)
    if full:
        limitations[0]='CBA and NAB prose search includes all six reports. Retrieved passages are not exhaustive; unvalidated tables and image-only content are not calculation-ready.'
        answer['limitations']=limitations
        answer['message']=answer['message'].replace('selected indexed pages','searchable report evidence')
    if decision['topic']=='general':
        answer['limitations'][1]='Cited passages support only what the source explicitly discloses. Quoted figures are not newly calculated results or a complete review of every report.'
    notes = decision.get('notes', [])
    answer['message'] = ' '.join(notes + [answer['message']])
    return dict(question=question, answer=answer,
                  narrative_request={k: v for k, v in decision.items() if k != 'query'},
                  research_coverage=coverage, research_searches=searches,
                  full_report_search=full,
                  interpretation={'retrieval_question': decision['query'], 'notes': notes})
