/*
  scene.js: the shared visual world and its primitives.

  Every section draws with these helpers so the model, the harness, and
  each content role look identical everywhere (spec section 5.1).

  Conventions:
  - Colors are never set here. Elements get CSS classes (role-result,
    model-box, ...) and site.css maps them to theme tokens, so switching
    themes needs no redraw.
  - Every top-level SVG gets role="img" and an aria-label. Callers update
    the label when the scene's meaning changes.
  - Sizes are in SVG user units; the SVG scales to its container.
*/

// XML namespace for SVG elements. This is an identifier, not a network
// address; check.py allowlists it.
export const SVG_NS = "http://www.w3.org/2000/svg";

/** Content roles. Order here is the order they appear in a request. */
export const ROLES = {
  system: { label: "System prompt" },
  tools: { label: "Tool definitions" },
  instructions: { label: "Instructions file" },
  user: { label: "Your message" },
  model: { label: "Model message" },
  result: { label: "Tool result" },
  summary: { label: "Compaction summary" },
};

/** The six harness components, in the order they sit on the ring. */
export const COMPONENTS = [
  { id: "interface", label: "Interface" },
  { id: "instructions", label: "Instructions" },
  { id: "context", label: "Context" },
  { id: "tools", label: "Tools" },
  { id: "permissions", label: "Permissions" },
  { id: "memory", label: "Memory" },
];

/* Token blocks: one block stands for a fixed number of tokens. */
export const BLOCK = { size: 10, gap: 2 };

let uid = 0;

/* Basics ------------------------------------------------------------------- */

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Create an SVG element with attributes, optionally appending to a parent. */
export function el(tag, attrs = {}, parent = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null) node.setAttribute(key, String(value));
  }
  if (parent) parent.append(node);
  return node;
}

/** SVG text helper. */
export function text(parent, x, y, content, attrs = {}) {
  const node = el("text", { x, y, ...attrs }, parent);
  node.textContent = content;
  return node;
}

/**
 * Create the root SVG for a scene inside `container`, replacing its contents.
 * Also defines the hatch pattern used by compaction summaries.
 */
export function createScene(container, { width, height, label }) {
  const svg = el("svg", {
    class: "scene",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": label,
    focusable: "false",
  });

  // Each SVG gets its own pattern id so several scenes can share a page.
  const hatchId = `hatch-${++uid}`;
  const defs = el("defs", {}, svg);
  const pattern = el(
    "pattern",
    { id: hatchId, width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
    defs
  );
  el("rect", { class: "hatch-bg", width: 6, height: 6 }, pattern);
  el("line", { class: "hatch-line", x1: 0, y1: 0, x2: 0, y2: 6 }, pattern);
  svg.dataset.hatch = hatchId;

  container.replaceChildren(svg);
  return svg;
}

export function setSceneLabel(svg, label) {
  svg.setAttribute("aria-label", label);
}

/**
 * A scene with clickable or focusable parts is a labelled group, not an
 * image: role="img" hides its children from assistive technology, so the
 * parts' buttons would be unreachable.
 */
export function setSceneInteractive(svg) {
  svg.setAttribute("role", "group");
}

/* Model, harness, world ------------------------------------------------------ */

/** The model: a sealed box. It never has connections of its own. */
export function drawModel(parent, { cx, cy, w = 150, h = 96, label = "Model", sublabel = "predicts text" }) {
  const g = el("g", { class: "model" }, parent);
  el("rect", { class: "model-box", x: cx - w / 2, y: cy - h / 2, width: w, height: h, rx: 14 }, g);
  el("rect", { class: "model-core", x: cx - w / 2 + 10, y: cy - h / 2 + 10, width: w - 20, height: h - 20, rx: 8 }, g);
  text(g, cx, cy - 2, label, { "text-anchor": "middle", class: "label-strong", "font-size": 17 });
  if (sublabel) text(g, cx, cy + 18, sublabel, { "text-anchor": "middle", class: "label-muted" });
  return g;
}

/** A component pill on the harness ring. */
export function drawComponent(parent, { cx, cy, label, id, w = 116, h = 32 }) {
  const g = el("g", { class: "component", "data-id": id }, parent);
  el("rect", { class: "component-pill", x: cx - w / 2, y: cy - h / 2, width: w, height: h, rx: h / 2 }, g);
  text(g, cx, cy + 5, label, { "text-anchor": "middle", "font-size": 15 });
  return g;
}

/**
 * Two layouts for the world. "wide" puts You left and the outside world
 * right; "tall" stacks them so labels stay readable on phones.
 * Angles are degrees, 0 = right, measured clockwise (SVG y points down).
 */
const WORLD_LAYOUTS = {
  wide: {
    width: 860, height: 440, cx: 430, cy: 220, r: 165, pill: 116,
    angles: { interface: 180, instructions: 240, context: 300, tools: 0, permissions: 60, memory: 120 },
    you: { x: 60, y: 220 },
    world: { x: 790, y: 220, w: 120, h: 70 },
    ringLabel: { x: 430, y: 41, anchor: "middle" },
  },
  tall: {
    width: 400, height: 600, cx: 200, cy: 300, r: 150, pill: 104,
    angles: { interface: 270, instructions: 330, context: 30, tools: 90, permissions: 150, memory: 210 },
    you: { x: 200, y: 44 },
    world: { x: 200, y: 552, w: 170, h: 56 },
    ringLabel: { x: 340, y: 304, anchor: "end" },
  },
};

/**
 * Draw the shared world: You, the harness ring with six components, the
 * model in the middle, and your files, shell, and APIs outside.
 * Returns handles so sections can highlight or fade parts.
 */
export function drawWorld(container, { layout = "wide", label } = {}) {
  const L = WORLD_LAYOUTS[layout];
  const svg = createScene(container, {
    width: L.width,
    height: L.height,
    label:
      label ||
      "The model sits alone in the center. Around it, the harness ring holds six components: " +
        "Interface, Instructions, Context, Tools, Permissions, and Memory. You connect only to the " +
        "Interface; only Tools reach your files, shell, and APIs.",
  });

  const point = (deg, r = L.r) => {
    const rad = (deg * Math.PI) / 180;
    return { x: L.cx + r * Math.cos(rad), y: L.cy + r * Math.sin(rad) };
  };

  const links = el("g", { class: "links" }, svg);
  el("circle", { class: "harness-ring", cx: L.cx, cy: L.cy, r: L.r }, svg);
  text(svg, L.ringLabel.x, L.ringLabel.y, "Harness", { "text-anchor": L.ringLabel.anchor, class: "label-muted ring-label" });

  // Spokes: the model reaches the world only through components.
  for (const comp of COMPONENTS) {
    const p = point(L.angles[comp.id], L.r - 18);
    el("line", { class: "spoke", "data-for": comp.id, x1: L.cx, y1: L.cy, x2: p.x, y2: p.y }, links);
  }

  const model = drawModel(svg, { cx: L.cx, cy: L.cy });

  const components = {};
  for (const comp of COMPONENTS) {
    const p = point(L.angles[comp.id]);
    components[comp.id] = drawComponent(svg, { cx: p.x, cy: p.y, label: comp.label, id: comp.id, w: L.pill });
  }

  // You: a circle outside the ring, linked to Interface.
  const you = el("g", { class: "actor" }, svg);
  el("circle", { class: "actor-shape", cx: L.you.x, cy: L.you.y, r: 26 }, you);
  text(you, L.you.x, L.you.y + 5, "You", { "text-anchor": "middle", class: "label-strong" });

  // Files, shell, APIs: a dashed box outside the ring, linked to Tools.
  const world = el("g", { class: "world" }, svg);
  const W = L.world;
  el("rect", { class: "world-shape", x: W.x - W.w / 2, y: W.y - W.h / 2, width: W.w, height: W.h, rx: 8 }, world);
  if (layout === "wide") {
    text(world, W.x, W.y - 4, "Your files,", { "text-anchor": "middle" });
    text(world, W.x, W.y + 14, "shell, APIs", { "text-anchor": "middle" });
  } else {
    text(world, W.x, W.y + 5, "Your files, shell, APIs", { "text-anchor": "middle" });
  }

  // Links from outside nodes to their components (edge to edge).
  const iface = point(L.angles.interface);
  const tools = point(L.angles.tools);
  if (layout === "wide") {
    el("line", { class: "link", "data-for": "interface", x1: L.you.x + 26, y1: L.you.y, x2: iface.x - L.pill / 2, y2: iface.y }, links);
    el("line", { class: "link", "data-for": "tools", x1: tools.x + L.pill / 2, y1: tools.y, x2: W.x - W.w / 2, y2: W.y }, links);
  } else {
    el("line", { class: "link", "data-for": "interface", x1: L.you.x, y1: L.you.y + 26, x2: iface.x, y2: iface.y - 16 }, links);
    el("line", { class: "link", "data-for": "tools", x1: tools.x, y1: tools.y + 16, x2: W.x, y2: W.y - W.h / 2 }, links);
  }

  // Key points, so sections can trace the path a request takes: You, the
  // model, your files, and every component on the ring.
  const points = {
    you: { x: L.you.x, y: L.you.y },
    model: { x: L.cx, y: L.cy },
    world: { x: W.x, y: W.y },
  };
  for (const comp of COMPONENTS) points[comp.id] = point(L.angles[comp.id]);
  const geometry = { cx: L.cx, cy: L.cy, r: L.r, angles: { ...L.angles } };
  return { svg, model, components, you, world, layout, points, geometry };
}

/**
 * Pick a world layout from the container's width and redraw on resize.
 * `onDraw(handles)` runs after every redraw so callers can restore state.
 */
export function mountWorld(container, onDraw = () => {}) {
  let current = null;
  const draw = () => {
    const layout = container.clientWidth < 560 ? "tall" : "wide";
    if (layout === current) return;
    current = layout;
    onDraw(drawWorld(container, { layout }));
  };
  draw();
  if ("ResizeObserver" in window) new ResizeObserver(draw).observe(container);
}

/* Token blocks ---------------------------------------------------------------- */

/**
 * Lay out a sequence of segments as blocks, wrapping into rows.
 * segments: [{ role, blocks, className? }]. Returns the group plus its size.
 * Blocks flow in reading order so a request reads like a sentence.
 */
export function drawBlocks(parent, { x, y, segments, perRow = 24, svg }) {
  const g = el("g", { class: "blocks", transform: `translate(${x} ${y})` }, parent);
  const step = BLOCK.size + BLOCK.gap;
  let i = 0;
  for (const seg of segments) {
    for (let b = 0; b < seg.blocks; b += 1) {
      const col = i % perRow;
      const row = Math.floor(i / perRow);
      const attrs = {
        class: `block role-${seg.role}${seg.className ? ` ${seg.className}` : ""}`,
        x: col * step,
        y: row * step,
        width: BLOCK.size,
        height: BLOCK.size,
        rx: 2,
      };
      // Summaries are hatched so they never rely on color alone.
      if (seg.role === "summary" && svg) attrs.fill = `url(#${svg.dataset.hatch})`;
      el("rect", attrs, g);
      i += 1;
    }
  }
  const rows = Math.max(1, Math.ceil(i / perRow));
  return { group: g, width: Math.min(i, perRow) * step - BLOCK.gap, height: rows * step - BLOCK.gap, count: i };
}

/** A single swatch block, for legends. Returns a small standalone SVG. */
export function legendSwatch(role) {
  const svg = el("svg", { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": "true", focusable: "false" });
  if (role === "summary") {
    el("rect", { x: 1, y: 1, width: 10, height: 10, rx: 2, class: "role-summary" }, svg);
    el("path", { d: "M1 11 11 1 M1 6 6 1 M6 11 11 6", stroke: "var(--surface)", "stroke-width": 1.5 }, svg);
  } else {
    el("rect", { x: 1, y: 1, width: 10, height: 10, rx: 2, class: `role-${role}` }, svg);
  }
  return svg;
}

/** Render an HTML legend for the given roles into a <ul>. */
export function renderLegend(list, roles, counts = {}) {
  list.replaceChildren();
  for (const role of roles) {
    const li = document.createElement("li");
    li.append(legendSwatch(role), ROLES[role].label);
    if (counts[role] !== undefined) {
      const n = document.createElement("span");
      n.className = "mono";
      n.textContent = ` ${counts[role]}`;
      li.append(n);
    }
    list.append(li);
  }
}

/* Context window ------------------------------------------------------------------ */

/**
 * A context window: a frame with a limit line at the right edge and a
 * dashed compaction threshold. Contents are drawn by the caller inside
 * the returned `inner` group, from left to right.
 */
export function drawWindow(parent, { x, y, w, h, threshold = 0.8, limitLabel = "Limit", thresholdLabel = "Compaction at 80%" }) {
  const g = el("g", { class: "context-window" }, parent);
  el("rect", { class: "window-bg", x, y, width: w, height: h, rx: 6 }, g);
  el("rect", { class: "window-frame", x, y, width: w, height: h, rx: 6 }, g);
  const inner = el("g", {}, g);

  const tx = x + w * threshold;
  el("line", { class: "threshold-line", x1: tx, y1: y - 8, x2: tx, y2: y + h + 8 }, g);
  text(g, tx, y + h + 24, thresholdLabel, { "text-anchor": "middle", class: "threshold-label" });

  el("line", { class: "limit-line", x1: x + w, y1: y - 14, x2: x + w, y2: y + h + 14 }, g);
  text(g, x + w, y - 20, limitLabel, { "text-anchor": "end", class: "limit-label" });

  return { group: g, inner };
}

/** A filled horizontal segment inside a window (or anywhere). */
export function drawSegment(parent, { x, y, w, h, role, svg }) {
  const attrs = { class: `block role-${role}`, x, y, width: Math.max(0, w), height: h, rx: 3 };
  if (role === "summary" && svg) {
    attrs.fill = `url(#${svg.dataset.hatch})`;
    attrs.class += " summary-tile";
  }
  return el("rect", attrs, parent);
}

/* Arrows --------------------------------------------------------------------------- */

/** A straight arrow from (x1,y1) to (x2,y2) with a small triangular head. */
export function drawArrow(parent, { x1, y1, x2, y2, active = false, dashed = false }) {
  const g = el("g", {}, parent);
  const cls = (active ? " is-active" : "") + (dashed ? " is-dashed" : "");
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const head = 8;
  el("line", { class: `arrow${cls}`, x1, y1, x2: x2 - head * Math.cos(angle), y2: y2 - head * Math.sin(angle) }, g);
  const p = (a, r) => `${x2 - r * Math.cos(angle + a)},${y2 - r * Math.sin(angle + a)}`;
  el("polygon", { class: `arrow-head${cls}`, points: `${x2},${y2} ${p(0.45, head * 1.4)} ${p(-0.45, head * 1.4)}` }, g);
  return g;
}

/* Motion --------------------------------------------------------------------------- */

/**
 * Run an explanatory animation with the Web Animations API.
 * With reduced motion, jump straight to the final keyframe instead.
 * Resolves when finished either way, so callers can sequence steps.
 */
export function animate(node, keyframes, options = {}) {
  const final = keyframes[keyframes.length - 1];
  if (prefersReducedMotion() || typeof node.animate !== "function") {
    for (const [prop, value] of Object.entries(final)) {
      if (prop !== "offset" && prop !== "easing") node.style[prop] = value;
    }
    return Promise.resolve();
  }
  const anim = node.animate(keyframes, { duration: 900, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)", fill: "forwards", ...options });
  return anim.finished.catch(() => {});
}
