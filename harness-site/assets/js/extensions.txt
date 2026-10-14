/*
  extensions.js: choosing an extension.

  A. Decision flow: Module 5's chart, drawn whole. Answer one question at
     a time; the path you took lights up and stays visible, and the result
     shows the mechanism's trade-offs. Back and Restart work at any point.
  B. Comparison grid: the mechanisms against five attributes. Select a
     mechanism to highlight its column, or an attribute for its row.
  C. Scenario practice: the module's seven design-exercise needs. Pick a
     mechanism; the feedback explains the recommendation in words.
*/

import { initPage, initSection } from "./common.js";
import { el, text, createScene, setSceneLabel } from "./scene.js";

/* A. Decision flow --------------------------------------------------------------- */

const Q = { w: 230, h: 56 };       // question box
const R = { h: 40, perChar: 8.4, pad: 34 }; // result pill

/** Split a label into at most two lines, at the space that balances them best. */
function twoLines(label) {
  if (label.length <= 24) return [label];
  let best = null;
  for (let i = 0; i < label.length; i += 1) {
    if (label[i] !== " ") continue;
    const longest = Math.max(i, label.length - i - 1);
    if (!best || longest < best.longest) best = { i, longest };
  }
  return best ? [label.slice(0, best.i), label.slice(best.i + 1)] : [label];
}

const resultWidth = (label) => label.length * R.perChar + R.pad;

function nodeBox(n) {
  return n.type === "question" ? { w: Q.w, h: Q.h } : { w: resultWidth(n.label), h: R.h };
}

/** Elbow connector from the bottom of one node to the top of another. */
function connector(from, to) {
  const a = { x: from.x, y: from.y + nodeBox(from).h / 2 };
  const b = { x: to.x, y: to.y - nodeBox(to).h / 2 };
  const midY = (a.y + b.y) / 2;
  return { d: `M ${a.x} ${a.y} V ${midY} H ${b.x} V ${b.y - 6}`, label: { x: (a.x + b.x) / 2, y: midY - 6 }, end: b };
}

function createFlow(content, onShowInGrid) {
  const flow = content.flow;
  const nodes = Object.fromEntries(flow.nodes.map((n) => [n.id, n]));
  const mech = Object.fromEntries(content.mechanisms.map((m) => [m.id, m]));
  const box = document.getElementById("flow-scene");
  const els = {
    stage: document.getElementById("flow-stage"),
    question: document.getElementById("flow-question"),
    answer: document.getElementById("flow-answer"),
    yes: document.getElementById("flow-yes"),
    no: document.getElementById("flow-no"),
    result: document.getElementById("flow-result"),
    path: document.getElementById("flow-path"),
    back: document.getElementById("flow-back"),
    restart: document.getElementById("flow-restart"),
  };

  // State: the answers given so far, then the team-sharing answer.
  let answers = [];        // [{ node, answer: "yes" | "no" }]
  let share = null;        // null, "yes", or "no"

  const current = () => {
    let id = flow.start;
    for (const a of answers) id = nodes[id][a.answer];
    return nodes[id];
  };

  function draw() {
    const svg = createScene(box, { width: 940, height: 640, label: "" });
    const taken = new Set();
    let id = flow.start;
    const visited = new Set([id]);
    for (const a of answers) {
      taken.add(`${id}:${a.answer}`);
      id = nodes[id][a.answer];
      visited.add(id);
    }
    const here = nodes[id];

    // Edges first, so nodes sit on top of them.
    const edges = el("g", {}, svg);
    for (const n of flow.nodes) {
      if (n.type !== "question") continue;
      for (const answer of ["yes", "no"]) {
        const c = connector(n, nodes[n[answer]]);
        const isTaken = taken.has(`${n.id}:${answer}`);
        el("path", { class: `flow-edge${isTaken ? " is-taken" : ""}`, d: c.d }, edges);
        el("path", { class: `flow-arrow${isTaken ? " is-taken" : ""}`, d: `M ${c.end.x - 5} ${c.end.y - 6} L ${c.end.x + 5} ${c.end.y - 6} L ${c.end.x} ${c.end.y} Z` }, edges);
        text(edges, c.label.x, c.label.y, answer === "yes" ? "Yes" : "No", { "text-anchor": "middle", class: `flow-edge-label${isTaken ? " is-taken" : ""}` });
      }
    }

    // The team-sharing step hangs off whichever result was reached.
    const [sx, sy] = flow.share_position;
    const [px, py] = flow.plugin_position;
    const shareNode = { x: sx, y: sy, type: "question", label: flow.share_question };
    if (here.type === "result") {
      const c = connector(here, shareNode);
      el("path", { class: "flow-edge is-taken", d: c.d }, edges);
    }
    const shareTaken = share === "yes";
    el("path", { class: `flow-edge${shareTaken ? " is-taken" : ""}`, d: `M ${sx + Q.w / 2} ${sy} H ${px - resultWidth(flow.share_yes.label) / 2 - 6}` }, edges);
    text(edges, (sx + Q.w / 2 + px - resultWidth(flow.share_yes.label) / 2) / 2, sy - 8, "Yes", { "text-anchor": "middle", class: `flow-edge-label${shareTaken ? " is-taken" : ""}` });

    // Nodes.
    const drawNode = (n, { isHere, isVisited, kind }) => {
      const { w, h } = n.type === "question" ? Q : { w: resultWidth(n.label), h: R.h };
      const g = el("g", { class: `flow-node ${kind}${isHere ? " is-here" : ""}${isVisited ? " is-visited" : ""}` }, svg);
      el("rect", { x: n.x - w / 2, y: n.y - h / 2, width: w, height: h, rx: n.type === "question" ? 10 : h / 2 }, g);
      const lines = n.type === "question" ? twoLines(n.label) : [n.label];
      lines.forEach((line, i) => {
        text(g, n.x, n.y + 5 + (i - (lines.length - 1) / 2) * 17, line, { "text-anchor": "middle" });
      });
    };
    for (const n of flow.nodes) {
      drawNode(n, { isHere: n.id === id && share === null, isVisited: visited.has(n.id), kind: n.type === "question" ? "is-question" : "is-result" });
    }
    drawNode(shareNode, { isHere: here.type === "result" && share === null, isVisited: here.type === "result", kind: "is-question is-share" });
    drawNode({ x: px, y: py, type: "result", label: flow.share_yes.label }, { isHere: shareTaken, isVisited: shareTaken, kind: "is-result" });

    const pathText = answers.map((a) => `${nodes[a.node].text} ${a.answer === "yes" ? "Yes" : "No"}.`).join(" ");
    setSceneLabel(svg, `Decision chart. ${pathText || "No answers yet."} ${here.type === "result" ? `Result: ${here.label}.` : `Now: ${here.text}`}`
      + (share ? ` Sharing with a team: ${share === "yes" ? "yes, package as a plugin" : "no"}.` : ""));
  }

  function renderPanel() {
    const here = current();
    // The path, in words, so it stays visible without the diagram.
    els.path.replaceChildren();
    for (const a of answers) {
      const li = document.createElement("li");
      li.textContent = `${nodes[a.node].text} `;
      const strong = document.createElement("strong");
      strong.textContent = a.answer === "yes" ? "Yes" : "No";
      li.append(strong);
      els.path.append(li);
    }
    els.back.disabled = answers.length === 0 && share === null;

    if (here.type === "question") {
      els.stage.textContent = `Question ${answers.length + 1}`;
      els.question.textContent = here.text;
      els.answer.hidden = false;
      els.result.hidden = true;
      return;
    }

    // A result: the mechanism, why, its trade-offs, then the sharing question.
    const m = mech[here.mechanism];
    els.result.hidden = false;
    els.result.replaceChildren();
    const h = document.createElement("h3");
    h.textContent = here.label;
    const why = document.createElement("p");
    why.textContent = here.why;
    const dl = document.createElement("dl");
    dl.className = "readouts tradeoffs";
    for (const [k, attr] of [["When it loads", "loads"], ["Who triggers it", "triggered"], ["Deterministic?", "deterministic"], ["Runs code?", "runs_code"]]) {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = m[attr];
      dl.append(dt, dd);
    }
    const link = document.createElement("button");
    link.type = "button";
    link.className = "button";
    link.textContent = `Compare ${m.label} in the grid`;
    link.addEventListener("click", () => onShowInGrid(m.id));
    els.result.append(h, why, dl, link);

    if (share === null) {
      els.stage.textContent = "Recommendation, then one more question";
      els.question.textContent = flow.share_question;
      els.answer.hidden = false;
    } else {
      els.stage.textContent = "Recommendation";
      els.answer.hidden = true;
      els.question.textContent = "";
      const p = document.createElement("p");
      p.className = "share-answer";
      if (share === "yes") {
        const strong = document.createElement("strong");
        strong.textContent = `${flow.share_yes.label}. `;
        p.append(strong, flow.share_yes.why);
      } else {
        p.textContent = flow.share_no;
      }
      els.result.append(p);
    }
  }

  function render() { draw(); renderPanel(); }

  function answer(value) {
    if (current().type === "question") answers.push({ node: current().id, answer: value });
    else if (share === null) share = value;
    render();
  }
  els.yes.addEventListener("click", () => answer("yes"));
  els.no.addEventListener("click", () => answer("no"));
  els.back.addEventListener("click", () => {
    if (share !== null) share = null;
    else answers.pop();
    render();
  });
  els.restart.addEventListener("click", () => { answers = []; share = null; render(); });
  render();
}

/* B. Comparison grid ------------------------------------------------------------------ */

function createGrid(content) {
  const table = document.getElementById("grid");
  const status = document.getElementById("grid-status");
  const state = { column: null, row: null };

  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const corner = document.createElement("td");
  headRow.append(corner);
  for (const m of content.mechanisms) {
    const th = document.createElement("th");
    th.scope = "col";
    th.dataset.col = m.id;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "grid-select";
    b.textContent = m.label;
    b.addEventListener("click", () => { state.column = state.column === m.id ? null : m.id; render(); });
    th.append(b);
    headRow.append(th);
  }
  head.append(headRow);

  const body = document.createElement("tbody");
  for (const a of content.attributes) {
    const tr = document.createElement("tr");
    tr.dataset.row = a.id;
    const th = document.createElement("th");
    th.scope = "row";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "grid-select";
    b.textContent = a.label;
    b.addEventListener("click", () => { state.row = state.row === a.id ? null : a.id; render(); });
    th.append(b);
    tr.append(th);
    for (const m of content.mechanisms) {
      const td = document.createElement("td");
      td.dataset.col = m.id;
      const flag = a.id === "deterministic" ? m.deterministic_flag : a.id === "runs_code" ? m.runs_flag : null;
      if (flag) {
        const chip = document.createElement("span");
        chip.className = `flag flag-${flag}`;
        chip.textContent = { yes: "Yes", no: "No", partly: "Partly" }[flag];
        td.append(chip, " ");
      }
      td.append(m[a.id]);
      tr.append(td);
    }
    body.append(tr);
  }
  table.replaceChildren(head, body);

  function render() {
    table.querySelectorAll("[data-col]").forEach((c) => c.classList.toggle("is-col", c.dataset.col === state.column));
    table.querySelectorAll("tr[data-row]").forEach((r) => r.classList.toggle("is-row", r.dataset.row === state.row));
    table.querySelectorAll("thead .grid-select").forEach((b) => b.setAttribute("aria-pressed", String(b.parentElement.dataset.col === state.column)));
    table.querySelectorAll("tbody .grid-select").forEach((b) => b.setAttribute("aria-pressed", String(b.closest("tr").dataset.row === state.row)));
    const parts = [];
    if (state.column) parts.push(`Highlighting the ${content.mechanisms.find((m) => m.id === state.column).label} column.`);
    if (state.row) parts.push(`Highlighting the "${content.attributes.find((a) => a.id === state.row).label}" row.`);
    status.textContent = parts.join(" ");
  }

  render();
  return {
    showColumn(id) {
      state.column = id;
      render();
      table.closest("section").scrollIntoView({ behavior: "smooth", block: "start" });
      table.querySelector(`thead th[data-col="${id}"] button`).focus({ preventScroll: true });
    },
  };
}

/* C. Scenario practice -------------------------------------------------------------------- */

function createScenarios(content) {
  const list = document.getElementById("scenarios");
  const score = document.getElementById("scenario-score");
  const picks = {};
  const choices = content.mechanisms;

  function renderScore() {
    const answered = Object.keys(picks).length;
    const matched = content.scenarios.filter((s) => picks[s.id] && s.answer.includes(picks[s.id])).length;
    score.textContent = answered
      ? `${matched} of ${answered} answered match the recommendation. ${content.scenarios.length - answered} to go.`
      : "";
  }

  content.scenarios.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = "panel scenario";
    const h = document.createElement("p");
    h.className = "scenario-text";
    h.textContent = `${i + 1}. ${s.text}`;
    const group = document.createElement("div");
    group.className = "choices";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", `Mechanism for need ${i + 1}`);
    const feedback = document.createElement("p");
    feedback.className = "feedback";
    feedback.setAttribute("aria-live", "polite");
    for (const m of choices) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chapter";
      b.textContent = m.short;
      b.addEventListener("click", () => {
        picks[s.id] = m.id;
        group.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        const right = s.answer.includes(m.id);
        feedback.className = `feedback ${right ? "is-right" : "is-wrong"}`;
        feedback.replaceChildren();
        const verdict = document.createElement("strong");
        verdict.textContent = right ? "Matches the recommendation. " : `Not quite: you chose ${m.label}. `;
        feedback.append(verdict, s.explanation);
        renderScore();
      });
      group.append(b);
    }
    li.append(h, group, feedback);
    list.append(li);
  });
}

/* Page ------------------------------------------------------------------------------------ */

async function main() {
  initPage();
  const content = await initSection("extensions");
  if (!content) return;
  document.getElementById("source-note").textContent = content.source_note;
  document.getElementById("takeaway").textContent = content.takeaway;
  const rules = document.getElementById("rules");
  for (const r of content.rules_of_thumb) {
    const li = document.createElement("li");
    li.textContent = r;
    rules.append(li);
  }
  const grid = createGrid(content);
  createFlow(content, (id) => grid.showColumn(id));
  createScenarios(content);
}

main();
