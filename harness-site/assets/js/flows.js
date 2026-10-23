/* Shared player for the three scripted flows. The trace is rebuilt from
   settings; stepping backward never relies on undoing an animation. */
import { initPage, loadContent, resolveSiteLink, showLoadError } from "./common.js";
import { createFlowScene } from "./flow-scene.js";
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
  let scene = null;
  let overview = true;
  let experimentIndex = 0;
  let previous = null;
  let playing = false;
  const tabs = [];

  function playLabel() {
    get("trace-play").textContent = playing ? "Pause animation" : scene && !scene.finished ? "Resume animation" : "Replay animation";
    get("trace-play").setAttribute("aria-pressed", String(playing));
  }

  function pause() {
    playing = false;
    scene?.pause();
    if (flow?.messages[trace[index]?.key]) evidence();
    playLabel();
  }

  function go(next) {
    pause();
    overview = false;
    const target = Math.max(0, Math.min(trace.length - 1, next));
    scene.show(trace, settings, { animate: false, limit: target });
    index = target;
    evidence();
  }

  function play() {
    if (playing) { pause(); return; }
    playing = true;
    overview = false;
    scene.play(scene.finished);
    evidence();
    playLabel();
  }

  function ensureScene() {
    if (scene?.id === flow.id) return;
    scene?.dispose();
    scene = createFlowScene(get("trace-scene"), flow, data.ui, changeSetting, (step, progress, done) => {
      index = step;
      if (done) { playing = false; overview = true; }
      evidence();
      playLabel();
    });
    scene.setSpeed(Number(get("flow-speed").value));
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
    ensureScene();
    index = flowOutcome(flow.id, trace).event;
    playing = motion;
    playing = scene.show(trace, settings, { animate: motion });
    evidence();
    playLabel();
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

  function evidence() {
    const event = trace[index];
    const message = flow.messages[event.key];
    get("trace-status").textContent = playing ? "Flow in motion" : overview ? data.ui.live.state : `${data.ui.step} ${index + 1} / ${trace.length}`;
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
  get("trace-live").addEventListener("click", () => {
    pause(); overview = true; index = flowOutcome(flow.id, trace).event;
    scene.show(trace, settings, { animate: false }); evidence(); playLabel();
  });
  get("flow-playhead").addEventListener("input", (event) => {
    pause(); overview = false; scene.seek(Number(event.target.value) / 100);
  });
  get("flow-speed").addEventListener("change", (event) => scene.setSpeed(Number(event.target.value)));
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
