/* Shared player for the three scripted flows. The trace is rebuilt from
   settings; stepping backward never relies on undoing an animation. */
import { initPage, loadContent, resolveSiteLink, showLoadError } from "./common.js";
import { createScene, el, text, drawModel, drawComponent, prefersReducedMotion, setSceneInteractive } from "./scene.js";
import { buildTrace, flowOutcome } from "./flow-model.js";

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
  let animations = [];
  let overview = true;
  let experimentIndex = 0;
  let previous = null;
  let playing = false;
  const tabs = [];

  function pause() {
    playing = false;
    animations.forEach((a) => a.pause());
    clearTimeout(timer);
    timer = null;
    get("trace-play").textContent = "Replay route";
    get("trace-play").setAttribute("aria-pressed", "false");
  }

  function go(next, motion = false) {
    animations.forEach((a) => a.cancel());
    animations = [];
    index = Math.max(0, Math.min(trace.length - 1, next));
    render(motion);
    if (index === trace.length - 1) {
      playing = false;
      clearTimeout(timer);
      get("trace-play").textContent = "Replay route";
      get("trace-play").setAttribute("aria-pressed", "false");
    }
  }

  function tick() {
    if (!playing) return;
    go(index + 1, true);
    if (playing) timer = setTimeout(tick, 750);
  }

  function play() {
    if (playing) { pause(); return; }
    const restart = overview || index === trace.length - 1;
    overview = false;
    if (restart) go(0);
    animations.forEach((a) => a.play());
    playing = true;
    get("trace-play").textContent = "Pause";
    get("trace-play").setAttribute("aria-pressed", "true");
    timer = setTimeout(tick, 750);
  }

  function rebuild(motion = false) {
    pause();
    trace = buildTrace(flow.id, settings);
    get("trace-chapters").replaceChildren();
    trace.forEach((event, i) => {
      const item = make("li");
      const button = make("button", "chapter", `${i + 1}. ${flow.nodes.find((n) => n.id === event.node).label}`);
      button.type = "button";
      button.addEventListener("click", () => { pause(); overview = false; go(i, true); });
      item.append(button);
      get("trace-chapters").append(item);
    });
    overview = true;
    go(flowOutcome(flow.id, trace).event, motion);
    comparison();
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
        changeSetting(control.id, control.options ? input.value : input.checked);
      });
      root.append(field);
    });
  }

  function outcomeCopy(outcome) {
    const title = flow.outcomes?.[outcome.key] || flow.messages[outcome.key].title;
    const copies = outcome.copies.map((id) => flow.nodes.find((n) => n.id === id).label);
    const evidence = flow.id === "network"
      ? `${data.ui.live.copies}: ${copies.length ? copies.join(" · ") : data.ui.live.none}. ${flow.messages[outcome.extraTraffic].evidence}`
      : flow.messages[outcome.key].evidence;
    return { title, evidence };
  }

  function comparison() {
    const root = get("flow-comparison");
    root.replaceChildren();
    const now = flowOutcome(flow.id, trace);
    const entries = previous ? [[data.ui.live.before, previous], [data.ui.live.after, now]] : [[data.ui.live.state, now]];
    for (const [label, outcome] of entries) {
      const card = make("div", "flow-outcome");
      const copy = outcomeCopy(outcome);
      card.append(make("p", "eyebrow", label), make("h3", "", copy.title), make("p", "mono", copy.evidence));
      root.append(card);
    }
    const note = previous ? JSON.stringify(previous) === JSON.stringify(now) ? data.ui.live.unchanged : data.ui.live.changed : data.ui.live.initial;
    root.append(make("p", "flow-delta", note));
  }

  function changeSetting(id, value) {
    previous = flowOutcome(flow.id, trace);
    settings[id] = value;
    // Keep the sidebar and the diagram as two views of the same state.
    const input = get("flow-settings").querySelector(`[data-setting="${id}"]`);
    if (input.type === "checkbox") input.checked = value;
    else input.value = value;
    rebuild(true);
  }

  function experiments() {
    const root = get("flow-experiments");
    root.replaceChildren();
    flow.experiments.forEach((experiment, i) => {
      const button = make("button", "flow-experiment", experiment.title);
      button.type = "button";
      button.setAttribute("aria-pressed", String(i === experimentIndex));
      button.addEventListener("click", () => {
        previous = flowOutcome(flow.id, trace);
        experimentIndex = i;
        settings = { ...experiment.settings };
        for (const [j, node] of [...root.children].entries()) node.setAttribute("aria-pressed", String(j === i));
        get("flow-brief").textContent = experiment.prompt;
        controls();
        rebuild(true);
      });
      root.append(button);
    });
    get("flow-brief").textContent = flow.experiments[experimentIndex].prompt;
  }

  function selectFlow(id, updateHash = true) {
    pause();
    flow = data.flows.find((f) => f.id === id) || data.flows[0];
    experimentIndex = 0;
    get("flow-inspection").open = false;
    settings = { ...flow.experiments[0].settings };
    previous = null;
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
    experiments();
    controls();
    rebuild(true);
    if (updateHash) history.replaceState(null, "", `#${flow.id}`);
  }

  function draw(motion) {
    const current = trace[index];
    const message = flow.messages[current.key];
    const svg = createScene(get("trace-scene"), { width: 1020, height: 420, label: `${flow.label}. Step ${index + 1} of ${trace.length}: ${message.title}` });
    const arrowId = `flow-arrow-${svg.dataset.hatch}`;
    const marker = el("marker", { id: arrowId, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" }, svg.querySelector("defs"));
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "flow-arrow" }, marker);
    const blockedArrowId = `${arrowId}-blocked`;
    const blockedMarker = el("marker", { id: blockedArrowId, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" }, svg.querySelector("defs"));
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "flow-arrow is-blocked" }, blockedMarker);
    const arrivals = new Map();
    let routeTime = 0;
    const points = Object.fromEntries(flow.nodes.map((n) => [n.id, n]));
    const limit = overview ? trace.length - 1 : index;
    const visited = new Set(trace.slice(0, limit + 1).map((event) => event.node));
    // In the network lens edges branch from their true data source. Other
    // lenses show the decision route in timeline order.
    for (let i = 1; i <= limit; i += 1) {
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
      const blocked = event.blocked || ["hook_block", "deny_block", "declined", "sandbox_block"].includes(event.key);
      const path = el("path", { d, class: `flow-trace-edge${blocked ? " is-blocked" : ""}`, "marker-end": `url(#${blocked ? blockedArrowId : arrowId})` }, svg);
      if (motion && (overview || i === index) && !prefersReducedMotion()) {
        const duration = overview ? 240 : 450;
        // Branches start when their source receives the request. This keeps
        // gateway -> model sequential while local copies can fork together.
        const delay = !overview ? 0 : flow.id === "network" ? (arrivals.get(fromId) || 0) : routeTime;
        arrivals.set(event.node, delay + duration);
        routeTime = delay + duration;
        // Reveal through an alpha mask so dashed denial paths keep their
        // pattern. Animating the actual path's dash array would erase it.
        const maskId = `reveal-${svg.dataset.hatch}-${i}`;
        const mask = el("mask", { id: maskId, maskUnits: "userSpaceOnUse", x: 0, y: 0, width: 1020, height: 420, style: "mask-type:alpha" }, svg.querySelector("defs"));
        const reveal = el("path", { d, class: "flow-reveal-mask" }, mask);
        const length = path.getTotalLength();
        reveal.style.strokeDasharray = String(length);
        path.setAttribute("mask", `url(#${maskId})`);
        animations.push(reveal.animate([{ strokeDashoffset: String(length) }, { strokeDashoffset: "0" }], { duration, delay, fill: "both", easing: "linear" }));
        const dot = el("circle", { cx: 0, cy: 0, r: 4, class: `flow-arrival${blocked ? " is-blocked" : ""}` }, svg);
        dot.style.offsetPath = `path('${d}')`;
        animations.push(dot.animate([
          { offsetDistance: "0%", opacity: 0 },
          { offsetDistance: "5%", opacity: 1, offset: 0.05 },
          { offsetDistance: "95%", opacity: 1, offset: 0.95 },
          { offsetDistance: "100%", opacity: 0 },
        ], { duration, delay, fill: "both", easing: "linear" }));
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
      const events = trace.slice(0, limit + 1).filter((event) => event.node === node.id);
      let status = visited.has(node.id) ? data.ui.status.visited : data.ui.status.pending;
      if (events.some((event) => event.retain)) status = data.ui.status.retained;
      if (flow.id === "network" && node.id === "public" && events.length) {
        const attempts = events.filter((event) => !event.disabled);
        status = !attempts.length ? data.ui.status.disabled
          : attempts.every((event) => event.blocked) ? data.ui.status.blocked : data.ui.status.sent;
      }
      const binding = flow.bindings[node.id];
      if (binding) {
        setSceneInteractive(svg);
        const control = flow.defaults.find((c) => c.id === binding);
        const state = flow.control_states[binding]?.[String(settings[binding])] || control.options.find((o) => o.value === settings[binding]).label;
        group.classList.add("is-operable");
        group.dataset.control = binding;
        group.setAttribute("role", "button");
        group.setAttribute("tabindex", "0");
        group.setAttribute("aria-description", `${control.label}. ${data.ui.live.toggle}`);
        if (!control.options) group.setAttribute("aria-pressed", String(settings[binding]));
        group.querySelectorAll("text").forEach((label) => label.setAttribute("y", node.y - 5));
        group.append(document.createTextNode(" "));
        text(group, node.x, node.y + 19, state, { "text-anchor": "middle", class: "flow-control-state" });
        const labels = [...group.querySelectorAll("text")];
        labels.forEach((label, i) => { label.id = `${svg.dataset.hatch}-${node.id}-${i}`; });
        group.setAttribute("aria-labelledby", labels.map((label) => label.id).join(" "));
        const toggle = () => {
          const values = control.options?.map((o) => o.value);
          const next = values ? values[(values.indexOf(settings[binding]) + 1) % values.length] : !settings[binding];
          changeSetting(binding, next);
          get("trace-scene").querySelector(`[data-control="${binding}"]`)?.focus({ preventScroll: true });
        };
        group.addEventListener("click", toggle);
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
        });
      }
      text(svg, node.x, node.y + 53, active ? data.ui.status.active : status,
        { "text-anchor": "middle", class: "label-muted flow-node-status" });
    }
  }

  function render(motion = false) {
    const event = trace[index];
    const message = flow.messages[event.key];
    get("trace-status").textContent = overview ? data.ui.live.state : `${data.ui.step} ${index + 1} / ${trace.length}`;
    get("trace-title").textContent = message.title;
    get("trace-copy").textContent = message.text;
    get("trace-evidence").textContent = message.evidence;
    get("trace-evidence").hidden = !message.evidence;
    get("trace-back").disabled = index === 0;
    get("trace-next").disabled = index === trace.length - 1;
    get("trace-progress").style.width = `${(overview ? 1 : (index + 1) / trace.length) * 100}%`;
    [...get("trace-chapters").querySelectorAll("button")].forEach((b, i) => {
      if (i === index) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
    });
    const retained = trace.slice(0, overview ? trace.length : index + 1).filter((e) => e.retain).map((e) => flow.nodes.find((n) => n.id === e.node).label);
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
  get("trace-back").addEventListener("click", () => { pause(); overview = false; go(index - 1); });
  get("trace-next").addEventListener("click", () => { pause(); overview = false; go(index + 1, true); });
  get("trace-restart").addEventListener("click", () => { pause(); overview = false; go(0); });
  get("trace-live").addEventListener("click", () => { pause(); overview = true; go(flowOutcome(flow.id, trace).event, true); });
  get("flow-reset").addEventListener("click", () => selectFlow(flow.id));
  get("flow-player").addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.target.closest("input, select, textarea")) return;
    if (event.key === " " && !event.target.closest("button, a")) { event.preventDefault(); play(); }
    const delta = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
    if (delta) { event.preventDefault(); pause(); overview = false; go(index + delta, delta > 0); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
  window.addEventListener("hashchange", () => selectFlow(location.hash.slice(1), false));
  selectFlow(location.hash.slice(1), false);
}

main().catch(showLoadError);
