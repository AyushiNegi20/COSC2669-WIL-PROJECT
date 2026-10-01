// Scope is resolved by the API, not independently reinterpreted by the browser.
export function readScope() {
  return { company: document.getElementById("company-filter").value,
    year: document.getElementById("year-filter").value };
}
export function restoreScope(scope = {}) {
  document.getElementById("company-filter").value = scope.company || "all";
  document.getElementById("year-filter").value = scope.year || "all";
}
export function disableScope(busy) {
  for (const id of ["company-filter", "year-filter"]) document.getElementById(id).disabled = busy;
}
export function scopeDescription(result) {
  const scope = result.ui_scope;
  return scope ? ["Question scope: " + scope.summary, ...(scope.notes || [])] : [];
}
export function renderScope(result, fragment) {
  const lines = scopeDescription(result);
  if (!lines.length) return;
  const block = document.createElement("div"); block.className = "answer-scope";
  for (const line of lines) {
    const p = document.createElement("p"); p.textContent = line; block.append(p);
  }
  fragment.append(block);
}
