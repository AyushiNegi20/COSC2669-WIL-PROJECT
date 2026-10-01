import { EXAMPLES, METRICS, statusInfo, formatValue, human, presentedClaim, sourceKey,
  collectEvidence, documentLink, changeUnit, validateResult } from "/ui-model.mjs";

const $ = id => document.getElementById(id);
const state = { connected: false, busy: false, history: [], current: null, evidence: [], documents: [] };
let historySequence = 0;
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function announce(text) { $("announcement").textContent = text; }
function issue(text) { return el("p", "issue", text); }
function updateForm() {
  $("char-count").textContent = $("question").value.length;
  $("ask-button").disabled = !state.connected || state.busy;
  $("ask-button").textContent = state.busy ? "Reading reports..." : "Ask FinTrace";
  $("question").disabled = state.busy;
  document.querySelectorAll(".example, #history button").forEach(b => b.disabled = state.busy);
  $("clear-history").disabled = state.busy;
}
async function connect() {
  $("connection").className = "connection";
  $("connection").textContent = "Connecting";
  $("reconnect").hidden = true;
  try {
    const response = await fetch("/health", { signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error("Offline");
    const health = await response.json();
    if (health.status !== "ready") throw new Error("Not ready");
    state.connected = true;
    $("connection").className = "connection connected";
    $("connection").textContent = "Backend connected";
    const docs = await fetch("/documents");
    if (docs.ok) {
      const catalog = await docs.json();
      state.documents = Array.isArray(catalog.documents) ? catalog.documents : [];
      renderDocuments();
    }
  } catch {
    state.connected = false;
    $("connection").className = "connection disconnected";
    $("connection").textContent = "Backend unavailable";
    $("reconnect").hidden = false;
    announce("Backend unavailable. Start the local server, then reconnect.");
  }
  updateForm();
}
function renderDocuments() {
  $("document-list").replaceChildren();
  for (const doc of state.documents) {
    const row = el("div", "document-link");
    const href = documentLink({ document_id: doc.id, pdf_page: 1 }, state.documents);
    if (href) {
      const a = el("a", "", doc.title); a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      row.append(a);
    } else row.append(el("span", "small", doc.title));
    row.append(el("p", "", doc.available ? human(doc.role) + " report / year-end " + doc.period_end : "Source file unavailable or changed"));
    $("document-list").append(row);
  }
}
function clearEvidence(message = "Ask a question to see the supporting report pages.") {
  state.evidence = [];
  $("source-count").textContent = "0";
  const empty = el("div", "evidence-empty");
  empty.append(el("h3", "", "No source selected"), el("p", "", message));
  $("evidence-content").replaceChildren(empty);
}
function renderEvidence(key) {
  const list = state.evidence;
  $("source-count").textContent = list.length;
  if (!list.length) {
    clearEvidence("This response does not provide supporting source pages. A clarification or refusal is not a verified figure.");
    return;
  }
  const selected = list.find(e => e.key === key) || list[0];
  const tabs = el("div", "source-tabs");
  tabs.setAttribute("role", "group"); tabs.setAttribute("aria-label", "Choose source page");
  for (const entry of list) {
    const button = el("button", "source-tab", "S" + entry.number + " / p. " + entry.source.pdf_page);
    button.type = "button";
    button.setAttribute("aria-pressed", String(entry.key === selected.key));
    button.setAttribute("aria-label", "Source " + entry.number + ": " + entry.source.document_title + ", PDF page " + entry.source.pdf_page);
    button.addEventListener("click", () => renderEvidence(entry.key));
    tabs.append(button);
  }
  const detail = el("div", "source-detail");
  detail.append(el("h3", "", selected.source.document_title),
    el("p", "source-meta", "PDF page " + selected.source.pdf_page + " / report year " + selected.source.report_year));
  const href = documentLink(selected.source, state.documents);
  if (href) {
    const a = el("a", "pdf-link", "Open original PDF at page " + selected.source.pdf_page);
    a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; detail.append(a);
  } else detail.append(issue("The original PDF is unavailable or its version could not be confirmed."));
  detail.append(el("p", "quote-label", "Exact extracted evidence, including headers"));
  for (const quote of selected.quotes) {
    detail.append(el("blockquote", "source-quote", quote.text), el("p", "source-id", quote.id));
  }
  $("evidence-content").replaceChildren(tabs, detail);
}
function sourceButton(source) {
  const entry = state.evidence.find(e => e.key === sourceKey(source));
  if (!entry) return null;
  const button = el("button", "source-ref", "S" + entry.number + " / PDF p. " + source.pdf_page);
  button.type = "button";
  button.setAttribute("aria-label", "Show source " + entry.number + ", PDF page " + source.pdf_page);
  button.addEventListener("click", () => {
    renderEvidence(entry.key);
    if (window.innerWidth <= 720) $("evidence-panel").scrollIntoView({ block: "start", behavior: "instant" });
    const active = $("evidence-content").querySelector('[aria-pressed="true"]');
    active?.focus({ preventScroll: true });
  });
  return button;
}
function renderClaim(claim) {
  const cell = claim.cell || {}, shown = presentedClaim(claim);
  const row = el("div", "claim");
  const top = el("div", "claim-top");
  const period = el("span", "claim-period", cell.period_end || "Period not supplied");
  const figure = el("span", "claim-value", formatValue(shown.value));
  figure.append(el("span", "claim-unit", " " + shown.unit));
  top.append(period, figure); row.append(top);
  const basis = el("div", "claim-basis", [human(cell.period_kind), human(cell.basis), human(cell.scope)].filter(Boolean).join(" / "));
  const ref = sourceButton(cell.source); if (ref) basis.append(ref);
  row.append(basis);
  if (shown.magnitude) {
    row.append(el("p", "presentation-note", shown.note + " Original signed value: " + formatValue(shown.sourceValue) + " " + shown.unit + "."));
  }
  return row;
}
function renderCalculation(calc) {
  const block = el("section", "calc-block");
  block.append(el("h3", "", calc.operation === "profit_gap" ? "Cash / statutory profit gap" : "Calculation"));
  block.append(el("div", "equation", formatValue(calc.left) + " − " + formatValue(calc.right) + " = " + formatValue(calc.absolute_change) + " " + changeUnit(calc)));
  block.append(el("p", "", calc.note || "Calculated by the backend from the cited source cells."));
  if (calc.basis_points !== undefined) {
    block.append(el("p", "", formatValue(calc.basis_points) + " basis points. This is a percentage-point movement, not relative percent growth."));
  }
  if (calc.relative_change_percent !== undefined && calc.relative_change_percent !== null) {
    const relative = Number(calc.relative_change_percent);
    block.append(el("p", "", "Relative change: " + (Number.isFinite(relative) ? relative.toFixed(2) : String(calc.relative_change_percent)) + "% (rounded for display)."));
  }
  if (calc.presentations?.some(p => p.representation === "expense_magnitude")) {
    block.append(el("p", "", "Expense magnitudes used. The original signed source difference is " + formatValue(calc.source_signed_difference) + " " + calc.unit + "."));
  }
  const workings = el("details", "");
  workings.append(el("summary", "", "Inspect the operands"));
  (calc.source_cells || []).forEach((cell, index) => {
    const p = el("p", "", (index === 0 ? "Left: " : "Right: ") + cell.company + " " + (METRICS[cell.metric] || human(cell.metric)) + ", " + cell.period_end + ". Source value: " + formatValue(cell.value) + " " + cell.unit + "; " + human(cell.basis) + ", " + human(cell.scope) + ".");
    const ref = sourceButton(cell.source); if (ref) p.append(ref); workings.append(p);
  });
  block.append(workings);
  return block;
}
function renderResult(entry, focus = true) {
  state.current = entry;
  const result = entry.result, answer = result.answer, status = statusInfo(answer.status);
  state.evidence = collectEvidence(answer);
  $("examples").hidden = true; $("result").hidden = false;
  const head = el("div", "result-head");
  head.append(el("span", "status " + status.tone, status.label));
  if (Number.isFinite(result.seconds)) head.append(el("span", "elapsed", result.seconds.toFixed(1) + "s backend time"));
  const fragment = document.createDocumentFragment();
  fragment.append(head, el("h2", "answered-question", result.question || entry.question));
  if (answer.message) fragment.append(el("p", "result-message", answer.message));
  const calculations = [];
  for (const part of answer.parts || []) {
    const section = el("section", "part");
    section.append(el("h3", "part-title", [part.request?.company, METRICS[part.request?.metric] || human(part.request?.metric)].filter(Boolean).join(" / ")));
    for (const claim of part.claims || []) section.append(renderClaim(claim));
    for (const text of part.issues || []) section.append(issue(text));
    fragment.append(section);
    calculations.push(...(part.calculations || []));
  }
  for (const calc of calculations) fragment.append(renderCalculation(calc));
  if (answer.calculation_coverage?.required > 0) fragment.append(el("p", "coverage", answer.calculation_coverage.completed + " of " + answer.calculation_coverage.required + " requested calculations completed."));
  for (const section of answer.source_excerpts || []) {
    const block = el("section", "excerpt-section");
    const title = el("h3", "", section.heading || section.source?.document_title || "Report excerpt");
    const ref = sourceButton(section.source); if (ref) title.append(ref);
    block.append(title);
    for (const excerpt of section.excerpts || []) block.append(el("blockquote", "", excerpt.quote));
    fragment.append(block);
  }
  for (const text of answer.issues || []) fragment.append(issue(text));
  for (const text of answer.limitations || []) fragment.append(issue(text));
  if (answer.warning) fragment.append(el("p", "answer-warning", answer.warning));
  if (answer.status === "source_bound_answer") fragment.append(el("p", "answer-warning", "Source-backed does not mean independently verified. Check the period, basis and evidence before relying on the answer."));
  if (answer.status === "clarify") {
    const tools = el("div", "answer-tools");
    const refine = el("button", "quiet", "Refine this question");
    refine.addEventListener("click", () => { $("question").value = result.question || entry.question; updateForm(); $("question").focus(); });
    tools.append(refine); fragment.append(tools);
  }
  const actions = el("div", "result-actions");
  const copy = el("button", "quiet", "Copy answer");
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(result.display_text || $("result").innerText); copy.textContent = "Copied"; }
    catch { copy.textContent = "Select the answer text to copy"; }
  });
  const download = el("button", "quiet", "Download answer JSON");
  download.addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    const a = el("a"); a.href = url; a.download = "fintrace-answer.json"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  actions.append(copy, download); fragment.append(actions);
  $("result").replaceChildren(fragment);
  renderEvidence(); renderHistory();
  if (focus) $("result").focus({ preventScroll: false });
}
function renderHistory() {
  $("history").replaceChildren();
  $("history-empty").hidden = state.history.length > 0;
  $("clear-history").hidden = !state.history.length;
  for (const entry of [...state.history].reverse()) {
    const li = el("li"), button = el("button", "", entry.question.length > 76 ? entry.question.slice(0, 73) + "..." : entry.question);
    button.title = entry.question; button.type = "button"; button.disabled = state.busy;
    button.setAttribute("aria-current", String(state.current?.id === entry.id));
    button.addEventListener("click", () => { $("question").value = entry.question; updateForm(); renderResult(entry); });
    li.append(button); $("history").append(li);
  }
}
function loading() {
  $("examples").hidden = true; $("result").hidden = false;
  const box = el("div", "loading-box");
  const spinner = el("span", "spinner"); spinner.setAttribute("aria-hidden", "true");
  const content = el("div"); content.append(el("h2", "", "Reading the reports"), el("p", "", "The first question loads the local model and can take a couple of minutes. Later questions usually run faster."));
  const timer = el("p", "", "Waiting for the backend...");
  content.append(timer); box.append(spinner, content); $("result").replaceChildren(box);
  clearEvidence("Waiting for the backend's evidence. No source has been selected yet.");
  const start = Date.now();
  return setInterval(() => { timer.textContent = Math.floor((Date.now() - start) / 1000) + " seconds elapsed. No answer has been returned yet."; }, 1000);
}
async function ask(event) {
  event.preventDefault();
  if (state.busy || !state.connected) return;
  const question = $("question").value.trim();
  if (!question || question.length > 2000) {
    $("input-error").textContent = "Enter a question between 1 and 2,000 characters.";
    $("input-error").hidden = false; $("question").focus(); return;
  }
  $("input-error").hidden = true;
  state.busy = true; updateForm();
  $("result").setAttribute("aria-busy", "true");
  const ticker = loading();
  announce("Reading reports. The first question may take a couple of minutes.");
  try {
    const response = await fetch("/ask", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }), signal: AbortSignal.timeout(180000) });
    if (!response.ok) {
      let message = "The backend could not answer. Check that the local server is running, then try again.";
      try { const payload = await response.json(); if (typeof payload.error === "string") message = payload.error; } catch {}
      throw new Error(message);
    }
    const result = validateResult(await response.json());
    if (!result.question) result.question = question;
    const entry = { id: ++historySequence, question, result };
    state.history.push(entry); if (state.history.length > 8) state.history.shift();
    renderResult(entry);
    announce(statusInfo(result.answer.status).label + ". Review the answer and its sources.");
  } catch (error) {
    state.current = null; renderHistory();
    const box = el("div", "result-message error-box");
    box.setAttribute("role", "alert");
    box.append(el("h2", "answered-question", "No answer returned"));
    box.append(el("p", "", error.name === "TimeoutError" ? "The browser stopped waiting after three minutes. The backend may still be processing. Wait before retrying; no result has been assumed." : error.name === "TypeError" ? "Could not reach the local backend. Check that the FinTrace server is running, then try this question again." : error.message));
    const retry = el("button", "quiet", "Try this question again"); retry.addEventListener("click", () => $("question-form").requestSubmit());
    box.append(retry); $("result").replaceChildren(box);
    clearEvidence("No new source evidence was returned. Previous answers have not been reused.");
    announce("No answer returned. Check the message and retry when ready.");
  } finally {
    clearInterval(ticker); state.busy = false; $("result").setAttribute("aria-busy", "false"); updateForm();
  }
}
$("question-form").addEventListener("submit", ask);
$("question").addEventListener("input", () => { $("input-error").hidden = true; updateForm(); });
$("question").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $("question-form").requestSubmit(); } });
document.querySelectorAll("[data-example]").forEach(button => button.addEventListener("click", () => {
  $("question").value = EXAMPLES[button.dataset.example]; updateForm(); $("question").focus(); announce("Example added. Select Ask FinTrace.");
}));
for (const id of ["scope-toggle", "scope-toggle-mobile"]) $(id).addEventListener("click", () => {
  $("scope-details").hidden = !$("scope-details").hidden;
  for (const button of ["scope-toggle", "scope-toggle-mobile"]) $(button).setAttribute("aria-expanded", String(!$("scope-details").hidden));
});
$("reconnect").addEventListener("click", connect);
$("clear-history").addEventListener("click", () => {
  state.history = []; state.current = null; renderHistory();
  $("result").replaceChildren(); $("result").hidden = true; $("examples").hidden = false;
  $("question").value = ""; updateForm(); clearEvidence(); announce("Session history cleared.");
});
connect();
