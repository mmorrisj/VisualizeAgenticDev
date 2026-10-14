/*
  loop.js: the agent loop section.

  Two parts share one scene:
  - a guided narrative (scroll steps from loop.json "steps")
  - a sandbox stepping through every event in loop.json "session"

  The session is turned into a list of snapshots up front (buildSession).
  Each snapshot is a complete, immutable description of one step, so
  rendering step N never depends on how you got there. That is what makes
  Back restore the previous state exactly.
*/

import { initPage, initSection } from "./common.js";
import {
  ROLES, BLOCK, el, text, createScene, drawModel, drawArrow, drawBlocks,
  legendSwatch, animate,
} from "./scene.js";
import { createScrolly } from "./scrolly.js";

const fmt = (n) => n.toLocaleString("en-US");
const sum = (items) => items.reduce((total, item) => total + item.tokens, 0);

/* Session model -------------------------------------------------------------- */

/**
 * Turn loop.json into snapshots.
 *
 * The rules, which are the concept the section teaches:
 * - The conversation starts as the fixed overhead (system prompt, tools,
 *   CLAUDE.md). Every event's item is appended to it.
 * - On "decide" and "answer" steps the harness sends a request. The request
 *   is the whole conversation so far, before the model's reply is added.
 * - A "stale" marker flags an earlier item as outdated. It stays in the
 *   conversation and keeps being sent; only its appearance changes.
 *
 * Items are copied when marked stale, so earlier snapshots keep their view.
 */
export function buildSession(content) {
  let conversation = content.fixed.map((item) => ({ ...item }));
  const requests = [];
  const snapshots = [];
  let current = null;

  content.session.forEach((event, index) => {
    const before = conversation.length;
    let sentCount = 0;

    if (event.stage === "decide" || event.stage === "answer") {
      const items = conversation.slice();
      requests.push(sum(items));
      current = { number: requests.length, items, total: sum(items), sent: true };
      sentCount = items.length;
    }

    if (event.stale) {
      conversation = conversation.map((item) =>
        item.id === event.stale ? { ...item, stale: true } : item
      );
    }
    if (event.item) conversation = [...conversation, { ...event.item }];

    // Before the first send, "the request" is the one being built.
    const shown = current || { number: 1, items: conversation.slice(), total: sum(conversation), sent: false };

    snapshots.push({
      index,
      stage: event.stage,
      explain: event.explain,
      conversation,
      current: shown,
      requests: requests.slice(),
      totalInput: requests.reduce((a, b) => a + b, 0),
      newFrom: before,
      sentCount,
    });
  });

  const allRequests = snapshots[snapshots.length - 1].requests;
  return {
    snapshots,
    maxRequest: Math.max(...allRequests),
    firstRequest: allRequests[0],
    lastRequest: allRequests[allRequests.length - 1],
    totalInput: allRequests.reduce((a, b) => a + b, 0),
    requestCount: allRequests.length,
  };
}

/* Scene ------------------------------------------------------------------------- */

const STAGE_TEXT = {
  ask: "You ask",
  decide: "Model decides",
  run: "Harness runs the tool",
  return: "Result returns",
  answer: "Model answers you",
};

// Which nodes and arrows light up at each stage.
const STAGE_ACTIVE = {
  ask: { nodes: ["you"], arrows: ["youModel"] },
  decide: { nodes: ["model"], arrows: ["modelHarness"] },
  run: { nodes: ["harness"], arrows: ["modelHarness"] },
  return: { nodes: ["result"], arrows: ["harnessResult", "resultModel"] },
  answer: { nodes: ["model", "you"], arrows: ["modelYou"] },
};

/*
  Two layouts, like the world diagram: "wide" puts the loop left and the
  request on the right; "tall" stacks them for phones.
*/
const LAYOUTS = {
  wide: {
    width: 780, height: 300,
    you: { x: 60, y: 70 },
    model: { x: 250, y: 70, w: 130, h: 72 },
    harness: { x: 250, y: 236, w: 150 },
    result: { x: 80, y: 236, w: 130 },
    train: { x: 380, y: 34, perRow: 32 },
    history: { x: 380, y: 150, labelW: 76, barMax: 230 },
  },
  tall: {
    width: 400, height: 520,
    you: { x: 60, y: 60 },
    model: { x: 280, y: 60, w: 130, h: 72 },
    harness: { x: 280, y: 220, w: 150 },
    result: { x: 85, y: 220, w: 140 },
    train: { x: 14, y: 300, perRow: 31 },
    history: { x: 14, y: 400, labelW: 76, barMax: 220 },
  },
};

function blocksFor(tokens, perBlock) {
  return Math.max(1, Math.round(tokens / perBlock));
}

/** A pill-shaped stage node; `kind` picks the outline color. */
function drawStageNode(parent, { x, y, w, label, kind }) {
  const g = el("g", { class: `component stage-node ${kind}-node` }, parent);
  el("rect", { class: "component-pill", x: x - w / 2, y: y - 17, width: w, height: 34, rx: 17 }, g);
  text(g, x, y + 4.5, label, { "text-anchor": "middle", "font-size": 13 });
  return g;
}

function describe(snap, session) {
  const parts = [`${STAGE_TEXT[snap.stage]}.`];
  const r = snap.current;
  parts.push(r.sent ? `Request ${r.number} sent: ${fmt(r.total)} tokens.` : `Request 1 being built: ${fmt(r.total)} tokens.`);
  if (snap.requests.length) parts.push(`Requests so far: ${snap.requests.map(fmt).join(", ")}.`);
  const stale = snap.conversation.filter((i) => i.stale);
  if (stale.length) parts.push(`${stale.length} outdated item still in the conversation.`);
  parts.push(`${session.requestCount} requests in this session.`);
  return parts.join(" ");
}

/**
 * Draw one snapshot. `animateFrom` is the previous index when moving
 * forward by one step; otherwise the state is drawn with no motion.
 */
function renderScene(container, snap, session, perBlock, layoutName, animateFrom) {
  const L = LAYOUTS[layoutName];
  const svg = createScene(container, { width: L.width, height: L.height, label: describe(snap, session) });
  const active = STAGE_ACTIVE[snap.stage];

  // Loop diagram ---------------------------------------------------------
  const M = L.model;
  const arrows = {
    youModel: { x1: L.you.x + 28, y1: L.you.y - 8, x2: M.x - M.w / 2 - 2, y2: M.y - 8 },
    modelYou: { x1: M.x - M.w / 2 - 2, y1: M.y + 12, x2: L.you.x + 28, y2: L.you.y + 12, dashed: true },
    modelHarness: { x1: M.x, y1: M.y + M.h / 2 + 2, x2: L.harness.x, y2: L.harness.y - 19 },
    harnessResult: { x1: L.harness.x - L.harness.w / 2 - 2, y1: L.harness.y, x2: L.result.x + L.result.w / 2 + 2, y2: L.result.y },
    resultModel: { x1: L.result.x + 20, y1: L.result.y - 19, x2: M.x - M.w / 2 + 6, y2: M.y + M.h / 2 + 2 },
  };
  for (const [name, a] of Object.entries(arrows)) {
    drawArrow(svg, { ...a, active: active.arrows.includes(name) });
  }
  const mid = (a) => ({ x: (a.x1 + a.x2) / 2, y: (a.y1 + a.y2) / 2 });
  const rm = mid(arrows.resultModel);
  text(svg, rm.x - 8, rm.y + 4, "next request", { "text-anchor": "end", class: "label-muted" });
  const ym = mid(arrows.youModel);
  text(svg, ym.x, ym.y - 22, "request", { "text-anchor": "middle", class: "label-muted" });

  const you = el("g", { class: "actor" }, svg);
  el("circle", { class: "actor-shape", cx: L.you.x, cy: L.you.y, r: 26 }, you);
  text(you, L.you.x, L.you.y + 5, "You", { "text-anchor": "middle", class: "label-strong" });

  const model = drawModel(svg, { cx: M.x, cy: M.y, w: M.w, h: M.h, sublabel: "stateless" });
  const harness = drawStageNode(svg, { ...L.harness, label: "Harness runs tool", kind: "harness" });
  const result = drawStageNode(svg, { ...L.result, label: "Tool result", kind: "result" });

  const nodes = { you, model, harness, result };
  for (const name of active.nodes) nodes[name].classList.add("is-active");

  // Request train: the whole conversation, in order ---------------------------
  const T = L.train;
  const r = snap.current;
  const heading = r.sent ? `Request ${r.number} sent` : "Request 1 being built";
  text(svg, T.x, T.y - 12, heading, { class: "label-strong" });
  text(svg, T.x + T.perRow * (BLOCK.size + BLOCK.gap) - BLOCK.gap, T.y - 12, `${fmt(r.total)} tokens`, {
    "text-anchor": "end", class: "mono label-strong",
  });

  const segments = snap.conversation.map((item) => ({
    role: item.role,
    blocks: blocksFor(item.tokens, perBlock),
    className: item.stale ? "is-stale" : "",
  }));
  const train = drawBlocks(svg, { x: T.x, y: T.y, segments, perRow: T.perRow, svg });

  // Request history: one bar per request sent, on a fixed scale ---------------
  const H = L.history;
  text(svg, H.x, H.y, "Requests sent so far", { class: "label-muted" });
  snap.requests.forEach((total, i) => {
    const y = H.y + 12 + i * 22;
    const w = Math.max(2, (total / session.maxRequest) * H.barMax);
    const latest = r.sent && i === snap.requests.length - 1;
    text(svg, H.x, y + 11, `Request ${i + 1}`, { class: "label-muted" });
    el("rect", { class: `history-bar${latest ? " is-latest" : ""}`, x: H.x + H.labelW, y, width: w, height: 14, rx: 3 }, svg);
    text(svg, H.x + H.labelW + w + 6, y + 11, fmt(total), { class: "mono label-muted" });
  });

  // Motion: only when stepping forward by one --------------------------------
  if (animateFrom === snap.index - 1) {
    // New blocks fade in.
    const firstNew = snap.conversation.slice(0, snap.newFrom)
      .reduce((n, item) => n + blocksFor(item.tokens, perBlock), 0);
    [...train.group.children].slice(firstNew).forEach((node, i) => {
      node.style.opacity = "0";
      animate(node, [{ opacity: 0 }, { opacity: 1 }], { duration: 260, delay: 500 + Math.min(i * 20, 400) });
    });

    // The signature moment: a copy of the sent request flies into the model.
    if (snap.sentCount) {
      const sentBlocks = snap.conversation.slice(0, snap.sentCount)
        .reduce((n, item) => n + blocksFor(item.tokens, perBlock), 0);
      const ghost = el("g", { "aria-hidden": "true" }, svg);
      const copy = train.group.cloneNode(true);
      [...copy.children].slice(sentBlocks).forEach((node) => node.remove());
      [...copy.children].forEach((node) => { node.style.opacity = ""; });
      ghost.append(copy);
      ghost.style.transformBox = "fill-box";
      ghost.style.transformOrigin = "center";
      const rows = Math.ceil(sentBlocks / T.perRow);
      const cx = T.x + (Math.min(sentBlocks, T.perRow) * (BLOCK.size + BLOCK.gap)) / 2;
      const cy = T.y + (rows * (BLOCK.size + BLOCK.gap)) / 2;
      animate(ghost, [
        { transform: "translate(0px, 0px) scale(1)", opacity: 0.9 },
        { transform: `translate(${M.x - cx}px, ${M.y - cy}px) scale(0.15)`, opacity: 0 },
      ], { duration: 900 }).then(() => ghost.remove());
    }
  }
}

/**
 * Mount a scene that picks its layout from the container width and
 * redraws (without motion) when that changes.
 */
function mountLoopScene(container, session, perBlock) {
  let layout = null;
  let index = 0;
  const pick = () => (container.clientWidth < 560 ? "tall" : "wide");

  function show(next, { animateFrom = null } = {}) {
    index = next;
    layout = pick();
    renderScene(container, session.snapshots[index], session, perBlock, layout, animateFrom);
  }

  if ("ResizeObserver" in window) {
    new ResizeObserver(() => { if (pick() !== layout) show(index); }).observe(container);
  }
  return { show, get index() { return index; } };
}

/* Legend -------------------------------------------------------------------------- */

/** Legend for the roles this session actually uses, in request order. */
function renderLegend(list, roles, hasStale) {
  list.replaceChildren();
  for (const role of roles) {
    const li = document.createElement("li");
    li.append(legendSwatch(role), ROLES[role].label);
    list.append(li);
  }
  if (!hasStale) return;
  const li = document.createElement("li");
  const swatch = legendSwatch("result");
  swatch.querySelector("rect").classList.add("is-stale");
  li.append(swatch, "Outdated, still sent");
  list.append(li);
}

/* Sandbox panel ---------------------------------------------------------------------- */

function renderPanel(snap, session, els) {
  els.stage.textContent = STAGE_TEXT[snap.stage];
  els.explain.textContent = snap.explain;

  const r = snap.current;
  els.requestLabel.textContent = r.sent ? `Request ${r.number} (last sent)` : "Request 1 (being built)";
  els.requestSize.textContent = `${fmt(r.total)} tokens`;
  els.conversation.textContent = `${fmt(sum(snap.conversation))} tokens`;
  els.totalInput.textContent = `${fmt(snap.totalInput)} tokens over ${snap.requests.length} request${snap.requests.length === 1 ? "" : "s"}`;

  // "What does the model see?" lists exactly the items in the request above,
  // so its total always equals the request size shown.
  els.seenTitle.textContent = r.sent
    ? `Request ${r.number}, as the model read it`
    : "Request 1, as it will be sent";
  els.seenList.replaceChildren();
  for (const item of r.items) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "seen-label";
    name.append(legendSwatch(item.role), item.label);
    if (item.stale) {
      const tag = document.createElement("span");
      tag.className = "badge";
      tag.textContent = "outdated";
      name.append(" ", tag);
    }
    const size = document.createElement("span");
    size.className = "mono";
    size.textContent = fmt(item.tokens);
    li.append(name, size);
    els.seenList.append(li);
  }
  els.seenTotal.textContent = fmt(sum(r.items));

  els.status.textContent = `Step ${snap.index + 1} of ${session.snapshots.length}`;
  els.prev.disabled = snap.index === 0;
  els.next.disabled = snap.index === session.snapshots.length - 1;
}

/* Predict, then reveal ---------------------------------------------------------------- */

function fill(template, session) {
  return template
    .replaceAll("{first_request}", fmt(session.firstRequest))
    .replaceAll("{last_request}", fmt(session.lastRequest))
    .replaceAll("{total_input}", fmt(session.totalInput))
    .replaceAll("{growth}", (session.lastRequest / session.firstRequest).toFixed(1));
}

function initPredict(predict, session) {
  document.getElementById("predict-question").textContent = fill(predict.question, session);
  const choices = document.getElementById("predict-choices");
  const reveal = document.getElementById("predict-reveal");
  choices.replaceChildren();
  predict.choices.forEach((choice) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button";
    button.textContent = choice;
    button.addEventListener("click", () => {
      for (const b of choices.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b === button));
      reveal.textContent = `You guessed: ${choice.toLowerCase()}. ${fill(predict.reveal, session)}`;
    });
    choices.append(button);
  });
}

/* Page ---------------------------------------------------------------------------------- */

async function main() {
  initPage();
  const content = await initSection("loop");
  if (!content) return;

  const session = buildSession(content);
  const perBlock = content.tokens_per_block;
  document.getElementById("source-note").textContent = content.source_note;
  document.querySelectorAll("[data-content='block-scale']").forEach((node) => {
    node.textContent = `One block = ${perBlock} tokens.`;
  });
  const hasStale = content.session.some((event) => event.stale);
  const used = new Set([...content.fixed, ...content.session.map((e) => e.item).filter(Boolean)].map((i) => i.role));
  const roles = Object.keys(ROLES).filter((role) => used.has(role));
  document.querySelectorAll(".loop-legend").forEach((list) => renderLegend(list, roles, hasStale));

  // Narrative ------------------------------------------------------------
  const stepsBox = document.getElementById("narrative-steps");
  stepsBox.replaceChildren();
  for (const step of content.steps) {
    const wrap = document.createElement("div");
    wrap.className = "step";
    const card = document.createElement("div");
    card.className = "step-card";
    const p = document.createElement("p");
    p.textContent = step.text;
    card.append(p);
    wrap.append(card);
    stepsBox.append(wrap);
  }

  const narrative = mountLoopScene(document.getElementById("narrative-scene"), session, perBlock);
  let lastNarrative = -1;
  createScrolly({
    steps: [...stepsBox.children],
    prev: document.getElementById("narrative-prev"),
    next: document.getElementById("narrative-next"),
    status: document.getElementById("narrative-status"),
    onStep: (i) => {
      const target = content.steps[i].state.session_step;
      // Animate only when the narrative moves forward to the very next event.
      const from = lastNarrative >= 0 ? content.steps[lastNarrative].state.session_step : null;
      narrative.show(target, { animateFrom: i === lastNarrative + 1 && from === target - 1 ? from : null });
      lastNarrative = i;
    },
  });

  // Predict --------------------------------------------------------------
  initPredict(content.predict, session);

  // Sandbox -----------------------------------------------------------------
  const sandbox = mountLoopScene(document.getElementById("sandbox-scene"), session, perBlock);
  const els = {
    stage: document.getElementById("panel-stage"),
    explain: document.getElementById("panel-explain"),
    requestLabel: document.getElementById("readout-request-label"),
    requestSize: document.getElementById("readout-request"),
    conversation: document.getElementById("readout-conversation"),
    totalInput: document.getElementById("readout-total"),
    seenTitle: document.getElementById("seen-title"),
    seenList: document.getElementById("seen-list"),
    seenTotal: document.getElementById("seen-total"),
    status: document.getElementById("sandbox-status"),
    prev: document.getElementById("sandbox-prev"),
    next: document.getElementById("sandbox-next"),
  };

  const go = (i, animateFrom = null) => {
    sandbox.show(i, { animateFrom });
    renderPanel(session.snapshots[i], session, els);
  };
  els.prev.addEventListener("click", () => go(sandbox.index - 1));
  els.next.addEventListener("click", () => go(sandbox.index + 1, sandbox.index));
  document.getElementById("sandbox-reset").addEventListener("click", () => go(0));

  const seenToggle = document.getElementById("seen-toggle");
  const seenPanel = document.getElementById("seen-panel");
  seenToggle.addEventListener("click", () => {
    const open = seenToggle.getAttribute("aria-expanded") !== "true";
    seenToggle.setAttribute("aria-expanded", String(open));
    seenPanel.hidden = !open;
  });

  go(0);
}

main();
