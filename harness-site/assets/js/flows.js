/* Shared player for the three scripted flows. The trace is rebuilt from
   settings; stepping backward never relies on undoing an animation. */
import { initPage, loadContent, resolveSiteLink, showLoadError } from "./common.js";
import { createScene, el, text, drawModel, drawComponent, prefersReducedMotion } from "./scene.js";
import { buildTrace } from "./flow-model.js";

const get = (id) => document.getElementById(id);
function make(tag, className, copy) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (copy !== undefined) node.textContent = copy;
  return node;
}

async function main() {
  initPage();
  const data = await loadContent("flows");
  get("flow-concept").textContent = data.concept;
  get("flow-disclaimer").textContent = data.source_note;
  let flow;
  let settings;
  let trace = [];
  let index = 0;
  let timer = null;
  let animation = null;
  let playing = false;
  const tabs = [];

  function pause() {
    playing = false;
    animation?.pause();
    clearTimeout(timer);
    timer = null;
    get("trace-play").textContent = "Play";
    get("trace-play").setAttribute("aria-pressed", "false");
  }

  function go(next, motion = false) {
    animation?.cancel();
    index = Math.max(0, Math.min(trace.length - 1, next));
    render(motion);
    if (index === trace.length - 1) pause();
  }

  function tick() {
    if (!playing) return;
    go(index + 1, true);
    if (playing) timer = setTimeout(tick, 5500);
  }

  function play() {
    if (playing) { pause(); return; }
    if (index === trace.length - 1) go(0);
    playing = true;
    get("trace-play").textContent = "Pause";
    get("trace-play").setAttribute("aria-pressed", "true");
    timer = setTimeout(tick, 5500);
  }

  function rebuild() {
    pause();
    trace = buildTrace(flow.id, settings);
    get("trace-chapters").replaceChildren();
    trace.forEach((event, i) => {
      const item = make("li");
      const button = make("button", "chapter", `${i + 1}. ${flow.nodes.find((n) => n.id === event.node).label}`);
      button.type = "button";
      button.addEventListener("click", () => { pause(); go(i, true); });
      item.append(button);
      get("trace-chapters").append(item);
    });
    go(0);
  }

  function controls() {
    const root = get("flow-settings");
    root.replaceChildren();
    flow.defaults.forEach((control) => {
      const field = make("div", "flow-field");
      const id = `setting-${flow.id}-${control.id}`;
      const label = make("label", "", control.label);
      label.htmlFor = id;
      const input = make(control.options ? "select" : "input");
      input.id = id;
      input.dataset.setting = control.id;
      if (control.options) {
        control.options.forEach((option) => {
          const node = make("option", "", option.label);
          node.value = option.value;
          input.append(node);
        });
        input.value = settings[control.id];
        field.append(label, input);
      } else {
        input.type = "checkbox";
        input.checked = settings[control.id];
        field.classList.add("flow-check");
        field.append(input, label);
      }
      input.addEventListener("change", () => {
        settings[control.id] = control.options ? input.value : input.checked;
        rebuild();
      });
      root.append(field);
    });
  }

  function selectFlow(id, updateHash = true) {
    pause();
    flow = data.flows.find((f) => f.id === id) || data.flows[0];
    settings = Object.fromEntries(flow.defaults.map((c) => [c.id, c.default]));
    tabs.forEach((tab) => {
      const selected = tab.dataset.flow === flow.id;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    get("flow-panel").setAttribute("aria-labelledby", `tab-${flow.id}`);
    get("flow-intro").textContent = flow.intro;
    get("flow-principle").textContent = flow.concept;
    get("flow-prediction").textContent = flow.predict;
    get("flow-source").textContent = flow.source_note;
    get("flow-module").href = resolveSiteLink(flow.module_link);
    get("flow-module").textContent = `Go deeper: ${flow.label}`;
    get("flow-retention").hidden = flow.id !== "network";
    controls();
    rebuild();
    if (updateHash) history.replaceState(null, "", `#${flow.id}`);
  }

  function draw(motion) {
    const current = trace[index];
    const message = flow.messages[current.key];
    const svg = createScene(get("trace-scene"), { width: 1020, height: 420, label: `${flow.label}. Step ${index + 1} of ${trace.length}: ${message.title}` });
    const arrowId = `flow-arrow-${svg.dataset.hatch}`;
    const marker = el("marker", { id: arrowId, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" }, svg.querySelector("defs"));
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "flow-arrow" }, marker);
    const points = Object.fromEntries(flow.nodes.map((n) => [n.id, n]));
    const visited = new Set(trace.slice(0, index + 1).map((event) => event.node));
    // In the network lens edges branch from their true data source. Other
    // lenses show the decision route in timeline order.
    for (let i = 1; i <= index; i += 1) {
      const event = trace[i];
      const fromId = flow.id === "network" ? event.from : trace[i - 1].node;
      if (!fromId || fromId === event.node || event.disabled) continue;
      const a = points[fromId];
      const b = points[event.node];
      const horizontal = Math.abs(b.x - a.x) > Math.abs(b.y - a.y);
      const dx = horizontal ? Math.sign(b.x - a.x) * 83 : 0;
      const dy = horizontal ? 0 : Math.sign(b.y - a.y) * 35;
      const x1 = a.x + dx, y1 = a.y + dy;
      const x2 = b.x - dx, y2 = b.y - dy;
      const d = `M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`;
      el("path", { d, class: `flow-trace-edge${event.blocked ? " is-blocked" : ""}`, "marker-end": `url(#${arrowId})` }, svg);
      // A static endpoint makes direction visible even with motion reduced.
      const dot = el("circle", { cx: x2, cy: y2, r: 4, class: "flow-arrival" }, svg);
      if (motion && i === index && !prefersReducedMotion()) {
        // Offset paths let the packet follow the same curve without moving
        // any node or changing the completed diagram state.
        dot.setAttribute("cx", "0");
        dot.setAttribute("cy", "0");
        dot.style.offsetPath = `path('${d}')`;
        dot.style.offsetDistance = "100%";
        animation = dot.animate([{ offsetDistance: "0%" }, { offsetDistance: "100%" }], { duration: 850, fill: "forwards", easing: "ease-out" });
      }
    }
    for (const node of flow.nodes) {
      const active = node.id === current.node;
      const group = node.kind === "model"
        ? drawModel(svg, { cx: node.x, cy: node.y, w: 162, h: 68, label: node.label, sublabel: "" })
        : drawComponent(svg, { cx: node.x, cy: node.y, w: 164, h: 64, label: node.label, id: node.id });
      group.classList.add("flow-trace-node");
      if (active) group.classList.add("is-active");
      if (!visited.has(node.id)) group.classList.add("is-pending");
      const events = trace.slice(0, index + 1).filter((event) => event.node === node.id);
      let status = visited.has(node.id) ? data.ui.status.visited : data.ui.status.pending;
      if (events.some((event) => event.retain)) status = data.ui.status.retained;
      if (flow.id === "network" && node.id === "public" && events.length) {
        const attempts = events.filter((event) => !event.disabled);
        status = !attempts.length ? data.ui.status.disabled
          : attempts.every((event) => event.blocked) ? data.ui.status.blocked : data.ui.status.sent;
      }
      text(svg, node.x, node.y + 53, active ? data.ui.status.active : status,
        { "text-anchor": "middle", class: "label-muted flow-node-status" });
    }
  }

  function render(motion = false) {
    const event = trace[index];
    const message = flow.messages[event.key];
    get("trace-status").textContent = `${data.ui.step} ${index + 1} / ${trace.length}`;
    get("trace-title").textContent = message.title;
    get("trace-copy").textContent = message.text;
    get("trace-evidence").textContent = message.evidence;
    get("trace-evidence").hidden = !message.evidence;
    get("trace-back").disabled = index === 0;
    get("trace-next").disabled = index === trace.length - 1;
    get("trace-progress").style.width = `${(index + 1) / trace.length * 100}%`;
    [...get("trace-chapters").querySelectorAll("button")].forEach((b, i) => {
      if (i === index) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
    });
    const retained = trace.slice(0, index + 1).filter((e) => e.retain).map((e) => flow.nodes.find((n) => n.id === e.node).label);
    get("flow-copies").textContent = retained.length ? retained.join(" · ") : data.ui.none;
    get("flow-request").hidden = flow.id !== "permissions";
    get("flow-request").textContent = data.ui.request_labels[settings.request] || "";
    draw(motion);
  }

  data.flows.forEach((item, i) => {
    const tab = make("button", "tab", item.label);
    tab.id = `tab-${item.id}`;
    tab.type = "button";
    tab.dataset.flow = item.id;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", "flow-panel");
    tab.addEventListener("click", () => selectFlow(item.id));
    tab.addEventListener("keydown", (event) => {
      const delta = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!delta && !["Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (i + delta + tabs.length) % tabs.length;
      selectFlow(data.flows[next].id);
      tabs[next].focus();
    });
    tabs.push(tab);
    get("flow-tabs").append(tab);
  });

  get("trace-play").addEventListener("click", play);
  get("trace-back").addEventListener("click", () => { pause(); go(index - 1); });
  get("trace-next").addEventListener("click", () => { pause(); go(index + 1, true); });
  get("trace-restart").addEventListener("click", () => { pause(); go(0); });
  get("flow-reset").addEventListener("click", () => selectFlow(flow.id));
  get("flow-player").addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.target.closest("input, select, textarea")) return;
    if (event.key === " " && !event.target.closest("button, a")) { event.preventDefault(); play(); }
    const delta = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
    if (delta) { event.preventDefault(); pause(); go(index + delta, delta > 0); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
  window.addEventListener("hashchange", () => selectFlow(location.hash.slice(1), false));
  selectFlow(location.hash.slice(1), false);
}

main().catch(showLoadError);
