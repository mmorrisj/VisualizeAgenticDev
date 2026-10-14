/*
  context.js: the context window section.

  Three parts, drawn with the same two visuals:
  - the window bar: one request, laid out left to right against the
    context limit, with the 80% compaction threshold marked
  - the request chart: every request's size, stacked by what fills it,
    so compaction shows as a sudden drop

  1. Replay: Module 3 Lab B, measured by running the course's mini-harness.
  2. Lab A: what an instructions file costs across a session (measured).
  3. Simulator: a simplified model of the same harness (illustrative).
*/

import { initPage, initSection } from "./common.js";
import { el, text, createScene, setSceneLabel, renderLegend, animate } from "./scene.js";

const fmt = (n) => Math.round(n).toLocaleString("en-US");
const pct = (part, whole) => `${Math.round((100 * part) / Math.max(whole, 1))}%`;

/* Shared visuals ----------------------------------------------------------------- */

// Geometry of the combined scene: window bar on top, request chart below.
const G = {
  width: 900,
  bar: { x: 20, y: 46, w: 860, h: 58 },
  chart: { x: 64, y: 168, w: 806, h: 190 },
  height: 400,
};

/**
 * Segments of one request, in the order they sit in the request.
 * Each: { role, tokens, label, removed?, truncated? }
 */
function segmentsOf(request) {
  const p = request.parts;
  const segs = [
    { role: "system", tokens: p.system, label: "System prompt" },
    { role: "tools", tokens: p.tools, label: "Tool definitions" },
  ];
  if (p.instructions) segs.push({ role: "instructions", tokens: p.instructions, label: "Instructions file" });
  segs.push({ role: "model", tokens: p.conversation, label: "Conversation" });
  request.results.forEach((r, i) => segs.push({
    role: r.removed ? "summary" : "result",
    tokens: r.tokens,
    label: r.removed ? `${r.label} (removed)` : r.label + (r.truncated ? " (truncated)" : ""),
    removed: r.removed,
    index: i,
  }));
  return segs;
}

const total = (request) => request.parts.system + request.parts.tools + request.parts.instructions
  + request.parts.conversation + request.results.reduce((a, r) => a + r.tokens, 0);

/** Draw one request as a bar against the window. Returns result positions. */
function drawWindowBar(svg, request, limit, threshold) {
  const B = G.bar;
  const scale = B.w / limit;
  const g = el("g", { class: "window" }, svg);
  el("rect", { class: "window-bg", x: B.x, y: B.y, width: B.w, height: B.h, rx: 6 }, g);
  el("rect", { class: "window-frame", x: B.x, y: B.y, width: B.w, height: B.h, rx: 6 }, g);

  const positions = {};
  let x = B.x;
  for (const s of segmentsOf(request)) {
    const w = Math.max(1, s.tokens * scale);
    const attrs = { class: `block role-${s.role}`, x: x + 0.5, y: B.y + 6, width: Math.max(0.5, w - 1), height: B.h - 12, rx: 2 };
    if (s.removed) {
      attrs.fill = `url(#${svg.dataset.hatch})`;
      attrs.class += " summary-tile";
    }
    const rect = el("rect", attrs, g);
    const tip = el("title", {}, rect);
    tip.textContent = `${s.label}: ${fmt(s.tokens)} tokens`;
    if (s.index !== undefined) positions[s.index] = { x, w };
    x += w;
  }

  // Threshold and limit, with labels above the bar.
  const tx = B.x + B.w * threshold;
  el("line", { class: "threshold-line", x1: tx, y1: B.y - 8, x2: tx, y2: B.y + B.h + 8 }, g);
  text(g, tx, B.y - 14, `Compaction at ${Math.round(threshold * 100)}%`, { "text-anchor": "middle", class: "threshold-label" });
  el("line", { class: "limit-line", x1: B.x + B.w, y1: B.y - 8, x2: B.x + B.w, y2: B.y + B.h + 8 }, g);
  text(g, B.x + B.w, B.y - 14, `Limit ${fmt(limit)}`, { "text-anchor": "end", class: "limit-label" });
  text(g, B.x, B.y - 14, `Request ${request.n}: ${fmt(total(request))} tokens (${pct(total(request), limit)} of the window)`, { class: "label-strong" });
  return positions;
}

/**
 * Every request's size as a stacked bar: fixed overhead, conversation, and
 * tool results (removed ones hatched). Bars are buttons when `onSelect`.
 */
function drawRequestChart(svg, requests, limit, threshold, { selected, upTo = requests.length, onSelect } = {}) {
  const C = G.chart;
  const g = el("g", { class: "request-chart" }, svg);
  const y = (tokens) => C.y + C.h - (tokens / limit) * C.h;
  const slot = C.w / Math.max(requests.length, 1);
  const barW = Math.min(36, slot * 0.7);

  // Axes: y in tokens from 0 to the limit; x is the request number.
  el("line", { class: "axis", x1: C.x, y1: C.y + C.h, x2: C.x + C.w, y2: C.y + C.h }, g);
  for (const t of [0, 0.5, 1]) {
    const yy = y(limit * t);
    el("line", { class: "gridline", x1: C.x, y1: yy, x2: C.x + C.w, y2: yy }, g);
    text(g, C.x - 8, yy + 4, fmt(limit * t), { "text-anchor": "end", class: "label-muted mono" });
  }
  el("line", { class: "threshold-line", x1: C.x, y1: y(limit * threshold), x2: C.x + C.w, y2: y(limit * threshold) }, g);
  text(g, C.x + C.w, y(limit * threshold) - 6, "80%", { "text-anchor": "end", class: "threshold-label" });
  text(g, C.x, C.y - 12, "Size of each request", { class: "label-muted" });
  text(g, C.x + C.w / 2, C.y + C.h + 34, "Request", { "text-anchor": "middle", class: "label-muted" });

  const labelEvery = requests.length > 20 ? 5 : 1;
  requests.forEach((req, i) => {
    const cx = C.x + slot * i + slot / 2;
    if ((i + 1) % labelEvery === 0 || i === 0) {
      text(g, cx, C.y + C.h + 16, String(req.n), { "text-anchor": "middle", class: "label-muted mono" });
    }
    if (i >= upTo) return;
    const kept = req.results.filter((r) => !r.removed).reduce((a, r) => a + r.tokens, 0);
    const removed = req.results.filter((r) => r.removed).reduce((a, r) => a + r.tokens, 0);
    const bar = el("g", {
      class: `chart-bar${i === selected ? " is-selected" : ""}`,
      role: onSelect ? "button" : null,
      tabindex: onSelect ? "-1" : null,
      "aria-label": `Request ${req.n}: ${fmt(total(req))} tokens${req.compacted ? ", after compaction" : ""}`,
    }, g);
    let base = 0;
    const layers = [["system", req.parts.system], ["tools", req.parts.tools], ["instructions", req.parts.instructions],
      ["model", req.parts.conversation], ["summary", removed], ["result", kept]];
    for (const [role, tokens] of layers) {
      if (tokens <= 0) continue;
      const attrs = { class: `block role-${role}`, x: cx - barW / 2, y: y(base + tokens), width: barW, height: (tokens / limit) * C.h };
      if (role === "summary") attrs.fill = `url(#${svg.dataset.hatch})`;
      el("rect", attrs, bar);
      base += tokens;
    }
    // A wider transparent hit area makes thin bars easy to click.
    el("rect", { class: "hit", x: cx - slot / 2, y: C.y, width: slot, height: C.h }, bar);
    const tip = el("title", {}, bar);
    tip.textContent = `Request ${req.n}: ${fmt(total(req))} tokens`;
    if (req.compacted) {
      el("path", { class: "compaction-mark", d: `M ${cx - 5} ${y(base) - 12} L ${cx + 5} ${y(base) - 12} L ${cx} ${y(base) - 5} Z` }, bar);
    }
    if (onSelect) bar.addEventListener("click", () => onSelect(i));
  });
}

/* 1. Replay ------------------------------------------------------------------------- */

function createReplay(replay) {
  const box = document.getElementById("replay-scene");
  const els = {
    status: document.getElementById("replay-status"),
    call: document.getElementById("replay-call"),
    caption: document.getElementById("replay-caption"),
    size: document.getElementById("replay-size"),
    share: document.getElementById("replay-share"),
    compactions: document.getElementById("replay-compactions"),
    totalInput: document.getElementById("replay-total"),
    prev: document.getElementById("replay-prev"),
    next: document.getElementById("replay-next"),
    restart: document.getElementById("replay-restart"),
  };
  const reqs = replay.requests;
  let index = 0;

  function render(animateFrom = null) {
    const req = reqs[index];
    const svg = createScene(box, { width: G.width, height: G.height, label: "" });
    const positions = drawWindowBar(svg, req, replay.limit, replay.threshold);
    drawRequestChart(svg, reqs, replay.limit, replay.threshold, { selected: index, upTo: index + 1 });

    // Compaction: the file contents that were just removed crumble away.
    if (animateFrom !== null && req.compacted) {
      const prev = reqs[animateFrom];
      const prevPositions = drawWindowBarPositions(prev, replay.limit);
      req.results.forEach((r, i) => {
        if (!r.removed || !prev.results[i] || prev.results[i].removed) return;
        const p = prevPositions[i];
        const ghost = el("rect", {
          class: "block role-result crumble", x: p.x + 0.5, y: G.bar.y + 6, width: Math.max(0.5, p.w - 1), height: G.bar.h - 12, rx: 2, "aria-hidden": "true",
        }, svg);
        animate(ghost, [
          { transform: "translate(0px, 0px)", opacity: 0.95 },
          { transform: `translate(0px, ${36 + (i % 3) * 10}px)`, opacity: 0 },
        ], { duration: 900, delay: i * 60 }).then(() => ghost.remove());
      });
    }

    const sent = reqs.slice(0, index + 1);
    const compactions = sent.filter((r) => r.compacted).length;
    els.status.textContent = `Request ${req.n} of ${reqs.length}`;
    els.call.textContent = req.call ? `Then the model asks for: ${req.call}` : "Then the model answers, and the session ends.";
    els.caption.textContent = req.caption;
    els.size.textContent = `${fmt(req.reported)} tokens`;
    els.share.textContent = pct(req.reported, replay.limit);
    els.compactions.textContent = req.compacted
      ? `${compactions} (this one: ${fmt(req.compacted.before)} to ${fmt(req.compacted.after)})`
      : String(compactions);
    els.totalInput.textContent = `${fmt(sent.reduce((a, r) => a + r.reported, 0))} tokens`;
    els.prev.disabled = index === 0;
    els.next.disabled = index === reqs.length - 1;

    const removed = req.results.filter((r) => r.removed).length;
    setSceneLabel(svg, `Request ${req.n} of ${reqs.length}: ${fmt(req.reported)} tokens, ${pct(req.reported, replay.limit)} of a ${fmt(replay.limit)}-token window. `
      + `${req.results.length} tool results, ${removed} removed by compaction. Requests so far: ${sent.map((r) => fmt(r.reported)).join(", ")}.`);
  }

  // Positions of a request's results in the bar, without drawing it.
  function drawWindowBarPositions(request, limit) {
    const scale = G.bar.w / limit;
    let x = G.bar.x;
    const positions = {};
    for (const s of segmentsOf(request)) {
      const w = Math.max(1, s.tokens * scale);
      if (s.index !== undefined) positions[s.index] = { x, w };
      x += w;
    }
    return positions;
  }

  const go = (i, animated = false) => {
    const from = index;
    index = Math.max(0, Math.min(reqs.length - 1, i));
    render(animated && index === from + 1 ? from : null);
  };
  els.prev.addEventListener("click", () => go(index - 1));
  els.next.addEventListener("click", () => go(index + 1, true));
  els.restart.addEventListener("click", () => go(0));
  box.closest("section").addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === "ArrowRight" && !els.next.disabled) { event.preventDefault(); go(index + 1, true); }
    if (event.key === "ArrowLeft" && !els.prev.disabled) { event.preventDefault(); go(index - 1); }
  });
  render();
}

/* 2. Lab A -------------------------------------------------------------------------- */

function drawLabA(lab) {
  const runs = lab.runs;
  const max = Math.max(...runs.map((r) => r.session_total));
  const W = 900, rowH = 64, top = 28, left = 190, right = 120;
  const svg = createScene(document.getElementById("laba-scene"), {
    width: W, height: top + rowH * runs.length + 34,
    label: "Total input over a five-request session. " + runs.map((r) =>
      `${r.label}: ${fmt(r.session_total)} tokens, of which the instructions file is ${fmt(r.instructions_tokens * r.requests)}.`).join(" "),
  });
  const scale = (W - left - right) / max;
  text(svg, left, 16, "Input tokens across the whole session (5 requests)", { class: "label-muted" });
  runs.forEach((r, i) => {
    const y = top + i * rowH + 10;
    const instr = r.instructions_tokens * r.requests;
    text(svg, left - 12, y + 18, r.label, { "text-anchor": "end", class: "label-strong" });
    text(svg, left - 12, y + 36, r.lines ? `${r.lines} lines, ${fmt(r.instructions_tokens)} tokens` : "nothing loaded", { "text-anchor": "end", class: "label-muted" });
    el("rect", { class: "block role-system", x: left, y, width: (r.session_total - instr) * scale, height: 30, rx: 3 }, svg);
    if (instr) el("rect", { class: "block role-instructions", x: left + (r.session_total - instr) * scale, y, width: instr * scale, height: 30, rx: 3 }, svg);
    text(svg, left + r.session_total * scale + 10, y + 20, `${fmt(r.session_total)}`, { class: "mono label-strong" });
    if (instr) {
      text(svg, left + r.session_total * scale + 10, y + 38, `${pct(instr, r.session_total)} instructions`, { class: "label-muted" });
    }
  });
  renderLegend(document.getElementById("laba-legend"), ["system", "instructions"]);
  const legendItems = document.querySelectorAll("#laba-legend li");
  legendItems[0].lastChild.textContent = "Everything else";
  legendItems[1].lastChild.textContent = "Instructions file, sent on every request";
}

/* 3. Simulator ------------------------------------------------------------------------ */

/*
  The simulator's model, a simplified version of the course harness.

  Fixed overhead (sent on every request, never compacted):
    fixed = system_tokens + tools * tokens_per_tool + instructions

  The conversation starts as your message (user_message_tokens). After each
  request except the last, the model asks for a tool and gets a result:
    conversation += model_message_tokens
    results.push(result * result_pattern[k mod 5])
  The pattern varies result sizes (files differ) and averages 1.0, so the
  "average tool result" control means what it says.

  Each request's size is fixed + conversation + every result.

  Before each request, if size >= 80% of the limit, compaction runs (the
  harness's rule): every result except the newest keep_recent_results is
  replaced with a stub of stub_tokens. Only results are removed; the model's
  own messages stay.

  If a request is still over the limit after compaction, the newest results
  are truncated until it fits. If fixed overhead plus your message alone
  exceed the limit, the session cannot start. So no request ever exceeds
  the limit.
*/
export function simulate(model, v) {
  const fixed = model.system_tokens + v.tools * model.tokens_per_tool + v.instructions;
  const parts = { system: model.system_tokens, tools: v.tools * model.tokens_per_tool, instructions: v.instructions };
  if (fixed + model.user_message_tokens > v.limit) {
    return { state: "overhead", fixed, requests: [], compactions: 0 };
  }
  let conversation = model.user_message_tokens;
  let results = [];
  const requests = [];
  let compactions = 0;
  let state = "ok";

  for (let k = 1; k <= v.steps; k += 1) {
    const size = () => fixed + conversation + results.reduce((a, r) => a + r.tokens, 0);
    let compacted = null;
    if (size() >= model.threshold * v.limit) {
      const before = size();
      const cutoff = results.length - model.keep_recent_results;
      results = results.map((r, i) => (i < cutoff && !r.removed ? { ...r, tokens: model.stub_tokens, removed: true } : r));
      compacted = { before, after: size() };
      compactions += 1;
    }
    let over = size() - v.limit;
    for (let i = results.length - 1; over > 0 && i >= 0; i -= 1) {
      const r = results[i];
      if (r.removed) continue;
      const cut = Math.min(over, r.tokens - model.stub_tokens);
      results[i] = { ...r, tokens: r.tokens - cut, truncated: true };
      over -= cut;
    }
    if (over > 0) { state = "full"; break; }

    requests.push({
      n: k,
      parts: { ...parts, conversation },
      results: results.map((r) => ({ ...r })),
      compacted,
    });
    if (k < v.steps) {
      conversation += model.model_message_tokens;
      results.push({ label: `Tool result ${k}`, tokens: Math.round(v.result * model.result_pattern[(k - 1) % model.result_pattern.length]) });
    }
  }
  return { state, fixed, requests, compactions };
}

function createSimulator(model) {
  model = { ...model, threshold: 0.8 };
  const values = { ...model.defaults };
  const box = document.getElementById("sim-scene");
  const panel = {
    summary: document.getElementById("sim-summary"),
    overhead: document.getElementById("sim-overhead"),
    requests: document.getElementById("sim-requests"),
    compactions: document.getElementById("sim-compactions"),
    peak: document.getElementById("sim-peak"),
    total: document.getElementById("sim-total"),
  };
  let selected = null;

  // Sliders: each with a live numeric readout.
  const controls = {};
  for (const key of ["instructions", "tools", "result", "steps"]) {
    const input = document.getElementById(`sim-${key}`);
    const output = document.getElementById(`sim-${key}-out`);
    const [min, max, step] = model.ranges[key];
    Object.assign(input, { min, max, step, value: values[key] });
    input.addEventListener("input", () => { values[key] = Number(input.value); selected = null; update(); });
    controls[key] = { input, output };
  }
  const limitBox = document.getElementById("sim-limit");
  for (const limit of model.limits) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "button";
    b.textContent = fmt(limit);
    b.dataset.limit = limit;
    b.addEventListener("click", () => { values.limit = limit; selected = null; update(); });
    limitBox.append(b);
  }
  const presetBox = document.getElementById("sim-presets");
  for (const preset of model.presets) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "button";
    b.textContent = preset.label;
    b.dataset.preset = preset.id;
    b.addEventListener("click", () => { Object.assign(values, preset.values); selected = null; update(); });
    presetBox.append(b);
  }

  function update() {
    for (const [key, c] of Object.entries(controls)) {
      c.input.value = values[key];
      const v = values[key];
      c.output.textContent = key === "instructions" ? `${fmt(v)} tokens (short AGENTS.md: 193, bloated: 2,618)`
        : key === "tools" ? `${v} (${fmt(v * model.tokens_per_tool)} tokens)`
        : key === "result" ? `${fmt(v)} tokens`
        : `${v} requests`;
    }
    limitBox.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.limit) === values.limit)));
    presetBox.querySelectorAll("button").forEach((b) => {
      const p = model.presets.find((x) => x.id === b.dataset.preset);
      b.setAttribute("aria-pressed", String(Object.entries(p.values).every(([k, v]) => values[k] === v)));
    });

    const sim = simulate(model, values);
    const svg = createScene(box, { width: G.width, height: G.height, label: "" });

    if (sim.state === "overhead") {
      text(svg, G.width / 2, 120, "Overhead exceeds the context window", { "text-anchor": "middle", class: "limit-label overhead-warning" });
      text(svg, G.width / 2, 150, `The system prompt, tool definitions, and instructions file alone are ${fmt(sim.fixed)} tokens; the window holds ${fmt(values.limit)}.`, { "text-anchor": "middle", class: "label-muted" });
      setSceneLabel(svg, `Overhead exceeds the context window: fixed overhead is ${fmt(sim.fixed)} tokens and the window is ${fmt(values.limit)}. No request can be sent.`);
      panel.summary.textContent = "The session cannot start: the fixed overhead alone is larger than the window.";
      panel.overhead.textContent = "";
      for (const k of ["requests", "compactions", "peak", "total"]) panel[k].textContent = "none";
      return;
    }

    const reqs = sim.requests;
    if (selected === null || selected >= reqs.length) selected = reqs.length - 1;
    drawWindowBar(svg, reqs[selected], values.limit, model.threshold);
    drawRequestChart(svg, reqs, values.limit, model.threshold, {
      selected, onSelect: (i) => { selected = i; update(); },
    });

    const sizes = reqs.map(total);
    const totalInput = sizes.reduce((a, b) => a + b, 0);
    const overheadTotal = sim.fixed * reqs.length;
    panel.requests.textContent = String(reqs.length);
    panel.compactions.textContent = String(sim.compactions);
    panel.peak.textContent = `${fmt(Math.max(...sizes))} tokens`;
    panel.total.textContent = `${fmt(totalInput)} tokens`;
    panel.overhead.textContent = `Fixed overhead is ${fmt(sim.fixed)} tokens per request: the system prompt, ${values.tools} tool definitions, and the instructions file. `
      + `It was sent ${reqs.length} times, ${fmt(overheadTotal)} tokens in total: ${pct(overheadTotal, totalInput)} of the session's input.`;
    panel.summary.textContent = sim.state === "full"
      ? `The session stopped after request ${reqs.length}: even after compaction, the conversation no longer fits.`
      : sim.compactions
        ? `Compaction ran ${sim.compactions} time${sim.compactions === 1 ? "" : "s"}. Each time, older tool results were reduced to stubs, and their exact contents were gone for the rest of the session.`
        : "The session fit without compaction.";
    setSceneLabel(svg, `Simulated session: ${reqs.length} requests in a ${fmt(values.limit)}-token window, ${sim.compactions} compactions, peak ${fmt(Math.max(...sizes))} tokens, ${fmt(totalInput)} tokens of input in total. Showing request ${selected + 1}: ${fmt(sizes[selected])} tokens.`);
  }

  // Keyboard alternative to clicking chart bars: Left and Right pick a request.
  box.closest("section").addEventListener("keydown", (event) => {
    if (event.target.tagName === "INPUT" || event.altKey || event.ctrlKey || event.metaKey) return;
    const sim = simulate(model, values);
    if (!sim.requests.length) return;
    if (event.key === "ArrowLeft" && selected > 0) { event.preventDefault(); selected -= 1; update(); }
    if (event.key === "ArrowRight" && selected < sim.requests.length - 1) { event.preventDefault(); selected += 1; update(); }
  });

  update();
}

/* Page ---------------------------------------------------------------------------------- */

async function main() {
  initPage();
  const content = await initSection("context");
  if (!content) return;

  for (const [id, part] of [["replay", content.replay], ["laba", content.lab_a], ["sim", content.simulator]]) {
    document.getElementById(`${id}-title`).textContent = part.title;
    document.getElementById(`${id}-intro`).textContent = part.intro;
  }
  document.getElementById("source-note").textContent = content.source_note;
  const legendRoles = ["system", "tools", "instructions", "model", "result", "summary"];
  document.querySelectorAll(".context-legend").forEach((list) => {
    renderLegend(list, legendRoles);
    list.querySelectorAll("li")[3].lastChild.textContent = "Conversation";
    list.querySelectorAll("li")[5].lastChild.textContent = "Removed by compaction";
  });

  createReplay(content.replay);
  drawLabA(content.lab_a);
  createSimulator(content.simulator);
}

if (document.getElementById("replay-scene")) main();
