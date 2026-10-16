/*
  inside-extensions.js: section 6.7, Inside an extension.

  One session (triage failing tests, fix them, add a regression test, check
  for empty passwords) seen through four lenses: MCP server, skill, subagent,
  and plugin. Each lens is a Play tour over the same scene: You, the harness,
  and the model across the top; an "outside the model" lane with the MCP
  server process, the skills folder, and the subagent's own context; and the
  context the model receives, drawn as a bar of blocks along the bottom.

  Below the lenses, a cost ledger rebuilds every request of the session for
  any mix of mechanisms, with an illustrative control for test-suite size.

  All numbers come from content/inside-extensions.json, measured by
  tools/measure_inside_extensions.py. composeDetailed() mirrors compose() in
  that script, which check.py also runs, so all three agree on every total.
*/

import { initPage, initSection } from "./common.js";
import { el, text, createScene, setSceneLabel, setSceneInteractive, prefersReducedMotion } from "./scene.js";

const MECHS = ["mcp", "skill", "subagent"];
const MECH_LABEL = { mcp: "MCP server", skill: "Skill", subagent: "Subagent" };
const fmt = (n) => Math.round(n).toLocaleString("en-US");
const tokens = (n) => `${fmt(n)} token${Math.round(n) === 1 ? "" : "s"}`;

/* Data model --------------------------------------------------------------------------- */

function active(when, on) {
  if (when === null || when === undefined) return true;
  return when.startsWith("!") ? !on.has(when.slice(1)) : on.has(when);
}

const eventTokens = (ev, scale) => (ev.scales ? Math.round(ev.tokens * scale) : ev.tokens);

/** Every request of the main conversation, with its parts. Mirrors compose(). */
export function composeDetailed(session, on, scale = 1) {
  const always = Object.entries(session.always)
    .filter(([, b]) => active(b.when, on))
    .map(([id, b]) => ({ id, ...b }));
  const alwaysTotal = always.reduce((a, b) => a + b.tokens, 0);
  const conv = [];
  const requests = [];
  let subTotal = 0;
  let subRequests = 0;
  let subConv = 0;
  for (const ev of session.events) {
    if (!active(ev.when, on)) continue;
    const t = eventTokens(ev, scale);
    if (ev.ctx === "sub") {
      subConv += t;
      if (ev.request_after) { subRequests += 1; subTotal += subConv; }
      continue;
    }
    conv.push({ ...ev, tokens: t });
    if (ev.request_after) {
      const convTotal = conv.reduce((a, e) => a + e.tokens, 0);
      requests.push({ always, conv: conv.slice(), alwaysTotal, convTotal, total: alwaysTotal + convTotal });
    }
  }
  return {
    requests,
    totalInput: requests.reduce((a, r) => a + r.total, 0),
    finalContext: requests.length ? requests[requests.length - 1].total : 0,
    subRequests,
    subInput: subTotal,
  };
}

/** The same summary compose() stores in ledger.expected, for checking. */
export function composeLedger(session, on, scale = 1) {
  const d = composeDetailed(session, on, scale);
  return {
    requests: d.requests.length,
    request_sizes: d.requests.map((r) => r.total),
    total_input: d.totalInput,
    final_context: d.finalContext,
    sub_requests: d.subRequests,
    sub_input: d.subInput,
  };
}

/** What the scene shows at a step: context blocks, the subagent's state, and more. */
function contextAt(session, at, on) {
  // Before the first request the MCP server is running, but the harness has
  // not listed its tools yet, so their definitions are not in the context.
  const always = Object.entries(session.always)
    .filter(([id, b]) => active(b.when, on) && !(at === "start" && id === "mcp-tools"))
    .map(([id, b]) => ({ id, ...b }));
  const conv = [];
  const sub = [];
  let reached = at === "start";
  let summaryIn = false;
  if (!reached) {
    for (const ev of session.events) {
      if (active(ev.when, on)) {
        if (ev.ctx === "sub") sub.push(ev);
        else conv.push(ev);
        if (ev.id === "summary") summaryIn = true;
      }
      if (ev.id === at) break;
    }
  }
  const subState = !on.has("subagent") || sub.length === 0 ? "none" : summaryIn ? "done" : "open";
  const skillLoaded = conv.some((e) => e.id === "skill-body");
  const sum = (list) => list.reduce((a, e) => a + e.tokens, 0);
  return {
    always, conv, sub, subState, skillLoaded,
    alwaysTotal: sum(always), convTotal: sum(conv), subTotal: sum(sub),
    started: at !== "start",
  };
}

/** Replace {dotted.path} placeholders with formatted numbers from the content. */
function fill(textValue, data) {
  return textValue.replace(/\{([a-z_.]+)\}/g, (_, path) => {
    const value = path.split(".").reduce((o, k) => (o ? o[k] : undefined), data);
    return typeof value === "number" ? fmt(value) : `{${path}}`;
  });
}

/* Scene geometry ----------------------------------------------------------------------- */

const W = 1000;
const H = 600;
const G = {
  you: { cx: 70, cy: 100 },
  harness: { x: 150, y: 40, w: 250, h: 132 },
  hook: { x: 168, y: 136, w: 214, h: 24 },
  model: { x: 610, y: 48, w: 170, h: 104 },
  lane: { y: 200 },
  mcp: { x: 150, y: 236, w: 250, h: 92 },
  pipeOut: { x: 245, y1: 172, y2: 236 },
  pipeIn: { x: 305, y1: 236, y2: 172 },
  skills: { x: 430, y: 236, w: 200, h: 92 },
  sub: { x: 660, y: 228, w: 320, h: 146 },
  bar: { x: 40, y: 432, w: 920, h: 46 },
};

const ROLE_LABEL = {
  system: "System prompt", tools: "Tool definitions", user: "Your request", model: "Model's tool calls and text",
  result: "Tool results", skill: "Skill", subagent: "Subagent",
};

function box(parent, { x, y, w, h }, cls, title, sub) {
  const g = el("g", { class: cls }, parent);
  el("rect", { x, y, width: w, height: h, rx: 12, class: "ix-box" }, g);
  text(g, x + 14, y + 26, title, { class: "ix-box-title" });
  if (sub) text(g, x + 14, y + 46, sub, { class: "label-muted" });
  return g;
}

/** Draw the whole scene for one state. Returns handles the effects use. */
function drawScene(container, ctx, opts) {
  const { focus, on, maxTokens, lensId } = opts;
  const svg = createScene(container, { width: W, height: H, label: "" });
  const h = { svg, segs: new Map(), subSegs: new Map() };

  // Top row: you, the harness, the model.
  const you = el("g", { class: "actor" }, svg);
  el("circle", { cx: G.you.cx, cy: G.you.cy, r: 30, class: "actor-shape" }, you);
  text(you, G.you.cx, G.you.cy + 5, "You", { "text-anchor": "middle", class: "ix-box-title" });
  el("line", { x1: 100, y1: G.you.cy, x2: G.harness.x, y2: G.you.cy, class: "arrow" }, svg);

  h.harness = box(svg, G.harness, "ix-harness", "Harness", "runs tools, checks permissions");
  const hookOn = MECHS.every((m) => on.has(m));
  h.hook = el("g", { class: `ix-hook${hookOn ? "" : " is-absent"}${focus === "hook" ? " is-focus" : ""}` }, svg);
  el("rect", { x: G.hook.x, y: G.hook.y, width: G.hook.w, height: G.hook.h, rx: 12, class: "ix-hook-pill" }, h.hook);
  text(h.hook, G.hook.x + G.hook.w / 2, G.hook.y + 16, "PreToolUse hook",
    { "text-anchor": "middle", class: "ix-small" });

  h.model = box(svg, G.model, "ix-model", "Model", "predicts text");
  el("line", { x1: G.harness.x + G.harness.w, y1: 82, x2: G.model.x, y2: 82, class: "arrow" }, svg);
  text(svg, (G.harness.x + G.harness.w + G.model.x) / 2, 74, "request", { "text-anchor": "middle", class: "label-muted" });
  el("line", { x1: G.model.x, y1: 120, x2: G.harness.x + G.harness.w, y2: 120, class: "arrow is-dashed" }, svg);
  text(svg, (G.harness.x + G.harness.w + G.model.x) / 2, 138, "reply: text or a tool call", { "text-anchor": "middle", class: "label-muted" });

  // Outside the model.
  el("line", { x1: 40, y1: G.lane.y, x2: 960, y2: G.lane.y, class: "ix-lane-rule" }, svg);
  text(svg, 40, G.lane.y + 20, "Outside the model", { class: "label-muted" });

  const mcpOn = on.has("mcp");
  h.mcp = box(svg, G.mcp, `ix-mcp${mcpOn ? "" : " is-absent"}${focus === "mcp" ? " is-focus" : ""}`,
    "practice-db", "MCP server: its own process");
  text(h.mcp, G.mcp.x + 14, G.mcp.y + 66, "list_tables, describe_table,", { class: "ix-small mono" });
  text(h.mcp, G.mcp.x + 14, G.mcp.y + 82, "run_select", { class: "ix-small mono" });
  h.pipes = el("g", { class: `ix-pipes${mcpOn ? "" : " is-absent"}` }, svg);
  h.pipeOut = el("line", { x1: G.pipeOut.x, y1: G.pipeOut.y1, x2: G.pipeOut.x, y2: G.pipeOut.y2, class: "ix-pipe" }, h.pipes);
  h.pipeIn = el("line", { x1: G.pipeIn.x, y1: G.pipeIn.y1, x2: G.pipeIn.x, y2: G.pipeIn.y2, class: "ix-pipe" }, h.pipes);
  text(h.pipes, G.pipeOut.x - 8, 210, "stdin", { "text-anchor": "end", class: "ix-small" });
  text(h.pipes, G.pipeIn.x + 8, 210, "stdout", { class: "ix-small" });

  const skillOn = on.has("skill");
  h.skills = box(svg, G.skills, `ix-skills${skillOn ? "" : " is-absent"}${focus === "skill" ? " is-focus" : ""}`,
    "skills/", "practice-test-triage");
  text(h.skills, G.skills.x + 14, G.skills.y + 70,
    ctx.skillLoaded ? "description and body in context" : "description in context; body on disk",
    { class: "ix-small" });

  drawSubagent(svg, ctx, h, { on, focus, maxTokens });
  drawBar(svg, ctx, h, { focus, maxTokens, lensId });
  return h;
}

function drawSubagent(svg, ctx, h, { on, focus }) {
  const S = G.sub;
  const present = on.has("subagent");
  const open = ctx.subState === "open";
  h.sub = el("g", { class: `ix-sub${present ? "" : " is-absent"}${open ? " is-open" : ""}${focus === "subagent" ? " is-focus" : ""}` }, svg);
  el("rect", { x: S.x, y: S.y, width: S.w, height: S.h, rx: 12, class: "ix-box" }, h.sub);
  text(h.sub, S.x + 14, S.y + 26, "test-reviewer", { class: "ix-box-title" });
  text(h.sub, S.x + 14, S.y + 46,
    open ? "subagent: its own context window" : ctx.subState === "done" ? "finished: only its summary returned" : "subagent: waiting to be delegated to",
    { class: "label-muted" });
  // Tools: allowed versus locked, in text as well as style.
  const tools = [["Read", true], ["Grep", true], ["Glob", true], ["Edit", false], ["Write", false], ["Bash", false]];
  tools.forEach(([name, ok], i) => {
    const x = S.x + 14 + i * 50;
    const g = el("g", { class: `ix-chip${ok ? "" : " is-locked"}` }, h.sub);
    el("rect", { x, y: S.y + 58, width: 46, height: 20, rx: 6 }, g);
    text(g, x + 23, S.y + 72, name, { "text-anchor": "middle", class: "ix-small" });
  });
  text(h.sub, S.x + 14, S.y + 94, "Edit, Write, Bash: locked", { class: "ix-small" });
  // Its own context bar.
  h.subBar = el("g", {}, h.sub);
  if (open) {
    const scaleX = (S.w - 28) / Math.max(1, ctx.subTotal);
    let x = S.x + 14;
    for (const ev of ctx.sub) {
      const w = Math.max(2, ev.tokens * scaleX);
      const r = el("rect", { x, y: S.y + 104, width: Math.max(1, w - 1.5), height: 22, rx: 3,
        class: `ix-seg block role-${ev.role}` }, h.subBar);
      h.subSegs.set(ev.id, r);
      x += w;
    }
    text(h.subBar, S.x + 14, S.y + 140, `its context: ${tokens(ctx.subTotal)}`, { class: "ix-small" });
  }
}

function segMatches(seg, focus) {
  if (!focus) return false;
  if (seg.id === focus) return true;
  if (focus === "plugin") return MECHS.includes(seg.mechanism);
  return seg.mechanism === focus;
}

function drawBar(svg, ctx, h, { focus, maxTokens }) {
  const B = G.bar;
  const scaleX = B.w / maxTokens;
  text(svg, B.x, B.y - 14, ctx.started ? "Context the model receives" : "Context before the first request",
    { class: "ix-bar-title" });
  el("rect", { x: B.x, y: B.y, width: B.w, height: B.h, rx: 6, class: "ix-bar-track" }, svg);
  const segs = [...ctx.always.map((b) => ({ ...b, kind: "always" })),
    ...ctx.conv.map((e) => ({ ...e, kind: "conv" }))];
  const anyFocus = segs.some((s) => segMatches(s, focus));
  let x = B.x;
  let alwaysEnd = B.x;
  const g = el("g", { class: "ix-bar" }, svg);
  for (const s of segs) {
    const w = s.tokens * scaleX;
    const hit = segMatches(s, focus);
    const r = el("rect", {
      x, y: B.y, width: Math.max(1, w - 1.5), height: B.h, rx: 3,
      class: `ix-seg block role-${s.role}${hit ? " is-focus" : ""}${anyFocus && !hit ? " is-dim" : ""}`,
    }, g);
    const tip = el("title", {}, r);
    tip.textContent = `${s.label}: ${tokens(s.tokens)}`;
    if (w > 92) text(g, x + 6, B.y + 28, s.label.length * 6.6 < w - 10 ? s.label : `${fmt(s.tokens)}`, { class: "ix-seg-label" });
    h.segs.set(s.id, { node: r, x, w, seg: s });
    x += w;
    if (s.kind === "always") alwaysEnd = x;
  }
  // Brackets: what is paid on every request, and the conversation so far.
  const bracket = (x1, x2, label) => {
    if (x2 - x1 < 4) return;
    el("path", { d: `M${x1},${B.y + B.h + 6} v6 H${x2 - 1.5} v-6`, class: "ix-bracket" }, svg);
    text(svg, x1, B.y + B.h + 28, label, { class: "ix-small" });
  };
  bracket(B.x, alwaysEnd, `on every request: ${tokens(ctx.alwaysTotal)}`);
  if (ctx.convTotal) bracket(alwaysEnd, x, `conversation so far: ${tokens(ctx.convTotal)}`);

  // Callout for the focused block(s), below the brackets.
  const hits = segs.filter((s) => segMatches(s, focus));
  if (hits.length) {
    const first = h.segs.get(hits[0].id);
    const last = h.segs.get(hits[hits.length - 1].id);
    const cx = Math.min(Math.max((first.x + last.x + last.w) / 2, B.x + 120), B.x + B.w - 120);
    const total = hits.reduce((a, s) => a + s.tokens, 0);
    const owner = { mcp: "the MCP server", skill: "the skill", subagent: "the subagent", plugin: "the plugin" }[focus];
    const label = hits.length === 1 ? `${hits[0].label}: ${tokens(total)}`
      : `${hits.length} blocks from ${owner || "this mechanism"}: ${tokens(total)}`;
    el("line", { x1: (first.x + last.x + last.w) / 2, y1: B.y + B.h + 34, x2: cx, y2: B.y + B.h + 52, class: "ix-callout-line" }, svg);
    text(svg, cx, B.y + B.h + 70, label, { "text-anchor": "middle", class: "ix-callout" });
  }
  h.barEnd = x;
}

/* Effects ------------------------------------------------------------------------------ */

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function anim(node, keyframes, options = {}) {
  if (!node || prefersReducedMotion() || typeof node.animate !== "function") return Promise.resolve();
  return node.animate(keyframes, { duration: 700, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)", fill: "both", ...options })
    .finished.catch(() => {});
}

/** A dot travelling a pipe: out (harness to server) or in (server to harness). */
async function packet(h, dir, cls = "") {
  const line = dir === "out" ? G.pipeOut : G.pipeIn;
  const dot = el("circle", { cx: line.x, cy: line.y1, r: 7, class: `ix-packet ${cls}` }, h.svg);
  await anim(dot, [{ transform: "translate(0,0)", opacity: 0.2 }, { transform: `translate(0,${line.y2 - line.y1}px)`, opacity: 1 }],
    { duration: 520, fill: "none" });
  dot.remove();
}

const dropIn = (node, delay = 0) =>
  anim(node, [{ transform: "translateY(-46px)", opacity: 0 }, { transform: "translateY(0)", opacity: 1 }], { duration: 650, delay });

async function runEffect(effect, h, step, ctxs, data) {
  const focusIds = [...h.segs.values()].filter((s) => s.node.classList.contains("is-focus")).map((s) => s.node);
  switch (effect) {
    case "launch": {
      await anim(h.mcp, [{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "translateY(0)" }]);
      for (const p of [h.pipeOut, h.pipeIn]) {
        p.style.strokeDasharray = "64";
        anim(p, [{ strokeDashoffset: 64 }, { strokeDashoffset: 0 }], { duration: 500 });
      }
      return wait(prefersReducedMotion() ? 0 : 520);
    }
    case "packet":
    case "refuse": {
      for (const i of step.wire || []) {
        const w = data.measured.wire[i];
        const bad = effect === "refuse" && w.dir === "in";
        await packet(h, w.dir, bad ? "is-error" : "");
      }
      if (effect === "refuse") {
        await Promise.all(focusIds.map((n) => anim(n, [
          { transform: "translateX(0)" }, { transform: "translateX(-5px)" }, { transform: "translateX(5px)" },
          { transform: "translateX(-3px)" }, { transform: "translateX(0)" }], { duration: 420 })));
      }
      return Promise.all(focusIds.map((n, i) => dropIn(n, i * 80)));
    }
    case "drop-in":
      for (const i of step.wire || []) await packet(h, data.measured.wire[i].dir);
      return Promise.all(focusIds.map((n, i) => dropIn(n, i * 80)));
    case "unfold":
      return Promise.all(focusIds.map((n) => {
        n.style.transformBox = "fill-box";
        n.style.transformOrigin = "left center";
        return anim(n, [{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: 900 });
      }));
    case "condense": {
      // The full output arrives at full width, then shrinks into the two lines that enter.
      const t = data.measured.triage;
      const seg = [...h.segs.values()].find((s) => s.node.classList.contains("is-focus"));
      if (!seg) return undefined;
      const full = t.full_tokens / t.condensed_tokens * seg.w;
      const ghost = el("rect", { x: seg.x, y: G.bar.y - 70, width: full, height: 40, rx: 4, class: "ix-ghost" }, h.svg);
      const label = text(h.svg, seg.x + 8, G.bar.y - 45,
        `full test output: ${fmt(t.full_chars)} characters, ${tokens(t.full_tokens)}`, { class: "ix-small" });
      await anim(ghost, [{ opacity: 0 }, { opacity: 1 }], { duration: 350 });
      await wait(prefersReducedMotion() ? 0 : 500);
      ghost.style.transformBox = "fill-box";
      ghost.style.transformOrigin = "left top";
      await anim(ghost, [{ transform: "scale(1,1)" }, { transform: `scale(${seg.w / full},1.15) translateY(52px)`, opacity: 0.2 }], { duration: 900 });
      ghost.remove();
      label.remove();
      return dropIn(seg.node);
    }
    case "split":
      return anim(h.sub, [{ opacity: 0, transform: "translate(-120px,-60px) scale(0.6)" }, { opacity: 1, transform: "translate(0,0) scale(1)" }], { duration: 800 });
    case "sub-grow":
      return Promise.all([...h.subSegs.values()].map((n, i) => dropIn(n, i * 140)));
    case "collapse": {
      const seg = [...h.segs.values()].find((s) => s.seg.id === "summary");
      const ghost = el("rect", { x: G.sub.x, y: G.sub.y, width: G.sub.w, height: G.sub.h, rx: 12, class: "ix-ghost is-sub" }, h.svg);
      ghost.style.transformBox = "fill-box";
      ghost.style.transformOrigin = "left top";
      if (seg) {
        const sx = Math.max(0.02, seg.w / G.sub.w);
        const sy = G.bar.h / G.sub.h;
        await anim(ghost, [{ transform: "translate(0,0) scale(1,1)", opacity: 0.9 },
          { transform: `translate(${seg.x - G.sub.x}px,${G.bar.y - G.sub.y}px) scale(${sx},${sy})`, opacity: 0.6 }], { duration: 1000 });
      }
      ghost.remove();
      return seg ? dropIn(seg.node) : undefined;
    }
    case "unpack":
    case "fly":
      return pluginMotion(effect, h);
    case "hook-fire":
      return anim(h.hook, [{ opacity: 1 }, { opacity: 0.35 }, { opacity: 1 }, { opacity: 0.35 }, { opacity: 1 }], { duration: 1100 });
    case "toggle-off": {
      // Ghosts of what the plugin added fade out of the bar.
      const before = ctxs.full;
      const gone = before.always.filter((b) => MECHS.includes(b.mechanism));
      const scaleX = G.bar.w / h.maxTokens;
      let x = G.bar.x;
      const ghosts = [];
      for (const b of before.always) {
        const w = b.tokens * scaleX;
        if (gone.includes(b)) ghosts.push(el("rect", { x, y: G.bar.y, width: w - 1.5, height: G.bar.h, rx: 3, class: `ix-seg block role-${b.role}` }, h.svg));
        x += w;
      }
      await Promise.all(ghosts.map((n) => anim(n, [{ opacity: 1, transform: "translateY(0)" }, { opacity: 0, transform: "translateY(30px)" }], { duration: 900 })));
      ghosts.forEach((n) => n.remove());
      return undefined;
    }
    default:
      return undefined;
  }
}

/** The plugin's package opens, and its four parts travel to where they live. */
async function pluginMotion(effect, h, still = false) {
  const origin = { x: 470, y: 330 };
  const parts = [
    { label: "skill", to: h.skills, x: G.skills.x + 100, y: G.skills.y + 46 },
    { label: "subagent", to: h.sub, x: G.sub.x + 160, y: G.sub.y + 40 },
    { label: "hook", to: h.hook, x: G.hook.x + G.hook.w / 2, y: G.hook.y + 12 },
    { label: "MCP server", to: h.mcp, x: G.mcp.x + 125, y: G.mcp.y + 46 },
  ];
  const pkg = el("g", { class: "ix-package" }, h.svg);
  el("rect", { x: origin.x - 90, y: origin.y - 26, width: 180, height: 52, rx: 10 }, pkg);
  text(pkg, origin.x, origin.y + 5, "practice-toolkit", { "text-anchor": "middle", class: "ix-box-title" });
  const chips = parts.map((p, i) => {
    const g = el("g", { class: "ix-part" }, h.svg);
    const cx = origin.x - 135 + i * 90;
    el("rect", { x: cx - 40, y: origin.y + 36, width: 80, height: 24, rx: 8 }, g);
    text(g, cx, origin.y + 52, p.label, { "text-anchor": "middle", class: "ix-small" });
    return { g, cx, cy: origin.y + 48, p };
  });
  if (effect === "unpack") {
    if (still) return undefined; // drawn as part of the step's resting state
    await anim(pkg, [{ opacity: 0, transform: "scale(0.8)" }, { opacity: 1, transform: "scale(1)" }], { duration: 500 });
    await Promise.all(chips.map((c, i) => anim(c.g, [{ opacity: 0, transform: "translateY(-30px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 500, delay: i * 120 })));
    return undefined;
  }
  pkg.remove();
  await Promise.all(chips.map((c, i) => anim(c.g, [{ transform: "translate(0,0)", opacity: 1 },
    { transform: `translate(${c.p.x - c.cx}px,${c.p.y - c.cy}px)`, opacity: 0 }], { duration: 1000, delay: i * 150 })));
  chips.forEach((c) => c.g.remove());
  const hits = [...h.segs.values()].filter((s) => s.node.classList.contains("is-focus"));
  return Promise.all(hits.map((s, i) => dropIn(s.node, i * 120)));
}

/* Wire panel --------------------------------------------------------------------------- */

function renderWire(box, titleEl, step, data, focusEvent) {
  box.replaceChildren();
  const m = data.measured;
  const pre = (content, cls = "") => {
    const p = document.createElement("pre");
    p.className = `ix-wire-text ${cls}`;
    p.textContent = content;
    return p;
  };
  const caption = (content) => {
    const c = document.createElement("p");
    c.className = "ix-wire-caption";
    c.textContent = content;
    return c;
  };
  if (step.wire?.length) {
    titleEl.textContent = "On the wire (recorded)";
    for (const i of step.wire) {
      const w = m.wire[i];
      box.append(caption(w.dir === "out" ? `harness to server: ${w.method}` : `server to harness: reply to ${w.method}`),
        pre(w.line, w.dir === "in" && w.line.includes('"isError": true') ? "is-error" : ""));
    }
    return;
  }
  const effect = step.state.effect;
  if (effect === "condense") {
    titleEl.textContent = "What the script did";
    box.append(caption(`Full test output: ${fmt(m.triage.full_chars)} characters (not sent)`), pre(m.triage.full_text),
      caption(`What failures.py printed: ${fmt(m.triage.condensed_chars)} characters (sent)`), pre(m.triage.condensed_text));
    return;
  }
  if (effect === "unpack") {
    titleEl.textContent = ".claude-plugin/plugin.json";
    box.append(pre(m.plugin.manifest));
    return;
  }
  if (effect === "fly") {
    titleEl.textContent = "Where the parts register";
    box.append(caption("hooks/hooks.json"), pre(m.plugin.hooks_json), caption(".mcp.json"), pre(m.plugin.mcp_json));
    return;
  }
  if (effect === "hook-fire") {
    titleEl.textContent = "The hook, run on each edit (recorded)";
    for (const r of m.hook.runs) box.append(caption(`Edit ${r.file}: exit code ${r.exit_code}, allowed`));
    const b = m.hook.blocked_example;
    box.append(caption(`A weakening edit to ${b.file}: exit code ${b.exit_code}, blocked. The model would see:`), pre(b.stderr, "is-error"));
    return;
  }
  if (step.state.focus === "skill-listing" || (step.state.focus === "skill" && !focusEvent)) {
    titleEl.textContent = "In context on every request";
    box.append(pre(m.skill.listing));
    return;
  }
  if (step.state.focus === "agent-listing") {
    titleEl.textContent = "In context on every request";
    box.append(pre(m.subagent.listing));
    return;
  }
  if (effect === "split" || (step.state.focus === "subagent" && step.state.at === "summary")) {
    titleEl.textContent = "The subagent's system prompt (agents/test-reviewer.md)";
    box.append(pre(m.subagent.system_prompt));
    return;
  }
  if (focusEvent?.show) {
    titleEl.textContent = focusEvent.scripted ? `${focusEvent.label} (scripted)` : `${focusEvent.label} (recorded)`;
    box.append(pre(focusEvent.show));
    return;
  }
  titleEl.textContent = "";
}

/* Lenses ------------------------------------------------------------------------------- */

function lensOn(state) {
  return new Set(state.combo ?? MECHS);
}

function createLenses(data) {
  const els = {
    tabs: document.getElementById("lens-tabs"),
    panel: document.getElementById("lens-panel"),
    intro: document.getElementById("lens-intro"),
    scene: document.getElementById("lens-scene"),
    status: document.getElementById("lens-status"),
    text: document.getElementById("lens-text"),
    progress: document.getElementById("lens-progress"),
    play: document.getElementById("lens-play"),
    back: document.getElementById("lens-back"),
    next: document.getElementById("lens-next"),
    restart: document.getElementById("lens-restart"),
    wire: document.getElementById("lens-wire"),
    wireTitle: document.getElementById("wire-title"),
    always: document.getElementById("meter-always"),
    conv: document.getElementById("meter-conv"),
    total: document.getElementById("meter-total"),
    sub: document.getElementById("meter-sub"),
    subLabel: document.getElementById("meter-sub-label"),
  };
  const session = data.session;
  const lenses = data.lenses;
  const eventById = new Map(session.events.map((e) => [e.id, e]));

  // One horizontal scale for every lens, so block widths are comparable.
  let maxTokens = 1;
  for (const lens of lenses) {
    for (const step of lens.steps) {
      const c = contextAt(session, step.state.at, lensOn(step.state));
      maxTokens = Math.max(maxTokens, c.alwaysTotal + c.convTotal);
    }
  }

  let lens = lenses[0];
  let index = 0;
  let playing = false;
  let runId = 0;
  let timer = 0;

  const tabs = lenses.map((l) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tab";
    b.id = `lens-tab-${l.id}`;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-controls", "lens-panel");
    b.textContent = l.label;
    b.addEventListener("click", () => select(l.id));
    b.addEventListener("keydown", (event) => {
      const d = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!d) return;
      event.preventDefault();
      const next = lenses[(lenses.indexOf(l) + d + lenses.length) % lenses.length];
      select(next.id);
      document.getElementById(`lens-tab-${next.id}`).focus();
    });
    return b;
  });
  els.tabs.replaceChildren(...tabs);

  function describe(step, ctx) {
    const parts = [`${lens.label} lens, step ${index + 1} of ${lens.steps.length}.`];
    parts.push(ctx.started
      ? `The model's context is ${tokens(ctx.alwaysTotal + ctx.convTotal)}: ${tokens(ctx.alwaysTotal)} on every request and ${tokens(ctx.convTotal)} of conversation.`
      : `Before the first request: ${tokens(ctx.alwaysTotal)} will be sent on every request.`);
    const on = lensOn(step.state);
    parts.push(`Enabled: ${MECHS.filter((m) => on.has(m)).map((m) => MECH_LABEL[m]).join(", ") || "none"}.`);
    if (ctx.subState === "open") parts.push(`The subagent's own context holds ${tokens(ctx.subTotal)}; the main context does not grow while it works.`);
    if (ctx.subState === "done") parts.push("The subagent has finished; only its summary is in the main context.");
    return parts.join(" ");
  }

  async function goTo(i, { animated = false } = {}) {
    clearTimeout(timer);
    index = Math.max(0, Math.min(lens.steps.length - 1, i));
    const myRun = ++runId;
    const step = lens.steps[index];
    const on = lensOn(step.state);
    const ctx = contextAt(session, step.state.at, on);
    const h = drawScene(els.scene, ctx, { focus: step.state.focus, on, maxTokens, lensId: lens.id });
    h.maxTokens = maxTokens;
    setSceneLabel(h.svg, describe(step, ctx));

    els.status.textContent = `${lens.label}: step ${index + 1} of ${lens.steps.length}`;
    els.text.textContent = fill(step.text, data);
    els.always.textContent = tokens(ctx.alwaysTotal);
    els.conv.textContent = tokens(ctx.convTotal);
    els.total.textContent = tokens(ctx.alwaysTotal + ctx.convTotal);
    const showSub = ctx.subState === "open";
    els.sub.hidden = !showSub;
    els.subLabel.hidden = !showSub;
    els.sub.textContent = tokens(ctx.subTotal);
    els.progress.style.width = `${((index + 1) / lens.steps.length) * 100}%`;
    els.back.disabled = index === 0;
    els.next.disabled = index === lens.steps.length - 1;
    renderWire(els.wire, els.wireTitle, step, data, eventById.get(step.state.focus));

    // The opened package is part of that step's resting state, so Back shows it too.
    if (!animated && step.state.effect === "unpack") pluginMotion("unpack", h, true);
    if (animated && step.state.effect !== "none") {
      const full = contextAt(session, step.state.at, new Set(MECHS));
      await runEffect(step.state.effect, h, step, { full }, data);
    }
    if (myRun !== runId || !playing) return;
    if (index < lens.steps.length - 1) {
      timer = setTimeout(() => { if (playing) goTo(index + 1, { animated: true }); }, prefersReducedMotion() ? 4200 : 3000);
    } else {
      setPlaying(false);
    }
  }

  function setPlaying(value) {
    playing = value;
    els.play.textContent = playing ? "Pause" : "Play";
    els.play.setAttribute("aria-pressed", String(playing));
    if (playing) {
      if (index >= lens.steps.length - 1) goTo(0, { animated: true });
      else goTo(index + 1, { animated: true });
    } else {
      clearTimeout(timer);
    }
  }

  function select(id) {
    lens = lenses.find((l) => l.id === id) || lenses[0];
    setPlaying(false);
    for (const b of tabs) {
      const selected = b.id === `lens-tab-${lens.id}`;
      b.setAttribute("aria-selected", String(selected));
      b.tabIndex = selected ? 0 : -1;
    }
    els.panel.setAttribute("aria-labelledby", `lens-tab-${lens.id}`);
    els.intro.textContent = lens.intro;
    goTo(0, { animated: true });
  }

  els.play.addEventListener("click", () => setPlaying(!playing));
  els.next.addEventListener("click", () => { setPlaying(false); goTo(index + 1, { animated: true }); });
  els.back.addEventListener("click", () => { setPlaying(false); goTo(index - 1); });
  els.restart.addEventListener("click", () => { setPlaying(false); goTo(0, { animated: true }); });

  els.panel.closest("section").addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    const onTab = event.target.getAttribute?.("role") === "tab";
    const onButton = event.target.tagName === "BUTTON";
    if (event.key === " " && !onButton) {
      event.preventDefault();
      setPlaying(!playing);
    } else if (event.key === "ArrowRight" && !onTab && index < lens.steps.length - 1) {
      event.preventDefault();
      setPlaying(false);
      goTo(index + 1, { animated: true });
    } else if (event.key === "ArrowLeft" && !onTab && index > 0) {
      event.preventDefault();
      setPlaying(false);
      goTo(index - 1);
    }
  });

  select(lenses[0].id);
}

function renderLegend(list, roles) {
  list.replaceChildren();
  for (const role of roles) {
    const li = document.createElement("li");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "14");
    svg.setAttribute("height", "14");
    svg.setAttribute("aria-hidden", "true");
    el("rect", { x: 1, y: 1, width: 12, height: 12, rx: 2, class: `ix-seg block role-${role}` }, svg);
    li.append(svg, ROLE_LABEL[role]);
    list.append(li);
  }
}

/* Cost ledger --------------------------------------------------------------------------- */

function createLedger(data) {
  const session = data.session;
  const els = {
    toggles: document.getElementById("ledger-toggles"),
    scale: document.getElementById("ledger-scale"),
    scaleOut: document.getElementById("ledger-scale-out"),
    scene: document.getElementById("ledger-scene"),
    summary: document.getElementById("ledger-summary"),
    breakeven: document.getElementById("ledger-breakeven"),
    requests: document.getElementById("ledger-requests"),
    total: document.getElementById("ledger-total"),
    delta: document.getElementById("ledger-delta"),
    final: document.getElementById("ledger-final"),
    sub: document.getElementById("ledger-sub"),
    partsTitle: document.getElementById("ledger-parts-title"),
    parts: document.getElementById("ledger-parts"),
  };
  const on = new Set(MECHS);
  let scale = 1;
  let selected = -1;
  const fullTokens = data.measured.triage.full_tokens;

  const buttons = {};
  const addToggle = (id, label) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "button";
    b.textContent = label;
    b.addEventListener("click", () => {
      if (id === "plugin") {
        const all = MECHS.every((m) => on.has(m));
        MECHS.forEach((m) => (all ? on.delete(m) : on.add(m)));
      } else if (on.has(id)) on.delete(id);
      else on.add(id);
      selected = -1;
      render();
    });
    buttons[id] = b;
    els.toggles.append(b);
  };
  MECHS.forEach((m) => addToggle(m, MECH_LABEL[m]));
  addToggle("plugin", "Plugin: all three, plus the hook");

  els.scale.addEventListener("input", () => {
    scale = Number(els.scale.value);
    render();
  });

  function breakEven() {
    const others = new Set([...on].filter((m) => m !== "skill"));
    const withSkill = new Set([...others, "skill"]);
    for (let k = 1; k <= 40; k += 1) {
      if (composeDetailed(session, withSkill, k).totalInput <= composeDetailed(session, others, k).totalInput) return k;
    }
    return null;
  }

  function render() {
    for (const m of MECHS) buttons[m].setAttribute("aria-pressed", String(on.has(m)));
    buttons.plugin.setAttribute("aria-pressed", String(MECHS.every((m) => on.has(m))));
    els.scaleOut.textContent = scale === 1
      ? `1x: the practice app as measured (full test output ${tokens(fullTokens)})`
      : `${scale}x the practice app: full test output about ${tokens(fullTokens * scale)}`;

    const d = composeDetailed(session, on, scale);
    const none = composeDetailed(session, new Set(), scale);
    // A fixed vertical scale for this suite size, so toggling never rescales the chart.
    let yMax = 1;
    for (let n = 0; n < 8; n += 1) {
      const combo = new Set(MECHS.filter((_, i) => n & (1 << i)));
      for (const r of composeDetailed(session, combo, scale).requests) yMax = Math.max(yMax, r.total);
    }
    if (selected < 0 || selected >= d.requests.length) selected = d.requests.length - 1;
    drawLedger(els.scene, d, yMax, selected, (i) => { selected = i; render(); });

    els.requests.textContent = String(d.requests.length);
    els.total.textContent = tokens(d.totalInput);
    const delta = d.totalInput - none.totalInput;
    els.delta.textContent = delta === 0 ? "the same" : `${delta > 0 ? "+" : "-"}${tokens(Math.abs(delta))}`;
    els.final.textContent = tokens(d.finalContext);
    els.sub.textContent = on.has("subagent") ? `${tokens(d.subInput)} over ${d.subRequests} requests` : "none";

    const names = { mcp: "the MCP server", skill: "the skill", subagent: "the subagent" };
    const list = MECHS.filter((m) => on.has(m)).map((m) => names[m]);
    const enabled = list.length > 2 ? [`${list.slice(0, -1).join(", ")}, and ${list[list.length - 1]}`]
      : list.length === 2 ? [`${list[0]} and ${list[1]}`] : list;
    const alwaysExt = d.requests[0]?.always.filter((b) => MECHS.includes(b.mechanism)).reduce((a, b) => a + b.tokens, 0) || 0;
    els.summary.textContent = enabled.length
      ? `With ${enabled[0]} enabled, every request carries ${tokens(alwaysExt)} of descriptions and tool definitions before any work happens.`
      : "No extensions: every request carries only the system prompt and the built-in tools.";
    const k = breakEven();
    els.breakeven.textContent = k === 1
      ? "At this setup, the skill already saves more than it costs at the measured test-suite size."
      : k
        ? `The skill pays for itself once the full test output is about ${k}x the practice app's (about ${tokens(fullTokens * k)}). ${scale >= k ? "At this size it saves tokens." : "At this size it still costs more than it saves."}`
        : "Within 40x the practice app, the skill never pays for itself in this setup.";

    const r = d.requests[selected];
    els.partsTitle.textContent = `Request ${selected + 1}: ${tokens(r.total)}`;
    els.parts.replaceChildren(...[...r.always, ...r.conv].map((p) => {
      const li = document.createElement("li");
      li.innerHTML = "";
      const name = document.createElement("span");
      name.textContent = p.label;
      const n = document.createElement("span");
      n.className = "mono";
      n.textContent = fmt(p.tokens);
      li.append(name, n);
      if (p.kind !== "conv" && r.always.includes(p)) li.classList.add("is-always");
      return li;
    }));
  }

  els.scene.closest("section").addEventListener("keydown", (event) => {
    if (event.target.tagName === "INPUT" || event.altKey || event.ctrlKey || event.metaKey) return;
    const n = composeDetailed(session, on, scale).requests.length;
    if (event.key === "ArrowLeft" && selected > 0) { event.preventDefault(); selected -= 1; render(); }
    if (event.key === "ArrowRight" && selected < n - 1) { event.preventDefault(); selected += 1; render(); }
  });

  render();
}

function drawLedger(container, d, yMax, selected, onSelect) {
  const LW = 1000;
  const LH = 380;
  const C = { x: 70, y: 30, w: 900, h: 290 };
  const svg = createScene(container, { width: LW, height: LH, label: "" });
  setSceneInteractive(svg);
  const y = (t) => C.y + C.h - (t / yMax) * C.h;
  el("line", { x1: C.x, y1: C.y + C.h, x2: C.x + C.w, y2: C.y + C.h, class: "axis" }, svg);
  for (const f of [0.5, 1]) {
    el("line", { x1: C.x, y1: y(yMax * f), x2: C.x + C.w, y2: y(yMax * f), class: "gridline" }, svg);
    text(svg, C.x - 8, y(yMax * f) + 4, fmt(yMax * f), { "text-anchor": "end", class: "label-muted mono" });
  }
  text(svg, C.x, C.y - 12, "Tokens in each request of the main conversation", { class: "label-muted" });
  text(svg, C.x + C.w / 2, LH - 14, "Request", { "text-anchor": "middle", class: "label-muted" });
  const slot = C.w / Math.max(d.requests.length, 1);
  const bw = Math.min(54, slot * 0.68);
  d.requests.forEach((r, i) => {
    const cx = C.x + slot * i + slot / 2;
    const g = el("g", { class: `chart-bar${i === selected ? " is-selected" : ""}`, role: "button", tabindex: "-1",
      "aria-label": `Request ${i + 1}: ${tokens(r.total)}, of which ${tokens(r.alwaysTotal)} on every request` }, svg);
    el("rect", { x: cx - slot / 2, y: C.y, width: slot, height: C.h, class: "hit" }, g);
    let base = 0;
    for (const b of r.always) {
      el("rect", { x: cx - bw / 2, y: y(base + b.tokens), width: bw, height: (b.tokens / yMax) * C.h,
        class: `ix-seg block role-${b.role}` }, g);
      base += b.tokens;
    }
    el("rect", { x: cx - bw / 2, y: y(base + r.convTotal), width: bw, height: (r.convTotal / yMax) * C.h, class: "ix-conv" }, g);
    text(g, cx, C.y + C.h + 16, String(i + 1), { "text-anchor": "middle", class: "label-muted mono" });
    g.addEventListener("click", () => onSelect(i));
  });
  setSceneLabel(svg, `Bar chart of ${d.requests.length} requests. Total input ${tokens(d.totalInput)}; the final request is ${tokens(d.finalContext)}. Request ${selected + 1} is selected.`);
}

/* Page ---------------------------------------------------------------------------------- */

async function main() {
  initPage();
  const data = await initSection("inside-extensions");
  if (!data) return;
  document.getElementById("task-text").textContent = data.task;
  document.getElementById("source-note").textContent = data.source_note;
  renderLegend(document.getElementById("lens-legend"), ["system", "tools", "user", "model", "result", "skill", "subagent"]);
  renderLegend(document.getElementById("ledger-legend"), ["system", "tools", "skill", "subagent"]);
  const conv = document.createElement("li");
  conv.innerHTML = '<svg width="14" height="14" aria-hidden="true"><rect x="1" y="1" width="12" height="12" rx="2" class="ix-conv"></rect></svg>';
  conv.append("Conversation so far");
  document.getElementById("ledger-legend").append(conv);
  createLenses(data);
  createLedger(data);
}

main();
