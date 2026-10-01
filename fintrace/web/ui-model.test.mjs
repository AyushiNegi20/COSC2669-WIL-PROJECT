import test from "node:test";
import assert from "node:assert/strict";
import { formatValue, statusInfo, presentedClaim, changeUnit, collectEvidence, documentLink, validateResult } from "./ui-model.mjs";

test("formats source strings without rounding or numeric precision loss", () => {
  assert.equal(formatValue("12345678901234567890.123400"), "12,345,678,901,234,567,890.123400");
  assert.equal(formatValue("-12218"), "-12,218");
  assert.equal(formatValue("11.70"), "11.70");
});
test("presentation does not overwrite original source signs", () => {
  const claim = { cell: { value: "-833", unit: "AUD million" }, presentation: { value: "833", representation: "expense_magnitude", note: "Source deduction" } };
  const shown = presentedClaim(claim);
  assert.equal(shown.value, "833"); assert.equal(shown.sourceValue, "-833");
  assert.equal(claim.cell.value, "-833"); assert.equal(shown.magnitude, true);
});
test("percentage differences are labelled percentage points", () => {
  assert.equal(changeUnit({ unit: "percent" }), "percentage points");
  assert.equal(changeUnit({ unit: "cents/share" }), "cents/share");
});
test("status labels do not call partial answers verified", () => {
  assert.equal(statusInfo("partial_answer").label, "Partial answer");
  assert.equal(statusInfo("evidence_answer").label, "Report excerpts");
  assert.equal(statusInfo("unexpected").label, "Review required");
  assert.equal(statusInfo("unable_to_verify").tone, "unavailable");
});
test("groups evidence by actual document/page and retains header quotes", () => {
  const s = { document_id: "cba25", pdf_page: 18 };
  const answer = { parts: [{ claims: [{ cell: { source: s }, evidence: [
    { source_id: "row1", quote: "Cash | 10,252", source: s },
    { source_id: "header", quote: "Full year | 30 Jun 25", source: s },
    { source_id: "header", quote: "Full year | 30 Jun 25", source: s },
  ] }], calculations: [] }], source_excerpts: [{ source: { ...s, pdf_page: 17 }, excerpts: [{ source_id: "p", quote: "Definition" }] }] };
  const entries = collectEvidence(answer);
  assert.equal(entries.length, 2); assert.equal(entries[0].quotes.length, 2);
  assert.equal(entries[1].number, 2);
});
test("source links use only the approved local catalog", () => {
  const s = { document_id: "cba25", pdf_page: 18, source_url: "javascript:alert(1)" };
  assert.equal(documentLink(s, [{ id: "cba25", available: true, path: "/reports/cba25.pdf" }]), "/reports/cba25.pdf#page=18");
  assert.equal(documentLink(s, [{ id: "cba25", available: true, path: "//evil.test/file.pdf" }]), null);
  assert.equal(documentLink(s, []), null);
  assert.equal(documentLink({ ...s, pdf_page: -1 }, [{ id: "cba25", available: true, path: "/reports/cba25.pdf" }]), null);
});
test("missing or changed documents never become clickable sources", () => {
  assert.equal(documentLink({ document_id: "nab25", pdf_page: 60 }, [{ id: "nab25", available: false, path: null }]), null);
});
test("invalid responses are rejected, guard-only responses allowed", () => {
  assert.throws(() => validateResult({}), /unreadable/);
  assert.throws(() => validateResult({ answer: { status: "partial_answer", parts: "not an array" } }), /unreadable/);
  assert.equal(validateResult({ answer: { status: "clarify", message: "Specify a bank" } }).answer.status, "clarify");
});
