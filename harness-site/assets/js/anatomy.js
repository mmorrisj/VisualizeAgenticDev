/*
  anatomy.js: the harness anatomy section.

  Both parts draw the shared world from scene.js:
  - a guided narrative that strips the harness away, one component at a
    time, until the model is alone, then puts it back
  - a sandbox where each component (and the model) can be selected to
    read what it does, plus a "Show model only" toggle

  Every state is applied from scratch by applyState(), so the world can be
  redrawn at any time (for example when the layout switches on resize).
*/

import { initPage, initSection, resolveSiteLink } from "./common.js";
import { COMPONENTS, el, text, mountWorld, setSceneLabel, animate, prefersReducedMotion } from "./scene.js";
import { createScrolly } from "./scrolly.js";

const ALL_IDS = COMPONENTS.map((c) => c.id);

/* Applying a state to a drawn world -------------------------------------------- */

/**
 * state: {
 *   hidden: component ids to fade out
 *   selected: component id (or "model") to highlight
 *   pulse: trace a request from You to your files
 *   bubble: show the model writing text that nothing acts on
 * }
 */
function applyState(handles, state, content, { animateMotion = false } = {}) {
  const hidden = new Set(state.hidden || []);
  const svg = handles.svg;

  for (const [id, node] of Object.entries(handles.components)) {
    node.classList.toggle("is-gone", hidden.has(id));
    node.classList.toggle("is-active", state.selected === id);
  }
  handles.model.classList.toggle("is-active", state.selected === "model" || hidden.size === ALL_IDS.length);

  // Lines belong to a component and disappear with it. The ring goes
  // once every component is gone.
  svg.querySelectorAll("[data-for]").forEach((line) => {
    line.classList.toggle("is-gone", hidden.has(line.dataset.for));
  });
  svg.querySelector(".harness-ring").classList.toggle("is-gone", hidden.size === ALL_IDS.length);
  svg.querySelector(".ring-label").classList.toggle("is-gone", hidden.size === ALL_IDS.length);

  svg.querySelectorAll(".pulse, .bubble").forEach((node) => node.remove());
  svg.querySelectorAll(".is-traced").forEach((node) => node.classList.remove("is-traced"));
  if (state.pulse) drawPulse(handles, animateMotion);
  if (state.bubble) drawBubble(handles, content.bubble, animateMotion);

  setSceneLabel(svg, describe(state));
}

function describe(state) {
  const hidden = new Set(state.hidden || []);
  if (hidden.size === ALL_IDS.length) {
    return "The model alone. Every harness component is gone, so nothing connects it to you or to your files. It writes a request that nobody carries out.";
  }
  const present = COMPONENTS.filter((c) => !hidden.has(c.id)).map((c) => c.label);
  const gone = COMPONENTS.filter((c) => hidden.has(c.id)).map((c) => c.label);
  let label = `The model in the center, surrounded by the harness: ${present.join(", ")}.`;
  if (gone.length) label += ` Removed: ${gone.join(", ")}.`;
  if (state.pulse) label += " A request travels from you, through the interface, to the model, and out through the tools to your files.";
  return label;
}

/**
 * A dot that travels the path of one request: You, Interface, Model,
 * Tools, your files. With reduced motion, the path's lines are
 * highlighted instead.
 */
function drawPulse(handles, animateMotion) {
  const P = handles.points;
  const path = [P.you, P.interface, P.model, P.tools, P.world];
  handles.svg.querySelectorAll(".link, .spoke[data-for='interface'], .spoke[data-for='tools']")
    .forEach((line) => line.classList.add("is-traced"));

  if (!animateMotion || prefersReducedMotion()) return;
  const dot = el("circle", { class: "pulse", r: 7, cx: 0, cy: 0, "aria-hidden": "true" }, handles.svg);
  animate(dot, path.map((p, i) => ({
    transform: `translate(${p.x}px, ${p.y}px)`,
    opacity: i === path.length - 1 ? 0 : 1,
  })), { duration: 2000, easing: "ease-in-out" }).then(() => dot.remove());
}

/** The model writes a request, and it drifts off into nothing. */
function drawBubble(handles, bubble, animateMotion) {
  const P = handles.points.model;
  const wide = handles.layout === "wide";
  const g = el("g", { class: "bubble" }, handles.svg);
  const x = wide ? P.x + 95 : P.x;
  const y = wide ? P.y - 70 : P.y - 110;
  text(g, x, y, bubble.text, { class: "mono bubble-text", "text-anchor": wide ? "start" : "middle" });
  text(g, x, y + 20, bubble.caption, { class: "label-muted", "text-anchor": wide ? "start" : "middle" });

  if (animateMotion) {
    animate(g, [
      { transform: "translate(-40px, 30px)", opacity: 0 },
      { transform: "translate(0px, 0px)", opacity: 1, offset: 0.35 },
      { transform: "translate(30px, -16px)", opacity: 0.75 },
    ], { duration: 2400, delay: 300 });
  } else {
    g.style.opacity = "0.75";
  }
}

/* Panel ------------------------------------------------------------------------------ */

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

/**
 * Make the components and the model keyboard-operable buttons. Called after
 * every redraw, because a redraw replaces the SVG.
 */
function makeSelectable(handles, content, onSelect, current) {
  const targets = [
    ...COMPONENTS.map((c) => [c.id, handles.components[c.id], c.label]),
    ["model", handles.model, "The model"],
  ];
  for (const [id, node, label] of targets) {
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", label);
    node.setAttribute("aria-pressed", String(current() === id));
    node.classList.add("is-selectable");
    node.addEventListener("click", () => onSelect(id));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect(id);
      }
    });
  }
}

/* Page ---------------------------------------------------------------------------------- */

async function main() {
  initPage();
  const content = await initSection("anatomy");
  if (!content) return;

  // Narrative --------------------------------------------------------------
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

  let narrativeIndex = 0;
  let narrativeWorld = null;
  mountWorld(document.getElementById("narrative-scene"), (handles) => {
    narrativeWorld = handles;
    applyState(handles, content.steps[narrativeIndex].state, content);
  });
  createScrolly({
    steps: [...stepsBox.children],
    prev: document.getElementById("narrative-prev"),
    next: document.getElementById("narrative-next"),
    status: document.getElementById("narrative-status"),
    onStep: (i) => {
      narrativeIndex = i;
      if (narrativeWorld) applyState(narrativeWorld, content.steps[i].state, content, { animateMotion: true });
    },
  });

  // Sandbox ------------------------------------------------------------------
  const panel = {
    title: document.getElementById("panel-title"),
    example: document.getElementById("panel-example"),
    what: document.getElementById("panel-what"),
    why: document.getElementById("panel-why"),
    link: document.getElementById("panel-link"),
  };
  const aloneButton = document.getElementById("model-only");
  let selected = null;
  let alone = false;
  let sandboxWorld = null;

  const render = () => {
    const state = alone ? { hidden: ALL_IDS } : { hidden: [], selected };
    applyState(sandboxWorld, state, content);
    for (const node of sandboxWorld.svg.querySelectorAll("[role='button']")) {
      const id = node.dataset.id || "model";
      node.setAttribute("aria-pressed", String(!alone && selected === id));
      // Faded parts leave the tab order, so keyboard users do not land on
      // things they cannot see.
      node.setAttribute("tabindex", alone && id !== "model" ? "-1" : "0");
    }
    aloneButton.setAttribute("aria-pressed", String(alone));
    renderPanel(panel, content, alone ? "model-only" : selected);
  };

  const select = (id) => {
    alone = false;
    selected = id;
    render();
  };

  mountWorld(document.getElementById("sandbox-scene"), (handles) => {
    sandboxWorld = handles;
    makeSelectable(handles, content, select, () => selected);
    render();
  });

  aloneButton.addEventListener("click", () => {
    alone = !alone;
    if (alone) selected = null;
    render();
  });
}

main();
