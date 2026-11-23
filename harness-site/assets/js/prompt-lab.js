/*
  prompt-lab.js: "Prompts across model generations" (PROMPT_LAB_SPEC section 14).

  Everything is drawn from two content files:
  - prompt-lab.json: the page's text;
  - prompt-lab-results.json: aggregates of one Prompt Lab results file,
    written by tools/import_prompt_lab.py.

  Seven blocks: prompt sensitivity, technique against information, harness
  quality and cost, where harness tokens go, cost per correct result, judge
  against checks, and the predictions table. A task filter redraws the
  charts that have per-task data.

  Conventions shared with the other sections: colors come from CSS classes,
  every scene has a text alternative, and nothing relies on color alone
  (generations differ by marker shape, harness prompts by letter, judge
  disagreements by shape).
*/

import { initPage, initSection, loadContent, showLoadError } from "./common.js";
import { el, text, createScene, setSceneLabel, setSceneInteractive, drawBlocks, legendSwatch } from "./scene.js";

const W = 1200;
const fmt = (n) => Math.round(n).toLocaleString("en-US");
const f2 = (n) => (n === null || n === undefined ? "-" : n.toFixed(2));
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const signed = (n) => {
  if (n === null) return "-";
  const r = Math.round(n * 100) / 100; // so a tiny negative never prints as -0.00
  return `${r < 0 ? "-" : "+"}${Math.abs(r).toFixed(2)}`;
};
const fill = (template, values) => template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));

/** Round up to 1, 2, 2.5, or 5 times a power of ten, for readable axes. */
function niceMax(value) {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) if (step * power >= value) return step * power;
  return 10 * power;
}

/* Shared state and data access ------------------------------------------------- */

const state = { task: null, tokensModel: null, tokensVariant: null, judgeKey: null };
let content;
let results;
let ladders; // family -> [model, ...] oldest first

const inTask = (cell) => state.task === null || cell.task === state.task;
const modelById = (id) => results.models.find((m) => m.id === id);
const variantLabel = (v) => content.variants[v] || v;

/** 0 = oldest in its family, 1 = in between, 2 = newest. Drives marker shape and color. */
function genStyle(model) {
  const ladder = ladders.get(model.family);
  const i = ladder.indexOf(model);
  return i === ladder.length - 1 ? 2 : i === 0 ? 0 : 1;
}

function oneShotScores(modelId, variant) {
  return results.one_shot.cells.filter((c) => c.model === modelId && c.variant === variant && inTask(c))
    .flatMap((c) => c.scores);
}

/** Harness cells for a model and prompt, combined across the selected tasks. */
function harnessAgg(modelId, variant) {
  const cells = results.harness.cells.filter((c) => c.model === modelId && c.variant === variant && inTask(c));
  if (!cells.length) return null;
  const runs = cells.reduce((a, c) => a + c.runs, 0);
  const weighted = (get) => {
    const usable = cells.filter((c) => get(c) !== null && get(c) !== undefined);
    if (usable.length !== cells.length) return null;
    return usable.reduce((a, c) => a + get(c) * c.runs, 0) / runs;
  };
  return {
    score: mean(cells.flatMap((c) => c.scores)),
    runs,
    hitLimit: cells.reduce((a, c) => a + c.hit_limit, 0),
    requests: weighted((c) => c.requests),
    failedCalls: weighted((c) => c.failed_calls),
    tokens: weighted((c) => c.tokens),
    chars: weighted((c) => c.chars),
    split: Object.fromEntries(["fixed", "conversation", "tool_results", "output", "reasoning"]
      .map((part) => [part, weighted((c) => c.split[part])])),
  };
}

/* Small drawing and DOM helpers --------------------------------------------------- */

function marker(parent, style, x, y, size, cls) {
  if (style === 1) return el("rect", { class: cls, x: x - size, y: y - size, width: size * 2, height: size * 2 }, parent);
  if (style === 2) {
    const s = size * 1.3;
    return el("path", { class: cls, d: `M${x} ${y - s} L${x + s} ${y} L${x} ${y + s} L${x - s} ${y} Z` }, parent);
  }
  return el("circle", { class: cls, cx: x, cy: y, r: size }, parent);
}

function scoreAxis(g, { x, y, w, h, label }) {
  for (const t of [0, 0.5, 1]) {
    const yy = y + h - t * h;
    el("line", { class: t === 0 ? "axis" : "gridline", x1: x, y1: yy, x2: x + w, y2: yy }, g);
    if (label) text(g, x - 8, yy + 4, t.toFixed(1), { "text-anchor": "end", class: "label-muted mono" });
  }
}

function htmlTable(headers, rows) {
  const table = document.createElement("table");
  table.className = "grid lab-table";
  const head = table.createTHead().insertRow();
  for (const h of headers) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = h;
    head.append(th);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    row.forEach((value, i) => {
      const cell = document.createElement(i === 0 ? "th" : "td");
      if (i === 0) cell.scope = "row";
      cell.textContent = value;
      tr.append(cell);
    });
  }
  return table;
}

function choiceButtons(container, options, selected, onPick) {
  container.replaceChildren();
  for (const [value, label] of options) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button";
    button.textContent = label;
    button.setAttribute("aria-pressed", String(value === selected));
    button.addEventListener("click", () => onPick(value));
    container.append(button);
  }
}

function legendItem(list, svg, label) {
  const li = document.createElement("li");
  li.append(svg, label);
  list.append(li);
}

function swatch(draw) {
  const svg = el("svg", { width: 16, height: 16, viewBox: "0 0 16 16", "aria-hidden": "true", focusable: "false" });
  draw(svg);
  return svg;
}

/* 1. Prompt sensitivity ------------------------------------------------------------- */

function renderSensitivity() {
  const variants = results.one_shot.variants;
  const families = [...ladders.keys()];
  const H = 400;
  const svg = createScene(document.getElementById("sensitivity-scene"), { width: W, height: H, label: "" });
  const area = { y: 46, h: 270 };
  const gap = 40;
  const panelW = (W - 70 - gap * (families.length - 1)) / families.length;
  const described = [];
  const tableRows = [];

  families.forEach((family, fi) => {
    const g = el("g", {}, svg);
    const x0 = 56 + fi * (panelW + gap);
    const models = ladders.get(family);
    text(g, x0, 24, family, { class: "label-strong" });
    scoreAxis(g, { x: x0, y: area.y, w: panelW, h: area.h, label: fi === 0 });
    const slot = panelW / variants.length;
    variants.forEach((v, vi) => {
      // Stagger the labels so long names do not collide.
      text(g, x0 + slot * (vi + 0.5), area.y + area.h + 22 + (vi % 2) * 18, variantLabel(v),
        { "text-anchor": "middle", class: "label-muted" });
    });
    models.forEach((model, mi) => {
      const style = genStyle(model);
      const offset = (mi - (models.length - 1) / 2) * Math.min(16, slot / (models.length + 1));
      const points = [];
      const means = [];
      variants.forEach((v, vi) => {
        const scores = oneShotScores(model.id, v);
        const cx = x0 + slot * (vi + 0.5) + offset;
        scores.forEach((s, i) => {
          const jitter = Math.max(-6, Math.min(6, (i - (scores.length - 1) / 2) * 2.2));
          el("circle", { class: `lab-dot lab-gen-${style}`, cx: cx + jitter, cy: area.y + area.h - s * area.h, r: 2.6 }, g);
        });
        const m = mean(scores);
        means.push(m);
        if (m !== null) points.push([cx, area.y + area.h - m * area.h]);
      });
      if (points.length > 1) {
        el("path", { class: `lab-line lab-gen-${style}`, d: points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ") }, g);
      }
      for (const [x, y] of points) marker(g, style, x, y, 5.5, `lab-mark lab-gen-${style}`);
      described.push(`${model.display}: ${variants.map((v, i) => `${variantLabel(v)} ${f2(means[i])}`).join(", ")}`);
      tableRows.push([model.display, ...means.map(f2)]);
    });
  });
  text(svg, 56, H - 8, "Check score, 0 to 1. Large markers are means; small dots are single runs.", { class: "label-muted" });
  setSceneLabel(svg, `Mean check score by prompt, per model. ${described.join(". ")}.`);

  const legend = document.getElementById("sensitivity-legend");
  legend.replaceChildren();
  for (const style of [...new Set(results.models.map(genStyle))].sort()) {
    legendItem(legend, swatch((s) => marker(s, style, 8, 8, 5, `lab-mark lab-gen-${style}`)), content.generations[style]);
  }
  for (const model of results.models) {
    const style = genStyle(model);
    legendItem(legend, swatch((s) => marker(s, style, 8, 8, 4, `lab-mark lab-gen-${style}`)), `${model.display} (${model.family})`);
  }
  document.getElementById("sensitivity-table").replaceChildren(htmlTable(["Model", ...variants.map(variantLabel)], tableRows));
}

/* 2. Technique against information ---------------------------------------------------- */

const GRID = [["terse", "technique"], ["informed", "full"]]; // rows: information; columns: technique

function renderGrid() {
  const models = results.models;
  const H = 310;
  const svg = createScene(document.getElementById("grid-scene"), { width: W, height: H, label: "" });
  const left = 150;
  const slot = Math.min(230, (W - left - 20) / models.length);
  const size = Math.min(78, (slot - 30) / 2);
  const top = 70;
  const axes = content.charts.grid.axes;
  axes.information.forEach((label, r) => {
    text(svg, left - 14, top + size * (r + 0.5) + 4, label, { "text-anchor": "end", class: "label-muted" });
  });
  const described = [];
  models.forEach((model, mi) => {
    const g = el("g", {}, svg);
    const x0 = left + mi * slot;
    text(g, x0 + size, 26, model.display, { "text-anchor": "middle", class: "label-strong" });
    axes.technique.forEach((label, c) => {
      text(g, x0 + size * (c + 0.5), top - 8, label, { "text-anchor": "middle", class: "label-muted" });
    });
    const value = (v) => mean(oneShotScores(model.id, v));
    GRID.forEach((row, r) => row.forEach((variant, c) => {
      const s = value(variant);
      const x = x0 + c * size;
      const y = top + r * size;
      el("rect", { class: "lab-cell-bg", x, y, width: size, height: size }, g);
      if (s !== null) el("rect", { class: "lab-cell", x, y, width: size, height: size, "fill-opacity": (0.08 + 0.84 * s).toFixed(3) }, g);
      text(g, x + size / 2, y + size / 2 + 5, f2(s), { "text-anchor": "middle", class: `mono lab-cell-text${s !== null && s > 0.55 ? " on-dark" : ""}` });
    }));
    const pair = (a, b) => {
      const xs = [value(a), value(b)].filter((v) => v !== null);
      return xs.length === 2 ? mean(xs) : null;
    };
    const diff = (hi, lo) => (hi === null || lo === null ? null : hi - lo);
    const technique = diff(pair("technique", "full"), pair("terse", "informed"));
    const information = diff(pair("informed", "full"), pair("terse", "technique"));
    text(g, x0 + size, top + size * 2 + 26, signed(technique), { "text-anchor": "middle", class: "mono lab-effect" });
    text(g, x0 + size, top + size * 2 + 46, signed(information), { "text-anchor": "middle", class: "mono lab-effect" });
    described.push(`${model.display}: ${GRID.flat().map((v) => `${variantLabel(v)} ${f2(value(v))}`).join(", ")}; `
      + `technique ${signed(technique)}, information ${signed(information)}`);
  });
  text(svg, left - 14, top - 8, axes.technique_title, { "text-anchor": "end", class: "label-muted" });
  // The effect rows are labelled once, at the left, so the numbers fit under narrow grids.
  axes.effects.forEach((label, i) => {
    text(svg, left - 14, top + size * 2 + 26 + i * 20, label, { "text-anchor": "end", class: "label-muted" });
  });
  setSceneLabel(svg, `Mean check score for four prompts per model, as a grid of technique against information. ${described.join(". ")}.`);
  document.getElementById("grid-readout").textContent = content.charts.grid.readout;
}

/* 3. Harness quality and cost ---------------------------------------------------------- */

function renderHarness() {
  const variants = results.harness.variants;
  const models = results.models.filter((m) => variants.some((v) => harnessAgg(m.id, v)));
  const H = 470;
  const svg = createScene(document.getElementById("harness-scene"), { width: W, height: H, label: "" });
  const x0 = 70;
  const top = { y: 44, h: 170 };
  const low = { y: 290, h: 120 };
  const slot = (W - x0 - 20) / Math.max(1, models.length);
  const barW = Math.min(34, (slot - 30) / variants.length);
  const data = models.map((model) => {
    const cells = Object.fromEntries(variants.map((v) => [v, harnessAgg(model.id, v)]));
    const full = cells["h-full"];
    const unit = Object.values(cells).every((c) => !c || c.tokens !== null) ? "tokens" : "chars";
    const cost = (v) => (cells[v] && full && full[unit] ? cells[v][unit] / full[unit] : null);
    return { model, cells, cost, unit };
  });
  const maxCost = niceMax(Math.max(1, ...data.flatMap((d) => variants.map((v) => d.cost(v) || 0))));

  scoreAxis(svg, { x: x0, y: top.y, w: W - x0 - 20, h: top.h, label: true });
  text(svg, x0, top.y - 16, "Check score, 0 to 1", { class: "label-muted" });
  for (const t of [0, 0.5, 1]) {
    const yy = low.y + low.h - t * low.h;
    el("line", { class: t === 0 ? "axis" : "gridline", x1: x0, y1: yy, x2: W - 20, y2: yy }, svg);
    text(svg, x0 - 8, yy + 4, `${(maxCost * t).toFixed(1)}x`, { "text-anchor": "end", class: "label-muted mono" });
  }
  text(svg, x0, low.y - 16, "Cost of a session, relative to the full prompt on the same model", { class: "label-muted" });

  const described = [];
  const tableRows = [];
  data.forEach(({ model, cells, cost, unit }, mi) => {
    const g = el("g", {}, svg);
    const gx = x0 + slot * mi + (slot - barW * variants.length) / 2;
    variants.forEach((v, vi) => {
      const c = cells[v];
      const x = gx + vi * barW;
      const code = content.harness_codes[v] || String(vi + 1);
      text(g, x + barW / 2 - 1, top.y + top.h + 18, code, { "text-anchor": "middle", class: "label-muted mono" });
      if (!c) return;
      const sh = (c.score ?? 0) * top.h;
      el("rect", { class: `lab-hbar lab-hbar-${vi}`, x: x + 2, y: top.y + top.h - Math.max(1.5, sh), width: barW - 5, height: Math.max(1.5, sh) }, g);
      if (c.hitLimit) {
        // Neighbouring labels alternate height so they never run into each other.
        text(g, x + barW / 2 - 1, top.y + top.h - Math.max(1.5, sh) - 6 - (vi % 2) * 13, `${c.hitLimit}/${c.runs}`, { "text-anchor": "middle", class: "lab-limit mono" });
      }
      const ratio = cost(v);
      if (ratio !== null) {
        const ch = (ratio / maxCost) * low.h;
        el("rect", { class: `lab-hbar lab-hbar-${vi}`, x: x + 2, y: low.y + low.h - ch, width: barW - 5, height: Math.max(1.5, ch) }, g);
      }
      tableRows.push([model.display, `${code}: ${variantLabel(v)}`, f2(c.score), c.requests === null ? "-" : c.requests.toFixed(1),
        c.failedCalls === null ? "-" : c.failedCalls.toFixed(1), `${c.hitLimit} of ${c.runs}`,
        c[unit] === null ? "not reported" : `${fmt(c[unit])} ${unit === "tokens" ? "tokens" : "characters"}`,
        ratio === null ? "-" : `${ratio.toFixed(1)}x`]);
    });
    text(g, x0 + slot * (mi + 0.5), low.y + low.h + 24, model.display, { "text-anchor": "middle", class: "label-strong" });
    described.push(`${model.display}: ${variants.map((v) => (cells[v]
      ? `${variantLabel(v)} score ${f2(cells[v].score)}${cost(v) !== null ? `, cost ${cost(v).toFixed(1)} times` : ""}${cells[v].hitLimit ? `, ${cells[v].hitLimit} of ${cells[v].runs} hit the limit` : ""}`
      : `${variantLabel(v)} not run`)).join("; ")}`);
  });
  if (data.some((d) => variants.some((v) => d.cells[v] && d.cells[v].hitLimit))) {
    text(svg, W - 20, top.y - 16, `n/n above a bar: sessions that ${content.charts.harness.limit}`, { "text-anchor": "end", class: "lab-limit" });
  }
  setSceneLabel(svg, `Harness sessions per model and prompt: check score, and cost relative to the full prompt. ${described.join(". ")}.`);

  const legend = document.getElementById("harness-legend");
  legend.replaceChildren();
  variants.forEach((v, vi) => {
    legendItem(legend, swatch((s) => el("rect", { class: `lab-hbar lab-hbar-${vi}`, x: 2, y: 2, width: 12, height: 12 }, s)),
      `${content.harness_codes[v] || vi + 1}: ${variantLabel(v)}`);
  });

  const readouts = document.getElementById("harness-readouts");
  readouts.replaceChildren();
  for (const d of data.filter(({ model }) => genStyle(model) === 2)) {
    const { cells, cost } = d;
    if (!cells["h-full"] || !cells["h-discoverable-gap"]) continue;
    const card = document.createElement("div");
    card.className = "panel readout-card";
    const h = document.createElement("h3");
    h.textContent = d.model.display;
    const p = document.createElement("p");
    p.textContent = fill(content.charts.harness.readout, {
      gap: f2(cells["h-discoverable-gap"].score), full: f2(cells["h-full"].score),
      cost: cost("h-discoverable-gap") === null ? "-" : cost("h-discoverable-gap").toFixed(1),
      private: cells["h-private-gap"] ? f2(cells["h-private-gap"].score) : "-",
    });
    card.append(h, p);
    readouts.append(card);
  }
  document.getElementById("harness-table").replaceChildren(
    htmlTable(["Model", "Prompt", "Score", "Requests", "Failed tool calls", "Hit limit", "Session size", "Cost vs full"], tableRows));
}

/* 4. Where harness tokens go ----------------------------------------------------------- */

const TOKEN_PARTS = [["fixed", "tools"], ["conversation", "user"], ["tool_results", "result"], ["output", "model"], ["reasoning", "summary"]];

function renderHarnessTokens() {
  const variants = results.harness.variants;
  const models = results.models.filter((m) => results.harness.cells.some((c) => c.model === m.id));
  if (!models.some((m) => m.id === state.tokensModel)) state.tokensModel = models.length ? models[models.length - 1].id : null;
  if (!variants.includes(state.tokensVariant)) state.tokensVariant = variants.includes("h-full") ? "h-full" : variants[0];
  choiceButtons(document.getElementById("tokens-model"), models.map((m) => [m.id, m.display]), state.tokensModel,
    (id) => { state.tokensModel = id; renderHarnessTokens(); });
  choiceButtons(document.getElementById("tokens-variant"), variants.map((v) => [v, variantLabel(v)]), state.tokensVariant,
    (v) => { state.tokensVariant = v; renderHarnessTokens(); });

  const box = document.getElementById("harness_tokens-scene");
  const legend = document.getElementById("harness_tokens-legend");
  const readout = document.getElementById("harness_tokens-readout");
  legend.replaceChildren();
  const agg = state.tokensModel ? harnessAgg(state.tokensModel, state.tokensVariant) : null;
  const parts = agg ? TOKEN_PARTS.map(([key, role]) => ({ key, role, tokens: agg.split[key] }))
    .filter((p) => typeof p.tokens === "number" && p.tokens > 0) : [];
  if (!parts.length) {
    createScene(box, { width: W, height: 60, label: content.charts.harness_tokens.none });
    readout.textContent = content.charts.harness_tokens.none;
    return;
  }
  const total = parts.reduce((a, p) => a + p.tokens, 0);
  const perBlock = Math.max(1, niceMax(total / 560));
  const segments = parts.map((p) => ({ role: p.role, blocks: Math.max(1, Math.round(p.tokens / perBlock)) }));
  const perRow = 80;
  const rows = Math.ceil(segments.reduce((a, s) => a + s.blocks, 0) / perRow);
  const svg = createScene(box, { width: W, height: 40 + rows * 12, label: "" });
  drawBlocks(svg, { x: (W - perRow * 12) / 2, y: 20, segments, perRow, svg });
  const labels = content.charts.harness_tokens.parts;
  for (const p of parts) {
    const li = document.createElement("li");
    const n = document.createElement("span");
    n.className = "mono";
    n.textContent = ` ${fmt(p.tokens)}`;
    li.append(legendSwatch(p.role), labels[p.key], n);
    legend.append(li);
  }
  const input = ["fixed", "conversation", "tool_results"].reduce((a, k) => a + (agg.split[k] || 0), 0);
  readout.textContent = fill(content.charts.harness_tokens.readout, {
    per_block: fmt(perBlock),
    fixed_share: input ? Math.round((100 * (agg.split.fixed || 0)) / input) : 0,
    requests: agg.requests === null ? "-" : agg.requests.toFixed(1),
    reasoning: typeof agg.split.reasoning === "number" ? fmt(agg.split.reasoning) : "not reported separately",
  });
  setSceneLabel(svg, `${modelById(state.tokensModel).display}, ${variantLabel(state.tokensVariant)}: `
    + `${parts.map((p) => `${labels[p.key]} ${fmt(p.tokens)} tokens`).join(", ")}. ${readout.textContent}`);
}

/* 5. Cost per correct result -------------------------------------------------------------- */

function renderPerCorrect() {
  const rows = results.per_correct.filter((r) => r.one_shot || r.harness);
  const modes = ["one_shot", "harness"];
  const rowH = 66;
  const svg = createScene(document.getElementById("per_correct-scene"), { width: W, height: 50 + rows.length * rowH, label: "" });
  const x0 = 420;
  const maxW = 440;
  const max = Math.max(1, ...rows.flatMap((r) => modes.map((m) => (r[m] && r[m].chars_per_correct) || 0)));
  const described = [];
  const tableRows = [];
  text(svg, x0, 22, "Characters sent and received per correct result (fewer is better)", { class: "label-muted" });
  rows.forEach((row, i) => {
    const g = el("g", {}, svg);
    const y = 40 + i * rowH;
    const model = modelById(row.model);
    text(g, 20, y + 32, model.display, { class: "label-strong" });
    modes.forEach((mode, mi) => {
      const d = row[mode];
      const by = y + 6 + mi * 26;
      text(g, x0 - 12, by + 15, content.charts.per_correct.modes[mode], { "text-anchor": "end", class: "label-muted" });
      if (!d) return;
      const value = d.chars_per_correct;
      const note = `${d.correct} of ${d.runs} correct`;
      if (value === null) {
        text(g, x0 + 4, by + 15, `${content.charts.per_correct.none} (${note})`, { class: "lab-limit" });
      } else {
        const w = Math.max(2, (value / max) * maxW);
        el("rect", { class: `lab-mode lab-mode-${mode}`, x: x0, y: by, width: w, height: 20 }, g);
        text(g, x0 + w + 10, by + 15, `${fmt(value)}  (${note})`, { class: "mono" });
      }
      described.push(`${model.display}, ${content.charts.per_correct.modes[mode]}: `
        + `${value === null ? content.charts.per_correct.none : `${fmt(value)} characters per correct result`}, ${note}`);
      tableRows.push([model.display, content.charts.per_correct.modes[mode], `${d.correct} of ${d.runs}`,
        value === null ? "-" : fmt(value), d.tokens_per_correct === null ? "-" : fmt(d.tokens_per_correct)]);
    });
  });
  setSceneLabel(svg, `Characters per correct result, one-shot against harness, per model. ${described.join(". ")}. ${content.charts.per_correct.scope_note}`);
  document.getElementById("per_correct-table").replaceChildren(
    htmlTable(["Model", "Mode", "Correct", "Characters per correct result", "Tokens per correct result (same family only)"], tableRows));
}

/* 6. Judge against checks ------------------------------------------------------------------- */

function renderJudge() {
  const chart = content.charts.judge;
  const points = results.judge.points.filter(inTask);
  const groups = new Map();
  for (const p of points) {
    const key = `${p.check.toFixed(2)}|${p.judge.toFixed(2)}|${p.disagree || "agree"}`;
    if (!groups.has(key)) groups.set(key, { key, check: p.check, judge: p.judge, kind: p.disagree, runs: [] });
    groups.get(key).runs.push(p);
  }
  if (!groups.has(state.judgeKey)) state.judgeKey = null;

  const H = 440;
  const svg = createScene(document.getElementById("judge-scene"), { width: W, height: H, label: "" });
  setSceneInteractive(svg);
  const area = { x: 90, y: 30, w: W - 130, h: 340 };
  const pad = 28; // keeps bubbles at 0 and 1 clear of the axis numbers
  const px = (v) => area.x + pad + v * (area.w - 2 * pad);
  const py = (v) => area.y + area.h - pad - v * (area.h - 2 * pad);
  const { high, low } = results.judge.rule;
  el("rect", { class: "lab-region", x: px(0), y: py(1), width: px(low) - px(0), height: py(high) - py(1) }, svg);
  text(svg, px(0) + 10, py(1) + 20, chart.kinds.lenient, { class: "lab-limit" });
  el("rect", { class: "lab-region", x: px(high), y: py(low), width: px(1) - px(high), height: py(0) - py(low) }, svg);
  text(svg, px(1) - 10, py(0) - 12, chart.kinds.harsh, { "text-anchor": "end", class: "lab-limit" });
  for (const t of [0, 0.5, 1]) {
    el("line", { class: "gridline", x1: area.x, y1: py(t), x2: area.x + area.w, y2: py(t) }, svg);
    text(svg, area.x - 10, py(t) + 4, t.toFixed(1), { "text-anchor": "end", class: "label-muted mono" });
    text(svg, px(t), area.y + area.h + 20, t.toFixed(1), { "text-anchor": "middle", class: "label-muted mono" });
  }
  el("line", { class: "axis", x1: area.x, y1: area.y + area.h, x2: area.x + area.w, y2: area.y + area.h }, svg);
  el("line", { class: "lab-diagonal", x1: px(0), y1: py(0), x2: px(1), y2: py(1) }, svg);
  text(svg, area.x + area.w / 2, H - 14, "Check score", { "text-anchor": "middle", class: "label-muted" });
  text(svg, 22, area.y + area.h / 2, "Judge score", { class: "label-muted", transform: `rotate(-90 22 ${area.y + area.h / 2})`, "text-anchor": "middle" });

  const evidence = document.getElementById("judge-evidence");
  const counts = { lenient: 0, harsh: 0 };
  for (const p of points) if (p.disagree) counts[p.disagree] += 1;

  function showEvidence() {
    evidence.replaceChildren();
    const summary = document.createElement("p");
    summary.textContent = fill(chart.summary, { judged: points.length, lenient: counts.lenient, harsh: counts.harsh });
    evidence.append(summary);
    const validation = results.judge.validation;
    if (validation && typeof validation.agreement_with_humans === "number") {
      const p = document.createElement("p");
      p.textContent = fill(chart.validation, { sample: validation.sample, humans: validation.agreement_with_humans.toFixed(2) });
      evidence.append(p);
    }
    const group = groups.get(state.judgeKey);
    if (!group) {
      const p = document.createElement("p");
      p.className = "note";
      p.textContent = counts.lenient + counts.harsh ? chart.prompt : chart.kinds.agree;
      evidence.append(p);
      return;
    }
    const h = document.createElement("h3");
    h.textContent = `${chart.kinds[group.kind]}: checks ${f2(group.check)}, judge ${f2(group.judge)}, ${group.runs.length} run${group.runs.length === 1 ? "" : "s"}`;
    evidence.append(h);
    for (const run of group.runs.slice(0, 3)) {
      const p = document.createElement("p");
      p.className = "mono";
      p.textContent = `${modelById(run.model)?.display || run.model} · ${run.task} · ${variantLabel(run.variant)}`;
      evidence.append(p, htmlTable(["Criterion", "Judge's score (1 to 5)", "Quote from the answer", "Judge's reason"],
        (run.evidence || []).map((e) => [e.criterion, String(e.score), e.quote, e.reason])));
    }
    if (group.runs.length > 3) {
      const more = document.createElement("p");
      more.className = "note";
      more.textContent = `And ${group.runs.length - 3} more with the same scores.`;
      evidence.append(more);
    }
  }

  const ordered = [...groups.values()].sort((a, b) => (a.kind ? 1 : 0) - (b.kind ? 1 : 0));
  for (const group of ordered) {
    const n = group.runs.length;
    const r = Math.min(22, 6 + 3 * Math.sqrt(n));
    const cx = px(group.check);
    const cy = py(group.judge);
    const g = el("g", { class: `lab-bubble${group.kind ? " lab-disagree" : " lab-agree"}` }, svg);
    if (group.kind) {
      el("path", { d: `M${cx} ${cy - r * 1.25} L${cx + r * 1.25} ${cy} L${cx} ${cy + r * 1.25} L${cx - r * 1.25} ${cy} Z` }, g);
      g.setAttribute("role", "button");
      g.setAttribute("tabindex", "0");
      g.setAttribute("aria-pressed", String(group.key === state.judgeKey));
      g.setAttribute("aria-label", `${chart.kinds[group.kind]}. ${n} run${n === 1 ? "" : "s"}: checks ${f2(group.check)}, judge ${f2(group.judge)}. Show the evidence.`);
      const pick = () => {
        state.judgeKey = group.key;
        for (const node of svg.querySelectorAll(".lab-disagree")) node.setAttribute("aria-pressed", String(node === g));
        showEvidence();
      };
      g.addEventListener("click", pick);
      g.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          pick();
        }
      });
    } else {
      el("circle", { cx, cy, r }, g);
    }
    if (n > 1) text(g, cx, cy + 4, String(n), { "text-anchor": "middle", class: "mono lab-bubble-count" });
  }
  svg.setAttribute("aria-label", `Judge score against check score for ${points.length} judged runs. `
    + fill(chart.summary, { judged: points.length, lenient: counts.lenient, harsh: counts.harsh }));
  showEvidence();

  const legend = document.getElementById("judge-legend");
  legend.replaceChildren();
  legendItem(legend, swatch((s) => el("circle", { class: "lab-agree-swatch", cx: 8, cy: 8, r: 6 }, s)), "Judge and checks agree (number = runs)");
  legendItem(legend, swatch((s) => el("path", { class: "lab-disagree-swatch", d: "M8 1 L15 8 L8 15 L1 8 Z" }, s)), "Disagreement: select to read the evidence");
}

/* 7. Predictions ------------------------------------------------------------------------------- */

function renderPredictions() {
  const table = htmlTable(["", "Prediction", "Outcome", "How it was read", "Comparisons"],
    results.predictions.map((p) => [p.id, content.predictions_text[p.id] || "", content.outcomes[p.outcome] || p.outcome,
      p.rule || "", String(p.n ?? "")]));
  for (const row of table.tBodies[0].rows) row.cells[2].className = "lab-outcome";
  document.getElementById("predictions-table").replaceChildren(table);
}

/* Page ---------------------------------------------------------------------------------------------- */

const PER_TASK = [renderSensitivity, renderGrid, renderHarness, renderHarnessTokens, renderJudge];

function renderTaskFilter() {
  document.getElementById("task-label").textContent = content.tasks_label;
  choiceButtons(document.getElementById("task-choices"),
    [[null, content.all_tasks], ...results.tasks.map((t) => [t, t])], state.task,
    (task) => {
      state.task = task;
      state.judgeKey = null;
      renderTaskFilter();
      for (const render of PER_TASK) render();
    });
}

async function main() {
  initPage();
  content = await initSection("prompt-lab");
  if (!content) return;
  try {
    results = await loadContent("prompt-lab-results");
  } catch (error) {
    showLoadError(error);
    return;
  }
  ladders = new Map();
  for (const model of [...results.models].sort((a, b) => a.generation - b.generation)) {
    if (!ladders.has(model.family)) ladders.set(model.family, []);
    ladders.get(model.family).push(model);
  }

  const scope = fill(content.scope, { date: results.created, tasks: results.tasks.length });
  for (const node of document.querySelectorAll("[data-scope]")) node.textContent = scope;
  document.getElementById("per_correct-title").closest("section").querySelector("[data-scope]").textContent
    = `${scope} · ${content.charts.per_correct.scope_note}`;
  if (results.synthetic) {
    const banner = document.getElementById("synthetic-banner");
    banner.textContent = content.synthetic;
    banner.hidden = false;
  }
  for (const [key, chart] of Object.entries(content.charts)) {
    document.getElementById(`${key}-title`).textContent = chart.title;
    document.getElementById(`${key}-intro`).textContent = chart.intro;
  }

  renderTaskFilter();
  for (const render of PER_TASK) render();
  renderPerCorrect();
  renderPredictions();
  document.getElementById("source-note").textContent = content.source_note;
}

main();
