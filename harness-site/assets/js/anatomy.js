/*
  anatomy.js: the harness anatomy section.

  Two parts, both drawn on the shared world from scene.js:
  - a tour player: press Play and a line travels the path one request
    takes through the harness, stopping at each component while a caption
    explains it
  - a sandbox where each component (and the model) can be selected to
    read what it does, plus a "Show model only" toggle

  Both redraw from their own state at any time (for example when the
  layout switches on resize), so nothing depends on how you got there.
*/

import { initPage, initSection, resolveSiteLink } from "./common.js";
import { COMPONENTS, el, text, mountWorld, setSceneLabel, prefersReducedMotion, setSceneInteractive } from "./scene.js";

const ALL_IDS = COMPONENTS.map((c) => c.id);
const RING = new Set(ALL_IDS);

/* Making parts selectable ------------------------------------------------------ */

/**
 * Make the components and the model keyboard-operable buttons. Called after
 * every redraw, because a redraw replaces the SVG.
 */
function makeSelectable(handles, onSelect, tooltip = null) {
  const targets = [
    ...COMPONENTS.map((c) => [c.id, handles.components[c.id], c.label]),
    ["model", handles.model, "The model"],
  ];
  setSceneInteractive(handles.model.ownerSVGElement);
  for (const [id, node, label] of targets) {
    node.dataset.id = id;
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "button");
    // Name the control from its visible SVG text; tooltip text is supplementary.
    const labels = [...node.querySelectorAll("text")];
    labels.forEach((text, index) => { text.id = `${handles.svg.dataset.hatch}-${id}-label-${index}`; });
    node.setAttribute("aria-labelledby", labels.map((text) => text.id).join(" "));
    node.classList.add("is-selectable");
    node.setAttribute("aria-description", tooltip ? tooltip(label) : label);
    node.addEventListener("click", () => onSelect(id));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect(id);
      }
    });
  }
}

function highlight(handles, target) {
  for (const [id, node] of Object.entries(handles.components)) {
    node.classList.toggle("is-active", id === target);
  }
  handles.model.classList.toggle("is-active", target === "model");
  handles.you.classList.toggle("is-active", target === "you");
  handles.world.classList.toggle("is-active", target === "world");
}

/* Tour: routing the line ----------------------------------------------------------- */

/*
  The line follows the drawing, not straight chords across it:
  - between two components on the ring it runs along the ring (an arc)
  - between a component and the model it runs along the spoke
  - You and your files connect by their straight links
  Stops can list "via" places, so the line can return the way it came.
*/
function segment(from, to, handles) {
  const P = handles.points;
  const G = handles.geometry;
  const a = P[from];
  const b = P[to];
  if (RING.has(from) && RING.has(to)) {
    let delta = G.angles[to] - G.angles[from];
    delta = ((delta + 540) % 360) - 180; // shortest way round, in degrees
    const sweep = delta > 0 ? 1 : 0; // angles run clockwise in SVG
    return `M ${a.x} ${a.y} A ${G.r} ${G.r} 0 0 ${sweep} ${b.x} ${b.y}`;
  }
  return `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
}

/** Path data for the move into stop `index` (empty for the first stop). */
function legFor(steps, index, handles) {
  if (index === 0) return "";
  const route = [steps[index - 1].state.target, ...(steps[index].state.via || []), steps[index].state.target];
  const parts = [];
  for (let i = 1; i < route.length; i += 1) parts.push(segment(route[i - 1], route[i], handles));
  return parts.join(" ");
}

/**
 * Show a stop's payload. Diff lines are tinted like a terminal; the leading
 * - and + stay visible, so color is never the only cue.
 */
function renderWire(pre, wire) {
  pre.hidden = !wire;
  pre.replaceChildren();
  if (!wire) return;
  for (const line of wire.split("\n")) {
    const span = document.createElement("span");
    if (line.startsWith("-") && !line.startsWith("---")) span.className = "wire-del";
    if (line.startsWith("+") && !line.startsWith("+++")) span.className = "wire-add";
    span.textContent = `${line}\n`;
    pre.append(span);
  }
}

/* Tour: player ------------------------------------------------------------------------ */

/**
 * The player holds several tours (the general path, and a recorded example)
 * on one diagram. Switching tours starts the new one from its first stop.
 */
function createTour(tours, els) {
  let tour = tours[0];
  let steps = tour.steps;
  let handles = null;
  let index = 0;
  let playing = false;
  let timer = 0;
  let frame = 0;

  // Reading time for a stop: about 4 words a second for the caption, plus
  // time to glance at each line of the payload, plus a pause.
  const dwell = (step) => 1500 + step.text.split(/\s+/).length * 240
    + (step.state.wire ? step.state.wire.split("\n").length * 700 : 0);
  let maxTokens = 0;
  const fmt = (n) => n.toLocaleString("en-US");

  function stopMotion() {
    window.clearTimeout(timer);
    window.cancelAnimationFrame(frame);
    els.progress.getAnimations?.().forEach((a) => a.cancel());
    els.progress.style.width = "0%";
  }

  /**
   * Draw the trail up to `upTo` with no motion. The trail sits behind the
   * parts of the diagram, so it reads as running between them and never
   * covers a label; at rest the highlighted part marks where it stopped.
   */
  function drawStatic(upTo) {
    const svg = handles.svg;
    svg.querySelectorAll(".tour, .tour-dot").forEach((n) => n.remove());
    const g = el("g", { class: "tour", "aria-hidden": "true" });
    svg.querySelector(".links").after(g);
    for (let i = 1; i <= upTo; i += 1) {
      const d = legFor(steps, i, handles);
      el("path", { class: "tour-glow", d }, g);
      el("path", { class: `tour-line${i === upTo ? " is-current" : ""}`, d }, g);
    }
    return g;
  }

  /** Animate the newest leg: the line draws itself and the dot rides its tip. */
  function animateLeg(to, done) {
    const g = drawStatic(to - 1);
    const d = legFor(steps, to, handles);
    el("path", { class: "tour-glow", d }, g);
    const line = el("path", { class: "tour-line is-current", d }, g);
    // While moving, a dot rides the tip of the line, above everything.
    const dot = el("circle", { class: "tour-dot", r: 7, "aria-hidden": "true" }, handles.svg);
    const length = line.getTotalLength();
    const duration = Math.min(1600, Math.max(500, length * 2.2));
    line.style.strokeDasharray = `${length}`;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      line.style.strokeDashoffset = `${length * (1 - eased)}`;
      const p = line.getPointAtLength(length * eased);
      dot.setAttribute("cx", p.x);
      dot.setAttribute("cy", p.y);
      if (t < 1) frame = window.requestAnimationFrame(tick);
      else { line.style.strokeDasharray = ""; dot.remove(); done(); }
    };
    frame = window.requestAnimationFrame(tick);
  }

  // The request shown is the latest one sent at or before this stop.
  function requestAt(i) {
    for (let k = i; k >= 0; k -= 1) if (steps[k].state.request) return steps[k].state.request;
    return null;
  }

  function renderCaption() {
    const step = steps[index];
    const phase = tour.phases.find((ph) => ph.id === step.state.phase);
    els.title.textContent = step.state.title;
    els.text.textContent = step.text;
    els.status.textContent = `${phase ? phase.label : ""} · stop ${index + 1} of ${steps.length}`;

    renderWire(els.wire, step.state.wire);

    const req = requestAt(index);
    els.meter.hidden = !req;
    if (req) {
      els.meterLabel.textContent = `Request ${req.number}`;
      els.meterValue.textContent = `${fmt(req.tokens)} tokens`;
      els.meterBar.style.width = `${(req.tokens / maxTokens) * 100}%`;
    }
    els.back.disabled = index === 0;
    els.next.disabled = index === steps.length - 1;
    els.play.textContent = playing ? "Pause" : index === steps.length - 1 ? "Play again" : "Play";
    els.chapters.querySelectorAll("button").forEach((b) => {
      if (b.dataset.phase === step.state.phase) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
    });
    highlight(handles, step.state.target);
    setSceneLabel(handles.svg, `Stop ${index + 1} of ${steps.length}: ${step.state.title}. ${step.text}`);
  }

  /** Go to a stop. Moving forward one stop animates; anything else jumps. */
  function goTo(next, { animated = false } = {}) {
    stopMotion();
    const forward = next === index + 1;
    index = next;
    renderCaption();
    const settle = () => {
      if (!playing) return;
      if (index === steps.length - 1) { playing = false; renderCaption(); return; }
      if (!prefersReducedMotion()) {
        els.progress.animate([{ width: "0%" }, { width: "100%" }], { duration: dwell(steps[index]), fill: "forwards" });
      }
      timer = window.setTimeout(() => goTo(index + 1, { animated: true }), dwell(steps[index]));
    };
    if (animated && forward && !prefersReducedMotion()) animateLeg(index, settle);
    else { drawStatic(index); settle(); }
  }

  function setPlaying(value) {
    playing = value;
    if (playing) {
      if (index === steps.length - 1) goTo(0);
      else goTo(index + 1, { animated: true });
    } else {
      stopMotion();
      drawStatic(index);
      renderCaption();
    }
  }

  // Controls --------------------------------------------------------------------
  els.play.addEventListener("click", () => setPlaying(!playing));
  els.back.addEventListener("click", () => { playing = false; goTo(index - 1); });
  els.next.addEventListener("click", () => { playing = false; goTo(index + 1, { animated: true }); });
  els.restart.addEventListener("click", () => { playing = false; goTo(0); });

  // One button per phase; each jumps to the phase's first stop.
  function renderPhases() {
    els.chapters.replaceChildren();
    for (const phase of tour.phases) {
      const first = steps.findIndex((s) => s.state.phase === phase.id);
      if (first < 0) continue;
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chapter";
      b.dataset.phase = phase.id;
      b.textContent = phase.label;
      b.addEventListener("click", () => { playing = false; goTo(first); });
      li.append(b);
      els.chapters.append(li);
    }
  }

  // Tabs: one per tour, following the ARIA tabs pattern (arrow keys move
  // between tabs; only the selected tab is in the tab order).
  const tabs = tours.map((t) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tab";
    b.id = `tour-tab-${t.id}`;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-controls", els.panel.id);
    b.textContent = t.label;
    b.addEventListener("click", () => selectTour(t.id));
    b.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const next = tours[(tours.indexOf(t) + step + tours.length) % tours.length];
      selectTour(next.id);
      document.getElementById(`tour-tab-${next.id}`).focus();
    });
    return b;
  });
  els.tabs.replaceChildren(...tabs);

  function selectTour(id) {
    tour = tours.find((t) => t.id === id) || tours[0];
    steps = tour.steps;
    maxTokens = Math.max(0, ...steps.map((s) => s.state.request?.tokens || 0));
    playing = false;
    stopMotion();
    index = 0;
    for (const b of tabs) {
      const selected = b.id === `tour-tab-${tour.id}`;
      b.setAttribute("aria-selected", String(selected));
      b.tabIndex = selected ? 0 : -1;
    }
    els.panel.setAttribute("aria-labelledby", `tour-tab-${tour.id}`);
    els.intro.textContent = tour.intro;
    // Reserve room for payloads only in tours that show them, so the caption
    // does not jump between stops but has no empty gap either.
    els.panel.dataset.wire = String(steps.some((s) => s.state.wire));
    renderPhases();
    if (handles) { drawStatic(0); renderCaption(); }
  }

  // Clicking a part of the diagram jumps to its first stop.
  const jumpTo = (id) => {
    const i = steps.findIndex((s) => s.state.target === id);
    if (i >= 0) { playing = false; goTo(i); }
  };

  selectTour(tours[0].id);

  // Desktop shortcuts while the tour is in use: Space plays or pauses,
  // the arrow keys step. Tabs keep their own arrow keys, and Space on a
  // focused button keeps its usual meaning (pressing that button).
  els.panel.closest("section").addEventListener("keydown", (event) => {
    // A focused diagram part already used this key (Enter or Space selects it).
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    const onTab = event.target.getAttribute?.("role") === "tab";
    const onButton = event.target.tagName === "BUTTON";
    if (event.key === " " && !onButton) {
      event.preventDefault();
      setPlaying(!playing);
    } else if (event.key === "ArrowRight" && !onTab && index < steps.length - 1) {
      event.preventDefault();
      playing = false;
      goTo(index + 1, { animated: true });
    } else if (event.key === "ArrowLeft" && !onTab && index > 0) {
      event.preventDefault();
      playing = false;
      goTo(index - 1);
    }
  });

  mountWorld(els.scene, (h) => {
    handles = h;
    makeSelectable(h, jumpTo, (label) => `${label}: jump to this stop`);
    stopMotion();
    drawStatic(index);
    renderCaption();
    // A redraw mid-play (layout change) carries on from the current stop.
    if (playing) goTo(index);
  });
}

/* Sandbox ----------------------------------------------------------------------------- */

/** The model writes a request, and nothing carries it out. */
function drawBubble(handles, bubble) {
  const P = handles.points.model;
  const wide = handles.layout === "wide";
  const g = el("g", { class: "bubble" }, handles.svg);
  const x = wide ? P.x + 95 : P.x;
  const y = wide ? P.y - 70 : P.y - 110;
  text(g, x, y, bubble.text, { class: "mono bubble-text", "text-anchor": wide ? "start" : "middle" });
  text(g, x, y + 20, bubble.caption, { class: "label-muted", "text-anchor": wide ? "start" : "middle" });
}

function applySandbox(handles, { alone, selected }, content) {
  const svg = handles.svg;
  for (const [id, node] of Object.entries(handles.components)) {
    node.classList.toggle("is-gone", alone);
    node.classList.toggle("is-active", !alone && selected === id);
  }
  handles.model.classList.toggle("is-active", alone || selected === "model");
  svg.querySelectorAll("[data-for], .harness-ring, .ring-label").forEach((n) => n.classList.toggle("is-gone", alone));
  svg.querySelector(".bubble")?.remove();
  if (alone) drawBubble(handles, content.bubble);

  for (const node of svg.querySelectorAll("[role='button']")) {
    const id = node.dataset.id;
    node.setAttribute("aria-pressed", String(!alone && selected === id));
    // Faded parts leave the tab order, so keyboard users do not land on
    // things they cannot see.
    node.setAttribute("tabindex", alone && id !== "model" ? "-1" : "0");
  }
  setSceneLabel(svg, alone
    ? "The model alone. Every harness component is gone, so nothing connects it to you or to your files. It writes a request that nobody carries out."
    : "The model in the center, surrounded by the harness: Interface, Instructions, Context, Tools, Permissions, and Memory. Select any part to learn what it does.");
}

function renderPanel(panel, content, selection) {
  const { title, example, what, why, link } = panel;
  link.hidden = true;
  example.hidden = true;

  if (selection === "model-only") {
    title.textContent = "The model alone";
    what.textContent = content.model_only;
    why.textContent = "";
    return;
  }
  if (selection === "model") {
    title.textContent = content.model.label;
    what.textContent = content.model.what;
    why.textContent = content.model.why;
    return;
  }
  const comp = content.components.find((c) => c.id === selection);
  if (!comp) {
    title.textContent = "The harness";
    what.textContent = content.intro;
    why.textContent = "";
    return;
  }
  title.textContent = comp.label;
  example.textContent = comp.example;
  example.hidden = false;
  what.textContent = comp.what;
  why.textContent = `Why it matters: ${comp.why}`;
  link.href = resolveSiteLink(comp.module_link);
  link.textContent = `Covered in ${comp.module_title}`;
  link.hidden = false;
}

function createSandbox(content) {
  const panel = {
    title: document.getElementById("panel-title"),
    example: document.getElementById("panel-example"),
    what: document.getElementById("panel-what"),
    why: document.getElementById("panel-why"),
    link: document.getElementById("panel-link"),
  };
  const aloneButton = document.getElementById("model-only");
  const state = { alone: false, selected: null };
  let handles = null;

  const render = () => {
    applySandbox(handles, state, content);
    aloneButton.setAttribute("aria-pressed", String(state.alone));
    renderPanel(panel, content, state.alone ? "model-only" : state.selected);
  };

  mountWorld(document.getElementById("sandbox-scene"), (h) => {
    handles = h;
    makeSelectable(h, (id) => { state.alone = false; state.selected = id; render(); },
      (label) => `${label}: what it does`);
    render();
  });

  aloneButton.addEventListener("click", () => {
    state.alone = !state.alone;
    if (state.alone) state.selected = null;
    render();
  });
}

/* Page ---------------------------------------------------------------------------------- */

async function main() {
  initPage();
  const content = await initSection("anatomy");
  if (!content) return;

  createTour(content.tours, {
    tabs: document.getElementById("tour-tabs"),
    panel: document.getElementById("tour-panel"),
    intro: document.getElementById("tour-intro"),
    scene: document.getElementById("tour-scene"),
    title: document.getElementById("tour-title"),
    text: document.getElementById("tour-text"),
    status: document.getElementById("tour-status"),
    progress: document.getElementById("tour-progress"),
    play: document.getElementById("tour-play"),
    back: document.getElementById("tour-back"),
    next: document.getElementById("tour-next"),
    restart: document.getElementById("tour-restart"),
    chapters: document.getElementById("tour-chapters"),
    wire: document.getElementById("tour-wire"),
    meter: document.getElementById("tour-meter"),
    meterLabel: document.getElementById("tour-meter-label"),
    meterValue: document.getElementById("tour-meter-value"),
    meterBar: document.getElementById("tour-meter-bar"),
  });
  createSandbox(content);
}

main();
