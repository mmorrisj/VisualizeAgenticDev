/*
  tokens.js: the token growth section.

  1. Two sessions (measured): a focused question and a broad request.
     Each request is a bar; the pile beside it is the session's total
     input, the sum of every request. Side by side, the broad pile towers
     over the focused one while their final requests are close in size.
     A single session can also be shown alone, with the running total as
     a line.
  2. Caching (the course's illustrative log): each request split into the
     part read from cache and the part processed fresh, with the one
     request where an idle gap broke the cache.
*/

import { initPage, initSection } from "./common.js";
import { el, text, createScene, setSceneLabel, prefersReducedMotion, animate } from "./scene.js";

const fmt = (n) => Math.round(n).toLocaleString("en-US");
const sum = (xs) => xs.reduce((a, b) => a + b, 0);

/** Round up to 1, 2, 2.5, or 5 times a power of ten, for readable axes. */
function niceMax(value) {
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) if (step * power >= value) return step * power;
  return 10 * power;
}

function stats(session) {
  const sizes = session.requests.map((r) => r.tokens);
  const total = sum(sizes);
  const final = sizes[sizes.length - 1];
  return { total, final, ratio: total / final, count: sizes.length };
}

/* Shared chart pieces --------------------------------------------------------- */

function yAxis(g, { x, y, h, max, label, side = "left" }) {
  const anchor = side === "left" ? "end" : "start";
  const dx = side === "left" ? -8 : 8;
  for (const t of [0, 0.5, 1]) {
    const yy = y + h - t * h;
    text(g, x + dx, yy + 4, fmt(max * t), { "text-anchor": anchor, class: "label-muted mono" });
  }
  text(g, x, y - 14, label, { "text-anchor": side === "left" ? "start" : "end", class: "label-muted" });
}

function gridlines(g, { x, y, w, h }) {
  for (const t of [0, 0.5, 1]) {
    const yy = y + h - t * h;
    el("line", { class: t === 0 ? "axis" : "gridline", x1: x, y1: yy, x2: x + w, y2: yy }, g);
  }
}

/** One bar per request. Returns the bar elements for animation. */
function drawRequestBars(g, session, { x, y, w, h, max, upTo }) {
  const slot = w / session.requests.length;
  const barW = Math.min(30, slot * 0.68);
  const bars = [];
  session.requests.forEach((r, i) => {
    const cx = x + slot * i + slot / 2;
    if (session.requests.length <= 15 || (i + 1) % 5 === 0 || i === 0) {
      text(g, cx, y + h + 16, String(r.n), { "text-anchor": "middle", class: "label-muted mono" });
    }
    if (i >= upTo) return;
    const bh = (r.tokens / max) * h;
    const bar = el("rect", {
      class: "token-bar", x: cx - barW / 2, y: y + h - bh, width: barW, height: bh, rx: 2,
      "aria-label": `Request ${r.n}: ${fmt(r.tokens)} input tokens`,
    }, g);
    const tip = el("title", {}, bar);
    tip.textContent = `Request ${r.n}: ${fmt(r.tokens)} tokens. Then: ${r.call}${r.compacted ? ". Compacted before this request." : ""}`;
    if (r.compacted) {
      el("path", { class: "compaction-mark", d: `M ${cx - 5} ${y + h - bh - 12} L ${cx + 5} ${y + h - bh - 12} L ${cx} ${y + h - bh - 5} Z` }, g);
    }
    bars.push(bar);
  });
  text(g, x + w / 2, y + h + 34, "Request", { "text-anchor": "middle", class: "label-muted" });
  return bars;
}

/**
 * The pile: every request's input stacked into one column, oldest at the
 * bottom. Its height is the session's total input.
 */
function drawPile(g, session, { x, y, w, h, max, upTo }) {
  let base = 0;
  const blocks = [];
  session.requests.forEach((r, i) => {
    if (i >= upTo) return;
    const bh = (r.tokens / max) * h;
    const block = el("rect", {
      class: `pile-block${i % 2 ? " is-alt" : ""}`, x, y: y + h - ((base + r.tokens) / max) * h, width: w, height: Math.max(0.5, bh - 1),
    }, g);
    const tip = el("title", {}, block);
    tip.textContent = `Request ${r.n} adds ${fmt(r.tokens)} tokens`;
    base += r.tokens;
    blocks.push(block);
  });
  if (upTo > 0) {
    text(g, x + w / 2, y + h - (base / max) * h - 10, fmt(base), { "text-anchor": "middle", class: "mono label-strong" });
  }
  return blocks;
}

/* 1. Two sessions ------------------------------------------------------------------ */

function createCompare(compare) {
  const sessions = compare.sessions;
  const box = document.getElementById("compare-scene");
  const modeBox = document.getElementById("compare-mode");
  const playButton = document.getElementById("compare-play");
  const readouts = document.getElementById("compare-readouts");

  // Shared scales, so the two sessions can be compared by eye.
  const barMax = niceMax(Math.max(...sessions.flatMap((s) => s.requests.map((r) => r.tokens))));
  const pileMax = niceMax(Math.max(...sessions.map((s) => stats(s).total)));
  const longest = Math.max(...sessions.map((s) => s.requests.length));

  let mode = "both";
  let upTo = longest;
  let timer = 0;

  const modes = [["focused", sessions[0].label], ["broad", sessions[1].label], ["both", "Side by side"]];
  for (const [id, label] of modes) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "button";
    b.textContent = label;
    b.dataset.mode = id;
    b.addEventListener("click", () => { stop(); mode = id; upTo = longest; render(); });
    modeBox.append(b);
  }

  function render({ newest = false } = {}) {
    modeBox.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
    document.getElementById("legend-pile").hidden = mode !== "both";
    document.getElementById("legend-line").hidden = mode === "both";
    const shown = mode === "both" ? sessions : sessions.filter((s) => s.id === mode);
    const svg = createScene(box, { width: 1200, height: 430, label: "" });

    const drawn = [];
    if (mode === "both") {
      shown.forEach((s, k) => {
        const ox = 70 + k * 590;
        const g = el("g", {}, svg);
        text(g, ox, 26, `${s.label}: "${s.prompt}"`, { class: "label-strong" });
        const area = { x: ox, y: 70, w: 340, h: 290 };
        gridlines(g, area);
        yAxis(g, { ...area, max: barMax, label: "Input per request" });
        const bars = drawRequestBars(g, s, { ...area, max: barMax, upTo });
        const pileArea = { x: ox + 400, y: 70, w: 70, h: 290 };
        el("line", { class: "axis", x1: pileArea.x - 10, y1: pileArea.y + pileArea.h, x2: pileArea.x + pileArea.w + 10, y2: pileArea.y + pileArea.h }, g);
        text(g, pileArea.x + pileArea.w / 2, pileArea.y + pileArea.h + 16, "Total input", { "text-anchor": "middle", class: "label-muted" });
        // Both piles share one scale; one axis, on the right, labels it.
        if (k === shown.length - 1) yAxis(g, { x: pileArea.x + pileArea.w + 10, y: pileArea.y, h: pileArea.h, max: pileMax, label: "", side: "right" });
        const blocks = drawPile(g, s, { ...pileArea, max: pileMax, upTo });
        drawn.push({ bars, blocks });
      });
    } else {
      const s = shown[0];
      const g = el("g", {}, svg);
      text(g, 70, 26, `${s.label}: "${s.prompt}"`, { class: "label-strong" });
      const area = { x: 70, y: 70, w: 1040, h: 290 };
      gridlines(g, area);
      yAxis(g, { ...area, max: barMax, label: "Input per request (bars)" });
      const bars = drawRequestBars(g, s, { ...area, max: barMax, upTo });
      // Running total on its own axis, on the right.
      yAxis(g, { x: area.x + area.w, y: area.y, h: area.h, max: pileMax, label: "Running total (line)", side: "right" });
      const slot = area.w / s.requests.length;
      let running = 0;
      const pts = s.requests.slice(0, upTo).map((r, i) => {
        running += r.tokens;
        return [area.x + slot * i + slot / 2, area.y + area.h - (running / pileMax) * area.h];
      });
      if (pts.length) {
        el("path", { class: "running-line", d: `M ${pts.map((p) => p.join(" ")).join(" L ")}` }, g);
        pts.forEach(([px, py], i) => {
          const dot = el("circle", { class: "running-dot", cx: px, cy: py, r: 4 }, g);
          const tip = el("title", {}, dot);
          tip.textContent = `After request ${i + 1}: ${fmt(sum(s.requests.slice(0, i + 1).map((r) => r.tokens)))} tokens in total`;
        });
      }
      drawn.push({ bars, blocks: [] });
    }

    // While playing, the newest bar grows and its block drops onto the pile.
    if (newest && !prefersReducedMotion()) {
      for (const { bars, blocks } of drawn) {
        const bar = bars[upTo - 1];
        const block = blocks[upTo - 1];
        if (bar) {
          bar.style.transformBox = "fill-box";
          bar.style.transformOrigin = "bottom";
          animate(bar, [{ transform: "scaleY(0)" }, { transform: "scaleY(1)" }], { duration: 260 });
        }
        if (block) animate(block, [{ transform: "translateY(-60px)", opacity: 0 }, { transform: "translateY(0)", opacity: 1 }], { duration: 320 });
      }
    }

    // Readouts and the text summary for screen readers.
    readouts.replaceChildren();
    const summary = [];
    for (const s of shown) {
      const st = stats(s);
      const card = document.createElement("div");
      card.className = "panel readout-card";
      const h = document.createElement("h3");
      h.textContent = s.label;
      const dl = document.createElement("dl");
      dl.className = "readouts";
      for (const [k, v] of [["Requests", String(st.count)], ["Final context", `${fmt(st.final)} tokens`],
        ["Total input", `${fmt(st.total)} tokens`], ["Total input / final context", `${st.ratio.toFixed(1)}x`]]) {
        const dt = document.createElement("dt"); dt.textContent = k;
        const dd = document.createElement("dd"); dd.textContent = v;
        dl.append(dt, dd);
      }
      card.append(h, dl);
      readouts.append(card);
      summary.push(`${s.label}: ${st.count} requests, sizes ${s.requests.map((r) => fmt(r.tokens)).join(", ")}. `
        + `Final context ${fmt(st.final)} tokens, total input ${fmt(st.total)} tokens, ${st.ratio.toFixed(1)} times the final context.`);
    }
    setSceneLabel(svg, summary.join(" "));
  }

  function stop() {
    window.clearTimeout(timer);
    timer = 0;
    playButton.textContent = "Play";
  }

  function tick() {
    if (upTo >= (mode === "both" ? longest : sessions.find((s) => s.id === mode).requests.length)) { stop(); return; }
    upTo += 1;
    render({ newest: true });
    timer = window.setTimeout(tick, 420);
  }

  playButton.addEventListener("click", () => {
    if (timer) { stop(); return; }
    upTo = 0;
    render();
    playButton.textContent = "Pause";
    timer = window.setTimeout(tick, 300);
  });

  render();
}

/* 2. Caching ------------------------------------------------------------------------ */

function createCaching(caching) {
  const box = document.getElementById("cache-scene");
  const toggle = document.getElementById("cache-toggle");
  const note = document.getElementById("cache-note");
  const share = document.getElementById("cache-share");
  const reqs = caching.requests;
  const miss = reqs.find((r, i) => i > 0 && r.cached === 0);
  let showCache = true;

  function render() {
    toggle.setAttribute("aria-pressed", String(showCache));
    toggle.textContent = showCache ? "Hide caching" : "Show caching";
    const svg = createScene(box, { width: 1200, height: 380, label: "" });
    const area = { x: 80, y: 50, w: 1060, h: 270 };
    const max = niceMax(Math.max(...reqs.map((r) => r.tokens)));
    const g = el("g", {}, svg);
    gridlines(g, area);
    yAxis(g, { ...area, max, label: "Input per request" });
    const slot = area.w / reqs.length;
    const barW = Math.min(46, slot * 0.6);

    reqs.forEach((r, i) => {
      const cx = area.x + slot * i + slot / 2;
      const fresh = r.tokens - r.cached;
      const yTop = area.y + area.h - (r.tokens / max) * area.h;
      text(g, cx, area.y + area.h + 16, String(r.n), { "text-anchor": "middle", class: "label-muted mono" });
      const label = `Request ${r.n}: ${fmt(r.tokens)} tokens, ${fmt(r.cached)} read from cache, ${fmt(fresh)} processed fresh`;
      const grp = el("g", { "aria-label": label }, g);
      const tip = el("title", {}, grp);
      tip.textContent = r === miss
        ? `${label}. Cache miss: ${caching.miss_note.replace("{n}", r.n).replace("{tokens}", fmt(r.tokens))}`
        : label;
      if (showCache) {
        // Cached part below (dimmed, dashed edge), fresh part on top (solid).
        const ch = (r.cached / max) * area.h;
        const fh = (fresh / max) * area.h;
        if (ch > 0) el("rect", { class: "token-bar is-cached", x: cx - barW / 2, y: area.y + area.h - ch, width: barW, height: ch }, grp);
        el("rect", { class: `token-bar${r === miss ? " is-miss" : ""}`, x: cx - barW / 2, y: yTop, width: barW, height: Math.max(1, fh) }, grp);
      } else {
        el("rect", { class: "token-bar", x: cx - barW / 2, y: yTop, width: barW, height: (r.tokens / max) * area.h }, grp);
      }
    });
    text(g, area.x + area.w / 2, area.y + area.h + 34, "Request", { "text-anchor": "middle", class: "label-muted" });

    // Call out the cache miss.
    if (showCache && miss) {
      const i = reqs.indexOf(miss);
      const cx = area.x + slot * i + slot / 2;
      const yTop = area.y + area.h - (miss.tokens / max) * area.h;
      el("line", { class: "callout-line", x1: cx, y1: yTop - 4, x2: cx, y2: area.y - 18 }, g);
      text(g, cx + 8, area.y - 22, `Request ${miss.n}: idle ${Math.round(miss.gap_seconds / 60)} minutes, cache expired, all ${fmt(miss.tokens)} tokens processed fresh`, { class: "callout-text" });
    }

    const totalIn = sum(reqs.map((r) => r.tokens));
    const totalCached = sum(reqs.map((r) => r.cached));
    share.textContent = `${Math.round((100 * totalCached) / totalIn)}% of this session's ${fmt(totalIn)} input tokens were read from cache.`;
    note.textContent = miss ? caching.miss_note.replace("{n}", miss.n).replace("{tokens}", fmt(miss.tokens)) : "";
    setSceneLabel(svg, `Cached session, ${reqs.length} requests. ${share.textContent} `
      + (miss ? `Cache miss at request ${miss.n}: ${fmt(miss.tokens)} tokens processed fresh after a ${Math.round(miss.gap_seconds / 60)}-minute idle gap.` : ""));
  }

  toggle.addEventListener("click", () => { showCache = !showCache; render(); });
  render();
}

/* Page ---------------------------------------------------------------------------------- */

async function main() {
  initPage();
  const content = await initSection("tokens");
  if (!content) return;
  for (const [id, part] of [["compare", content.compare], ["cache", content.caching]]) {
    document.getElementById(`${id}-title`).textContent = part.title;
    document.getElementById(`${id}-intro`).textContent = part.intro;
  }
  document.getElementById("source-note").textContent = content.source_note;
  createCompare(content.compare);
  createCaching(content.caching);
}

main();
