"""Conversational orchestration around the existing evidence and arithmetic paths."""
from copy import deepcopy
from decimal import Decimal
import re
from time import perf_counter
from answer_bank_release import Backend as PreviousBackend
from bank_answer_first import available_context
from bank_contract_v12 import metric_tags
from bank_conversation import present
from bank_query_routing import normalise_query, checked_numeric_request, definition_request, explanation_subject, generic_loan_lookup


def stopped(question, message, status='unable_to_verify'):
    return {'question': question, 'answer': {'status': status, 'message': message},
            'route': 'guard', 'generation': {'status': 'skipped'}}


def direct_numeric_lookup(question):
    return checked_numeric_request(question)


class Backend:
    version = 'fintrace-conversational-development'

    def __init__(self, core=None):
        self.use_cba_reports = core is None
        self.core = core if core is not None else PreviousBackend()
        self.intent_planner = None

    def answer(self, question):
        start = perf_counter()
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError('Question must contain 1-2000 characters')
        budget = getattr(self, 'provider_budget', None)
        calls_before = budget.calls if budget else 0
        interpreted, corrections = normalise_query(question)
        result = self.respond(interpreted)
        if corrections:
            result['query_normalisation'] = {'question': interpreted, 'changes': corrections}
            result['answer'].setdefault('limitations', []).append(
                'Wording interpreted as: ' + interpreted)
        result.update(question=question, version=self.version, seconds=perf_counter()-start)
        if getattr(self, 'inference_provider', None) == 'groq':
            result['inference'] = {'provider': 'groq', 'model': self.provider_model,
                                   'attempted_calls': budget.calls - calls_before,
                                   'session_calls': budget.calls,
                                   'session_halted': budget.halted_reason}
            result['answer'].setdefault('important_notes', []).append(
                'Experimental Groq mode: questions and selected public-report excerpts may be sent to Groq. Financial calculations remain local. No web search is used.')
        return present(result)

    def respond(self, question):
        context = available_context(question)
        if re.search(r'\b(?:should|would|can) I\b|\brecommend\b',question,re.I) and re.search(r'\bshares?\b|\bstocks?\b|\binvest\w*\b|\bsavings\b',question,re.I):
            return stopped(question,'I can explain the historical reports, but cannot recommend buying shares or moving your savings. Reported profit growth alone does not establish whether an investment is suitable for you.')
        if context['plan']['behavior'] == 'abstain':
            return stopped(question, context['plan']['reason'])
        if re.search(r'\bpayback\b|\bpaid back\b|\bpay(?:s|ing)? (?:itself|back)\b|\breturn on investment\b|\bROI\b',question,re.I):
            return stopped(question,'I cannot verify project payback or return-on-investment rankings from the checked evidence. That requires project-level costs, benefits and timing. Spending amounts or spending growth are not a substitute for investment returns.')
        # An annual investment table cannot answer another reporting window.
        if re.search(r'\binvest\w*\b|\bspend\w*\b|\bmoney\b', question,re.I) and re.search(r'half.year|six months|quarter\w*|calendar year|January.*December',question,re.I):
            return stopped(question,'The checked investment figures cover full financial years ending 30 June for CBA. I have not validated this requested shorter or calendar-year period, so I will not substitute the annual total. The full report may contain additional period disclosures.')
        if re.search(r'\bwill\b|\bguarantee\w*\b|\bpredict\w*\b|\bnext year\b|\bkeep (?:rising|growing)\b',question,re.I) and re.search(r'\bprofit\b|\breturn\w*\b|\bearnings\b',question,re.I):
            return stopped(question,'Historical report figures do not establish future profit or returns. Investment and profit moving together do not prove causation or guarantee continued growth. I can compare the disclosed historical results, but cannot verify that prediction.')
        if re.search(r'\b(?:customer|person|account holder)\b.*\bnamed\b|\b(?:individual|person|named customer)\b.*\b(?:balance|account number|transactions?)\b|\b(?:balance|transactions?)\b.*\b(?:a|an|one|named) customer\b',question,re.I):
            return stopped(question,'These are public corporate reports, not customer account records. I cannot establish an individual customer\'s balance, account number or transactions from them.')
        if self.use_cba_reports:
            if generic_loan_lookup(question):
                # Offer a labelled disclosed alternative, not a silent total/net
                # alias. The existing binder must still establish the figure.
                alternative=re.sub(r'\btotal loans\b','gross loans and acceptances',question,flags=re.I)
                result=self.core.answer(alternative)
                result['answer'].setdefault('important_notes',[]).insert(0,
                    'For "total loans", the disclosed measure shown is gross loans and acceptances, before impairment allowances. This is not a net-loan total; a different definition needs its own evidence.')
                return result
            from bank_statement_tables import answer as statement_answer
            try:
                statement = statement_answer(question, context)
            except (ValueError, OSError) as error:
                return stopped(question, 'The additional statement-table checks did not pass. No numerical answer was inferred. ' + str(error))
            if statement is not None:
                return statement
        # Check an assumed numeric direction before model routing can return
        # early through the narrative path. This guard applies in production,
        # not only when a test injects a simplified core.
        premise = self.check_directional_premise(question)
        if premise is not None:
            return premise
        if self.use_cba_reports:
            from cba_investment_answer import eligible, answer as investment_answer
            from answer_bank_release import conceptual, excluded_terms
            from bank_conversational_intent import IntentPlanner
            from answer_bank_simplified import split_mixed
            plan = None
            if len(context['banks']) == 1:
                from bank_report_library import get_library
                unknown = get_library().unmatched_subject(question)
                if unknown:
                    return stopped(question, 'I could not match the requested subject (' + ', '.join(unknown) + ') in the searchable bank report text. I will not substitute a different project or broader spending category. Check the name or provide a source page; this search result does not prove that the subject is absent from every image or disclosure.')
            # Recognised financial requests cannot be vetoed by a stochastic
            # topic label. The core still enforces all evidence and scope gates.
            if split_mixed(question) or (direct_numeric_lookup(question) and not excluded_terms(question)):
                return self.core.answer(question)
            if definition_request(question):
                return self.core.finish(self.core.evidence_backend.definition(question, excluded_terms(question)), question)
            if excluded_terms(question) and not re.search(r'\b(?:share|stock) price\b|market cap|\bcurrent rating\b', question, re.I):
                # Numerical validation scope is not document-reading scope.
                # This path quotes the requested disclosure; it never calculates
                # an unsupported measure or binds a neighbouring KPI.
                return self.core.research(question, 'general')
            if explanation_subject(question) and not excluded_terms(question):
                # A named expense's drivers must not become a broad performance
                # summary merely because the planner sees "financial performance".
                return self.core.research(question, 'general')
            if len(context['banks'])==1 and context['banks'][0] in ('CBA','NAB'):
                # Keep named numerical measures, definitions and exclusions on
                # their proven paths. The model selects tools, never new aliases.
                direct_numeric=direct_numeric_lookup(question)
                if not direct_numeric and not conceptual(question) and not excluded_terms(question):
                    if self.intent_planner is None: self.intent_planner = IntentPlanner()
                    plan = self.intent_planner.plan(question)
                    if plan.get('advice') or plan['topic']=='unsupported' or plan.get('task')=='unsupported':
                        result=stopped(question,'I cannot establish the requested conclusion or measure from the checked evidence. Historical spending totals do not establish individual-project payback, undisclosed budgets, future returns or personal investment recommendations. I will not substitute a spending category or neighbouring measure. This is a verification limit, not proof that every report lacks the information.')
                        result['intent_plan']=plan
                        return result
                    if plan.get('task')=='definition' or re.search(r'\bwhen\b.*\bsays?\b|\bis it talking about\b',question,re.I):
                        result=self.core.finish(self.core.evidence_backend.definition(question,excluded_terms(question)),question)
                        result['intent_plan']=plan
                        return result
                    narrative_comparison = bool(re.search(r'\breasons?\b|\bdrivers?\b|\bwhy\b', question, re.I))
                    if plan.get('task')=='comparison' and metric_tags(question) and not narrative_comparison:
                        query=('Calculate the year-on-year change: '+question) if len(set(re.findall(r'20\d{2}',question)))==2 else question
                        result=self.core.answer(query)
                        result['intent_plan']=plan
                        return result
            if not excluded_terms(question) and eligible(question,context,plan):
                from cba_report_library import get_library
                try:
                    result=investment_answer(question,context,get_library(),plan)
                    result['intent_plan']=plan or {'status':'literal_route'}
                    return result
                except (ValueError,OSError) as error:
                    return stopped(question,'The CBA source-table checks could not be completed. No investment amount or ranking is inferred. '+str(error))
            if plan and (plan['topic'] in ('spending','lending','performance','general') or plan.get('task') in ('explanation','causality')):
                topic=plan['topic'] if plan['topic'] in ('spending','lending','performance','general') else 'general'
                result=self.core.research(question,topic,plan.get('subject'))
                result['intent_plan']=plan
                if plan.get('task')=='causality' or re.search(r'\bcause[ds]?\b|\bprove[ds]?\b|\bresponsible for\b',question,re.I):
                    result['causality_note']='The report can describe management\'s explanation; these disclosures alone do not establish that one factor caused another.'
                    result['answer'].setdefault('limitations',[]).append(result['causality_note'])
                return result
        if re.fullmatch(r'\s*(?:what about (?:that|this|it|CBA|NAB)|and (?:in )?(?:FY)?20\d{2}|why|explain that)[?.!]?\s*', question, re.I):
            return stopped(question, 'I need the earlier subject to answer this follow-up. Which result or report passage are you referring to?', 'clarify')
        judgement = re.search(r'\bbetter\b|\bmore successful\b|\bstronger performance\b|\bperformed best\b', question, re.I)
        if judgement and not metric_tags(question) and re.search(r'\bbanks?\b|\bCBA\b|\bNAB\b', question, re.I):
            banks = context['banks']
            parts, limits = [], []
            for bank in banks:
                for year in context['years']:
                    branch = self.core.answer(f'What was {bank} cash profit and statutory profit in FY{year}?')
                    parts.extend(branch['answer'].get('parts', []))
                    if branch['answer']['status'] != 'source_bound_answer':
                        limits.append(branch['answer'].get('message', 'A requested profit comparison was unavailable.'))
            return {'question': question, 'route': 'numeric', 'generation': {'status':'skipped'},
                'comparison_policy': 'Disclosed profit measures, not an overall ranking',
                'answer': {'status': 'partial_answer' if parts else 'unable_to_verify', 'parts': parts,
                    'message': 'There is no single overall winner without choosing what "better" means. Here are the disclosed cash and statutory profit figures as a starting point, not a performance ranking. Larger profit alone does not establish better efficiency, risk or shareholder returns.',
                    'limitations': (['CBA ends its financial year on 30 June; NAB ends on 30 September. These reporting windows differ.'] if len(banks)>1 else []) + limits}}
        causal = re.search(r'\bcause[ds]?\b|\bprove[ds]?\b|\bresponsible for\b|\bresulted in\b', question, re.I)
        result = self.core.answer(question)
        if self.use_cba_reports and result['answer']['status'] in ('clarify', 'unable_to_verify'):
            if not re.search(r'\b(?:predict\w*|future|next year|live|today|current|private|customer account|share price|stock price|market cap)\b', question, re.I):
                research = self.core.research(question, 'general')
                if research['answer'].get('source_excerpts'):
                    research['answer'].setdefault('important_notes', []).append(
                        'This is a report-evidence answer, not a newly validated calculation. The original numerical check could not establish all requested figures.')
                    return research
        if result['answer']['status']=='clarify' and re.search(r'Name a measure|requested measure is not clear',result['answer'].get('message',''),re.I):
            result=stopped(question,'I could not verify this specific request with the available evidence and checked numerical measures. That is a limitation of this system, not proof that the full reports contain no answer. I will not substitute a similarly named figure.')
        if causal:
            note = ('These disclosures can report management\'s explanation, but they do not independently prove that one factor caused another. '
                    'A change in spending alongside a change in profit is not enough to establish causation.')
            result['causality_note'] = note
            result['answer'].setdefault('limitations', []).insert(0, note)
        return result

    def check_directional_premise(self, question):
        """Validate the direction before a prose explanation, for either core."""
        premise = re.match(r'\s*why (?:did|has|have)\b', question, re.I)
        falling = re.search(r'\bfall|\bfell\b|\bdeclin\w*\b|\bdrop\w*\b|\bdecreas\w*\b', question, re.I)
        rising = re.search(r'\brise|\brose\b|\bgrow|\bgrew\b|\bincreas\w*\b', question, re.I)
        if premise and (falling or rising) and (metric_tags(question) or re.search(r'\bprofit\b', question, re.I)):
            query = re.sub(r'^\s*why (?:did|has|have)\s+', 'Compare ', question, flags=re.I)
            query = re.sub(r'\b(?:fall\w*|fell|declin\w*|drop\w*|decreas\w*|rise\w*|rose|grow\w*|grew|increas\w*)\b', 'change', query, flags=re.I)
            years = sorted(set(int(y) for y in re.findall(r'20\d{2}', query)))
            assumed_period = None
            if len(years) == 1 and years[0] == 2025:
                query += ' Compare FY2024 to FY2025.'
                assumed_period = 'For the stated FY2025 movement, checking FY2024 to FY2025 on a compatible reporting basis.'
            checked = None
            if self.use_cba_reports:
                from bank_statement_tables import answer as statement_answer
                try:
                    checked = statement_answer(query, available_context(query))
                except (ValueError, OSError) as error:
                    return stopped(question, 'The statement-table checks failed while checking the assumed movement. ' + str(error))
            if checked is None:
                checked = self.core.answer(query)
            if assumed_period:
                checked['answer'].setdefault('limitations', []).append(assumed_period)
            calculations = [c for p in checked['answer'].get('parts', []) for c in p.get('calculations', [])]
            directional = []
            for calc in calculations:
                cells = calc.get('source_cells', [])
                if len(cells) != 2 or cells[0]['period_end'] <= cells[1]['period_end']:
                    continue
                delta = Decimal(str(calc['absolute_change']))
                mismatch = delta >= 0 if falling else delta <= 0
                directional.append({'metric': cells[0]['metric'], 'matches_question': not mismatch})
            if directional and any(not d['matches_question'] for d in directional):
                checked['premise_check'] = directional
                checked['answer']['message'] = 'The question assumes a direction of change that does not match the cited comparison. The figures and calculation below show the reported movement; I will not invent a reason for a movement that did not occur.'
                return checked
            if not directional:
                checked['premise_check'] = {'verified': False}
                checked['answer']['status'] = 'partial_answer' if checked['answer'].get('parts') else 'unable_to_verify'
                checked['answer']['message'] = 'I could not verify the assumed direction of change on a compatible reporting basis, so I cannot safely explain it as a fact.'
                return checked
            if self.use_cba_reports and explanation_subject(question):
                cells = [c for calc in calculations for c in calc.get('source_cells', [])]
                documents = {c['source']['document_id'] for c in cells}
                bases = {c['basis'] for c in cells}
                research_question = question
                if len(bases) == 1:
                    research_question += ' On the ' + next(iter(bases)) + ' reporting basis.'
                result = self.core.research(research_question, 'general', source_documents=documents)
                result['answer'].setdefault('limitations', []).append(
                    'The movement is checked first; explanatory passages are restricted to its source report(s). Different reporting bases are not interchangeable.')
            else:
                result = self.core.answer(question)
            result['premise_check'] = directional
            result['answer']['parts'] = deepcopy(checked['answer'].get('parts', []))
            if assumed_period:
                result['answer'].setdefault('limitations', []).append(assumed_period)
            return result
        return None
