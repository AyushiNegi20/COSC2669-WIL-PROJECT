export const EXAMPLES = {
  expense: "Calculate NAB FY2025 credit impairment charge growth from FY2024, using positive expense magnitudes and the FY2025 report.",
  profit: "For CBA FY2025 continuing operations only, calculate cash profit minus statutory profit.",
  find: "What was CBA FY2025 annual dividend per share?",
  explain: "Explain what CBA FY2025 means by cash profit and whether it is a cash-flow or cash-accounting measure.",
};
export const METRICS = {
  cash_profit: "Cash profit", statutory_npat: "Statutory profit after tax",
  operating_income: "Total operating income", operating_expenses: "Operating expenses",
  credit_impairment: "Credit impairment charge", nim: "Net interest margin",
  basic_cash_eps: "Basic cash EPS", dividend_per_share: "Dividend per share",
  total_assets: "Total Group assets", gross_loans: "Gross loans and acceptances",
  customer_deposits: "Customer deposits", cet1: "CET1 capital ratio", lcr: "Liquidity coverage ratio",
};
const STATUSES = {
  source_bound_answer: { label: "Source-backed figures", tone: "supported" },
  partial_answer: { label: "Partial answer", tone: "partial" },
  evidence_answer: { label: "Report excerpts", tone: "excerpt" },
  clarify: { label: "Needs clarification", tone: "clarify" },
  unable_to_verify: { label: "Not supported", tone: "unavailable" },
};
export function statusInfo(status) {
  return STATUSES[status] || { label: "Review required", tone: "partial" };
}
export function formatValue(value) {
  const raw = String(value ?? "");
  const match = /^([+-]?)(\d+)(\.\d+)?$/.exec(raw);
  if (!match) return raw || "Not supplied";
  return match[1] + match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (match[3] || "");
}
export function human(value) {
  const aliases = { continuing: "Continuing operations", including_discontinued: "Including discontinued operations",
    as_at: "As at", annual: "Full year ending", quarterly_average: "Quarterly average ending" };
  return aliases[value] || String(value ?? "").replaceAll("_", " ");
}
export function presentedClaim(claim) {
  const cell = claim.cell || {};
  return {
    value: claim.presentation?.value ?? cell.value,
    sourceValue: cell.value,
    unit: cell.unit || "",
    magnitude: claim.presentation?.representation === "expense_magnitude",
    note: claim.presentation?.note || "",
  };
}
export function changeUnit(calc) {
  return calc.unit === "percent" ? "percentage points" : calc.unit;
}
export function sourceKey(source) {
  return String(source?.document_id || "") + ":" + String(source?.pdf_page || "");
}
export function collectEvidence(answer) {
  const sources = new Map();
  function add(source, id, quote) {
    if (!source?.document_id || !Number.isInteger(source.pdf_page)) return;
    const key = sourceKey(source);
    if (!sources.has(key)) sources.set(key, { key, number: sources.size + 1, source, quotes: [] });
    const entry = sources.get(key);
    if (quote && !entry.quotes.some(q => q.id === id && q.text === quote)) entry.quotes.push({ id, text: quote });
  }
  for (const part of answer.parts || []) {
    for (const claim of part.claims || []) {
      for (const e of claim.evidence || []) add(e.source || claim.cell?.source, e.source_id, e.quote);
    }
    for (const calc of part.calculations || []) {
      for (const cell of calc.source_cells || []) add(cell.source, cell.source_id, cell.row_quote);
    }
  }
  for (const section of answer.source_excerpts || []) {
    for (const e of section.excerpts || []) add(section.source, e.source_id, e.quote);
  }
  return [...sources.values()];
}
export function documentLink(source, documents) {
  const doc = documents.find(d => d.id === source?.document_id);
  const page = source?.pdf_page;
  if (!doc?.available || !/^\/reports\/[a-z0-9_]+\.pdf$/.test(doc.path || "")) return null;
  if (!Number.isInteger(page) || page < 1 || page > 10000) return null;
  return doc.path + "#page=" + page;
}
export function validateResult(result) {
  if (!result || typeof result !== "object" || !result.answer || typeof result.answer !== "object"
      || typeof result.answer.status !== "string") throw new Error("The backend returned an unreadable response.");
  for (const key of ["parts", "issues", "source_excerpts", "limitations"]) {
    if (result.answer[key] !== undefined && !Array.isArray(result.answer[key])) throw new Error("The backend returned an unreadable response.");
  }
  return result;
}
