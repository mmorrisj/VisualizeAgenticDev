/*
  prompt-lab.js: "Prompts across model generations" (PROMPT_LAB_SPEC section 14).

  Everything is drawn from two content files:
  - prompt-lab.json: the page's text;
  - prompt-lab-results.json: aggregates of one Prompt Lab results file,
    written by tools/import_prompt_lab.py.

  Built so far: the study label on every block, the synthetic-sample banner,
  and the predictions table. A chart block stays hidden until its renderer
  is registered in CHARTS, so the page never shows an empty frame.
*/

import { initPage, initSection, loadContent, showLoadError } from "./common.js";

/** Chart renderers by block key: (content, results) => void. Added as each chart is built. */
const CHARTS = {};

const CHART_KEYS = ["sensitivity", "grid", "harness", "harness_tokens", "per_correct", "judge"];

function cell(tag, value, attrs = {}) {
  const node = document.createElement(tag);
  node.textContent = value;
  for (const [key, v] of Object.entries(attrs)) node.setAttribute(key, v);
  return node;
}

function renderPredictions(content, results) {
  const table = document.createElement("table");
  table.className = "grid lab-table";
  const head = table.createTHead().insertRow();
  for (const label of ["", "Prediction", "Outcome", "How it was read", "Comparisons"]) {
    head.append(cell("th", label, { scope: "col" }));
  }
  const body = table.createTBody();
  for (const p of results.predictions) {
    const row = body.insertRow();
    row.append(cell("th", p.id, { scope: "row" }));
    row.append(cell("td", content.predictions_text[p.id] || ""));
    const outcome = cell("td", content.outcomes[p.outcome] || p.outcome);
    outcome.className = `lab-outcome lab-outcome-${String(p.outcome).replace(/\s+/g, "-")}`;
    row.append(outcome);
    row.append(cell("td", p.rule || ""));
    row.append(cell("td", String(p.n ?? "")));
  }
  document.getElementById("predictions-table").replaceChildren(table);
}

async function main() {
  initPage();
  const content = await initSection("prompt-lab");
  if (!content) return;
  let results;
  try {
    results = await loadContent("prompt-lab-results");
  } catch (error) {
    showLoadError(error);
    return;
  }

  const scope = content.scope.replace("{date}", results.created).replace("{tasks}", results.tasks.length);
  for (const node of document.querySelectorAll("[data-scope]")) node.textContent = scope;

  if (results.synthetic) {
    const banner = document.getElementById("synthetic-banner");
    banner.textContent = content.synthetic;
    banner.hidden = false;
  }

  for (const key of [...CHART_KEYS, "predictions"]) {
    document.getElementById(`${key}-title`).textContent = content.charts[key].title;
    document.getElementById(`${key}-intro`).textContent = content.charts[key].intro;
  }
  for (const key of CHART_KEYS) {
    const section = document.getElementById(`${key}-title`).closest("section");
    if (CHARTS[key]) CHARTS[key](content, results);
    else section.hidden = true;
  }
  document.querySelector(".lab-filter").hidden = !CHART_KEYS.some((key) => CHARTS[key]);

  renderPredictions(content, results);
  document.getElementById("source-note").textContent = content.source_note;
}

main();
