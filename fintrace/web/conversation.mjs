import {METRICS, formatValue, human, presentedClaim, collectEvidence, documentLink, changeUnit, validateResult} from '/ui-model.mjs';
const $ = id => document.getElementById(id);
const state = {ready:false, busy:false, turns:[], current:null, documents:[], sequence:0};
function el(tag, cls='', text) { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=String(text); return n; }
function announce(text){$('announcement').textContent=text;}
function scope(){return {company:$('company-filter').value,year:$('year-filter').value};}
function setScope(value={}){$('company-filter').value=value.company||'all';$('year-filter').value=value.year||'all';}
function update(){ $('char-count').textContent=$('question').value.length; $('ask').disabled=!state.ready||state.busy;
  $('ask').textContent=state.busy?'Reading reports...':'Ask FinTrace';
  for(const id of ['question','company-filter','year-filter','new-session','mobile-new'])$(id).disabled=state.busy;
  document.querySelectorAll('[data-question],#history button').forEach(n=>n.disabled=state.busy);
}
async function connect(){try{const r=await fetch('/health',{signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error();const h=await r.json();state.ready=h.status==='ready';
  if(!state.ready)throw Error();$('connection').textContent='Local backend connected';$('connection').className='ready';$('reconnect').hidden=true;
  const d=await fetch('/documents');if(d.ok)state.documents=(await d.json()).documents||[];
}catch{state.ready=false;$('connection').textContent='Backend unavailable';$('connection').className='';$('reconnect').hidden=false;}update();}
function closeDesk(){$('source-desk').hidden=true;}
function showSource(entry){const s=entry.source;const box=$('source-content');box.replaceChildren(el('h3','',s.document_title),el('p','muted',`PDF page ${s.pdf_page} / FY${s.report_year}`));
 const url=documentLink(s,state.documents);if(url){const a=el('a','','Open original report at this page');a.href=url;a.target='_blank';a.rel='noopener noreferrer';box.append(a);}
 for(const q of entry.quotes){box.append(el('blockquote','',q.text),el('small','',q.id));}
 $('source-desk').hidden=false;$('source-desk').focus();}
function sourceButton(source,evidence){const e=evidence.find(x=>x.source.document_id===source.document_id&&x.source.pdf_page===source.pdf_page);if(!e)return null;
 const b=el('button','citation',String(e.number));b.type='button';b.setAttribute('aria-label',`Source ${e.number}: ${source.document_title}, PDF page ${source.pdf_page}`);b.addEventListener('click',()=>showSource(e));return b;}
function detail(title,body){const d=el('details','details');d.append(el('summary','',title));const inner=el('div','details-content');inner.append(body);d.append(inner);return d;}
function figures(answer){const wrap=el('div','table-wrap'),table=el('table'),head=el('thead'),tr=el('tr');
 for(const label of ['Measure','Period end','Value','Basis / scope'])tr.append(el('th','',label));head.append(tr);table.append(head);const body=el('tbody');
 for(const p of answer.parts||[])for(const claim of p.claims||[]){const c=claim.cell,v=presentedClaim(claim),r=el('tr');
 for(const text of [`${c.company} / ${METRICS[c.metric]||human(c.metric)}`,c.period_end,`${formatValue(v.value)} ${v.unit}`,[human(c.basis),human(c.scope)].join(' / ')])r.append(el('td','',text));body.append(r);}
 table.append(body);wrap.append(table);return wrap;}
function workings(calcs,evidence){const wrap=el('div');for(const c of calcs){const item=el('div','calc');item.append(el('strong','',c.operation==='share'?`${formatValue(c.left)} / ${formatValue(c.right)} × 100 = ${Number(c.result).toFixed(2)}%`:`${formatValue(c.left)} - ${formatValue(c.right)} = ${formatValue(c.absolute_change)} ${changeUnit(c)}`));
 item.append(el('p','',c.note||'Calculated from the cited source cells.'));
 for(const cell of c.source_cells||[]){const p=el('p','',`${cell.company} / ${METRICS[cell.metric]||cell.metric} / ${cell.period_end} / ${human(cell.basis)} / ${human(cell.scope)}. `);const b=sourceButton(cell.source,evidence);if(b)p.append(b);item.append(p);}wrap.append(item);}return wrap;}
function render(entry){const result=entry.result,a=result.answer,evidence=collectEvidence(a),card=entry.node;card.replaceChildren(el('h2','question-heading',entry.question));
 const meta=el('div','answer-heading');meta.append(el('strong','','FinTrace'),el('span','',`${Number(result.seconds||0).toFixed(1)}s / ${result.generation?.status==='source_selected'?'selected report passages':result.generation?.status==='generated'?'source-grounded explanation':result.generation?.status==='fallback'?'report wording':a.parts?.length?'source-backed figures':'evidence limits'}`));card.append(meta);
 const body=el('div','answer-body');const intro=result.comparison_policy?a.message:result.premise_check?a.message:result.causality_note;
 if(intro)body.append(el('p','qualification',intro));
 const prose=result.presentation?.paragraphs||[{text:a.message||'No supported answer was returned.',citations:[],kind:'limit'}];
 for(const para of prose){const p=el('p',para.kind==='quotation'?'quotation':para.kind==='limit'?'limit':'',para.text);for(const source of para.citations||[]){const b=sourceButton(source,evidence);if(b)p.append(' ',b);}body.append(p);}
 if(a.unanswered_parts?.length)body.append(el('p','qualification','Not answered: '+a.unanswered_parts.join(', ')+'. These measures are outside the validated numerical scope.'));
 for(const note of result.presentation?.important_notes||[])body.append(el('p','qualification',note));
 card.append(body);
 if(result.ui_scope){const context=el('div','scope-note');context.append(el('p','',result.ui_scope.summary));for(const note of result.ui_scope.notes||[])context.append(el('p','',note));card.append(context);}
 const actions=el('div','answer-tools');if(evidence.length){const b=el('button','',`Sources (${evidence.length})`);b.addEventListener('click',()=>showSource(evidence[0]));actions.append(b);}
 const copy=el('button','','Copy answer');copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(result.display_text||body.innerText);copy.textContent='Copied';}catch{copy.textContent='Select the answer to copy';}});actions.append(copy);
 const download=el('button','','Download JSON');download.addEventListener('click',()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const link=el('a');link.href=u;link.download='fintrace-answer.json';link.click();setTimeout(()=>URL.revokeObjectURL(u),1000);});actions.append(download);card.append(actions);
 if(a.parts?.some(p=>p.claims?.length))card.append(detail('Source figures and reporting bases',figures(a)));
 const calcs=(a.parts||[]).flatMap(p=>p.calculations||[]);if(calcs.length)card.append(detail(`Calculation workings (${calcs.length})`,workings(calcs,evidence)));
 if(evidence.length){const content=el('div');for(const e of evidence){const section=el('section','source-entry');const title=el('h3','',`${e.source.document_title} / PDF ${e.source.pdf_page}`);const b=sourceButton(e.source,evidence);if(b)title.append(' ',b);section.append(title);for(const q of e.quotes)section.append(el('blockquote','',q.text));content.append(section);}card.append(detail('Read the source excerpts',content));}
 const qualifications=result.presentation?.qualifications||a.limitations||[];if(qualifications.length){const content=el('div');for(const q of qualifications)content.append(el('p','',q));card.append(detail('Interpretation and limitations',content));}
 if(a.status==='partial_answer')card.append(el('p','scope-note','Some parts or evidence coverage are limited. See interpretation and sources.'));
 if(result.generation?.status==='generated')card.append(el('p','scope-note','Generated wording has automated checks, not independent verification.'));
 card.tabIndex=-1;state.current=entry;history();}
function history(){$('history').replaceChildren();$('history-empty').hidden=state.turns.length>0;for(const e of [...state.turns].reverse()){if(!e.result)continue;const li=el('li'),b=el('button','',e.question);b.type='button';b.disabled=state.busy;b.setAttribute('aria-current',String(state.current===e));b.addEventListener('click',()=>{state.current=e;setScope(e.result.ui_scope?.effective);e.node.scrollIntoView({block:'start'});e.node.focus({preventScroll:true});history();});li.append(b);$('history').append(li);}}
async function ask(event){event.preventDefault();if(!state.ready||state.busy)return;const question=$('question').value.trim();if(!question||question.length>2000){$('input-error').textContent='Enter a question between 1 and 2,000 characters.';$('input-error').hidden=false;return;}
 const selected=scope(),previous=state.current?.result.effective_question;state.busy=true;update();$('welcome').hidden=true;$('input-error').hidden=true;
 const card=el('article','turn');card.id='turn-'+(++state.sequence);card.append(el('h2','question-heading',question));const loading=el('p','busy','Reading the report evidence...');card.append(loading);$('conversation').append(card);card.scrollIntoView({block:'start'});
 const started=Date.now();const ticker=setInterval(()=>{loading.textContent=`Reading the report evidence... ${Math.floor((Date.now()-started)/1000)}s. The first request can take longer while local models load.`;},1000);announce('Reading the reports.');
 try{const payload={question,scope:selected};if(previous)payload.previous_question=previous;const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(180000)});const result=await r.json();if(!r.ok)throw Error(result.error||'No answer returned');validateResult(result);
 const entry={question,result,node:card};state.turns.push(entry);if(state.turns.length>8){state.turns.shift().node.remove();}render(entry);setScope(result.ui_scope?.effective||selected);$('question').value='';card.focus({preventScroll:true});announce('Answer ready. Sources and calculations are available below it.');
 }catch(error){card.replaceChildren(el('h2','question-heading',question),el('p','error',error.name==='TimeoutError'?'The browser stopped waiting after three minutes. The backend may still be working. Wait before trying again.':error.message||'Could not reach the local backend.'));const retry=el('button','','Restore this question');retry.addEventListener('click',()=>{$('question').value=question;setScope(selected);update();$('question').focus();});card.append(retry);announce('No answer returned.');
 }finally{clearInterval(ticker);state.busy=false;update();history();}}
function newSession(){if(state.busy)return;state.turns=[];state.current=null;$('conversation').replaceChildren();$('welcome').hidden=false;$('question').value='';setScope();closeDesk();history();update();$('question').focus();announce('New conversation. Earlier question context cleared.');}
$('question-form').addEventListener('submit',ask);$('question').addEventListener('input',update);$('question').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('question-form').requestSubmit();}});
document.querySelectorAll('[data-question]').forEach(b=>b.addEventListener('click',()=>{$('question').value=b.dataset.question;update();$('question').focus();}));
for(const id of ['new-session','mobile-new'])$(id).addEventListener('click',newSession);$('reconnect').addEventListener('click',connect);$('close-source').addEventListener('click',closeDesk);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDesk();});
for(const id of ['show-scope','mobile-scope'])$(id).addEventListener('click',()=>{$('scope').hidden=!$('scope').hidden;if(!$('scope').hidden){$('scope').scrollIntoView();$('scope').focus();}});
for(const id of ['show-library','mobile-library'])$(id).addEventListener('click',()=>{const content=$('source-content');content.replaceChildren(el('h3','','Report library'));for(const d of state.documents){const block=el('section','library-item'),url=documentLink({document_id:d.id,pdf_page:1},state.documents);if(url){const a=el('a','',d.title);a.href=url;a.target='_blank';a.rel='noopener noreferrer';block.append(a);}else block.append(el('p','',d.title+' (unavailable)'));block.append(el('p','',`Year end: ${d.period_end}. ${human(d.role)}.`));content.append(block);}$('source-desk').hidden=false;$('source-desk').focus();});
connect();
