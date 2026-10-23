/* A persistent scene driven by one clock. Frames change geometry/opacity,
   never replace the SVG, nodes, controls, or connecting paths. */
import { createScene, el, text, drawModel, drawComponent, setSceneInteractive, prefersReducedMotion } from './scene.js';

export function createFlowScene(container, flow, ui, onToggle, onFrame) {
  const svg = createScene(container, { width: 1020, height: 420, label: flow.label });
  const defs = svg.querySelector('defs');
  const markerIds = [false, true].map(blocked => {
    const id = `flow-arrow-${svg.dataset.hatch}-${blocked}`;
    const marker = el('marker', { id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto' }, defs);
    el('path', { d: 'M 0 0 L 10 5 L 0 10 z', class: `flow-arrow${blocked ? ' is-blocked' : ''}` }, marker);
    return id;
  });
  const edgeLayer = el('g', { class: 'flow-edges' }, svg);
  const nodeLayer = el('g', {}, svg);
  const packetLayer = el('g', { 'aria-hidden': 'true' }, svg);
  const nodes = new Map();
  const edges = new Map();
  const points = Object.fromEntries(flow.nodes.map(n => [n.id, n]));
  let trace = [], schedule = [], arrivals = [], settings = {};
  let elapsed = 0, duration = 1, lastTime = null, frame = null, running = false, speed = 1;
  let lastIndex = -1;
  setSceneInteractive(svg);

  for (const node of flow.nodes) {
    const group = node.kind === 'model'
      ? drawModel(nodeLayer, { cx: node.x, cy: node.y, w: 162, h: 68, label: node.label, sublabel: '' })
      : drawComponent(nodeLayer, { cx: node.x, cy: node.y, w: 164, h: 64, label: node.label, id: node.id });
    group.classList.add('flow-trace-node');
    const status = text(nodeLayer, node.x, node.y + 53, '', { 'text-anchor': 'middle', class: 'label-muted flow-node-status' });
    const binding = flow.bindings[node.id];
    let state;
    if (binding) {
      group.classList.add('is-operable');
      group.dataset.control = binding;
      group.setAttribute('role', 'button');
      group.setAttribute('tabindex', '0');
      group.querySelectorAll('text').forEach(t => t.setAttribute('y', node.y - 5));
      group.append(document.createTextNode(' '));
      state = text(group, node.x, node.y + 19, '', { 'text-anchor': 'middle', class: 'flow-control-state' });
      const labels = [...group.querySelectorAll('text')];
      labels.forEach((t, i) => { t.id = `${svg.dataset.hatch}-${node.id}-${i}`; });
      group.setAttribute('aria-labelledby', labels.map(t => t.id).join(' '));
      const toggle = () => {
        const control = flow.defaults.find(c => c.id === binding);
        const values = control.options?.map(o => o.value);
        onToggle(binding, values ? values[(values.indexOf(settings[binding]) + 1) % values.length] : !settings[binding]);
      };
      group.addEventListener('click', toggle);
      group.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    }
    nodes.set(node.id, { group, status, state, binding });
  }

  function edgeFor(from, to, key, blocked) {
    const id = `${from}:${to}:${key}`;
    if (edges.has(id)) return edges.get(id);
    const a = points[from], b = points[to];
    const horizontal = Math.abs(b.x - a.x) > Math.abs(b.y - a.y);
    const dx = horizontal ? Math.sign(b.x - a.x) * 83 : 0;
    const dy = horizontal ? 0 : Math.sign(b.y - a.y) * 35;
    const x1 = a.x + dx, y1 = a.y + dy, x2 = b.x - dx, y2 = b.y - dy;
    const d = `M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2}, ${x2} ${(y1 + y2) / 2}, ${x2} ${y2}`;
    const group = el('g', { class: 'flow-route-segment', 'data-edge': id }, edgeLayer);
    el('path', { d, class: 'flow-track' }, group);
    const ink = el('path', { d, class: `flow-trace-edge${blocked ? ' is-blocked' : ''}`, 'marker-end': `url(#${markerIds[blocked ? 1 : 0]})` }, group);
    const maskId = `flow-mask-${svg.dataset.hatch}-${edges.size}`;
    const mask = el('mask', { id: maskId, maskUnits: 'userSpaceOnUse', x: 0, y: 0, width: 1020, height: 420, style: 'mask-type:alpha' }, defs);
    const reveal = el('path', { d, class: 'flow-reveal-mask' }, mask);
    const length = ink.getTotalLength();
    reveal.style.strokeDasharray = String(length);
    ink.setAttribute('mask', `url(#${maskId})`);
    const packet = el('g', { class: `flow-packet${blocked ? ' is-blocked' : ''}` }, packetLayer);
    el('circle', { r: 10, class: 'flow-packet-halo' }, packet);
    el('circle', { r: 4.5, class: 'flow-packet-core' }, packet);
    packet.style.opacity = '0';
    const edge = { id, from, to, group, ink, reveal, length, packet, progress: 0 };
    edges.set(id, edge);
    return edge;
  }

  function paint(notify = true) {
    const reached = new Map();
    let activeIndex = 0, latest = -1;
    arrivals.forEach((at, i) => {
      if (at <= elapsed) {
        reached.set(trace[i].node, { at, event: trace[i] });
        if (at >= latest) { latest = at; activeIndex = i; }
      }
    });
    for (const segment of schedule) {
      const fraction = Math.max(0, Math.min(1, (elapsed - segment.start) / segment.travel));
      const edge = segment.edge;
      edge.progress = fraction;
      edge.reveal.style.strokeDashoffset = String(edge.length * (1 - fraction));
      const point = edge.ink.getPointAtLength(edge.length * fraction);
      edge.packet.setAttribute('transform', `translate(${point.x} ${point.y})`);
      // Fade a packet into and out of its node; never teleport a visible dot.
      const opacity = fraction > 0 && fraction < 1
        ? Math.min(1, fraction * 12, (1 - fraction) * 12) : 0;
      edge.packet.style.opacity = String(opacity);
    }
    for (const [id, node] of nodes) {
      const visit = reached.get(id);
      node.group.classList.toggle('is-pending', !visit);
      node.group.classList.toggle('is-active', !!visit && elapsed - visit.at < 480 && elapsed < duration);
      node.group.classList.toggle('is-flow-blocked', !!visit && (visit.event.blocked || ['hook_block', 'deny_block', 'declined', 'sandbox_block'].includes(visit.event.key)));
      let label = !visit ? ui.status.pending : visit.event.retain ? ui.status.retained : ui.status.visited;
      if (id === 'public' && visit) label = visit.event.disabled ? ui.status.disabled : visit.event.blocked ? ui.status.blocked : ui.status.sent;
      if (visit && elapsed - visit.at < 480 && elapsed < duration) label = ui.status.active;
      if (node.status.textContent !== label) node.status.textContent = label;
    }
    if (notify && (activeIndex !== lastIndex || elapsed >= duration)) {
      lastIndex = activeIndex;
      svg.setAttribute('aria-label', `${flow.label}. ${flow.messages[trace[activeIndex].key].title}`);
      onFrame(activeIndex, elapsed / duration, elapsed >= duration);
    }
    // Progress is one stable control, independent of the narrative panels.
    const playhead = document.getElementById('flow-playhead');
    if (playhead && document.activeElement !== playhead) playhead.value = String(elapsed / duration * 100);
    const progress = document.getElementById('trace-progress');
    if (progress) progress.style.width = `${elapsed / duration * 100}%`;
  }

  function tick(now) {
    if (!running) return;
    if (lastTime !== null) elapsed = Math.min(duration, elapsed + (now - lastTime) * speed);
    lastTime = now;
    paint();
    if (elapsed < duration) frame = requestAnimationFrame(tick);
    else { running = false; frame = null; }
  }

  function pause() {
    running = false;
    cancelAnimationFrame(frame);
    frame = null;
    lastTime = null;
    // Leave the visible packet at its current position while paused.
  }

  function play(restart = false) {
    if (prefersReducedMotion()) { elapsed = duration; paint(); return; }
    if (restart || elapsed >= duration) elapsed = 0;
    running = true;
    lastTime = null;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(tick);
  }

  function show(nextTrace, nextSettings, { animate = true, limit = null, preserve = true } = {}) {
    const oldSchedule = schedule;
    const oldElapsed = elapsed;
    const oldDuration = duration;
    const oldCurrent = oldSchedule.find(s => oldElapsed >= s.start && oldElapsed < s.start + s.travel);
    pause();
    trace = nextTrace;
    settings = nextSettings;
    schedule = [];
    arrivals = [0];
    const nodeTimes = new Map([[trace[0].node, 0]]);
    let cursor = 0;
    for (let i = 1; i < trace.length; i++) {
      const event = trace[i];
      const from = flow.id === 'network' ? event.from : trace[i - 1].node;
      if (!from || from === event.node || event.disabled) { arrivals[i] = cursor + 220; continue; }
      const blocked = !!event.blocked || ['hook_block', 'deny_block', 'declined', 'sandbox_block'].includes(event.key);
      const edge = edgeFor(from, event.node, event.key, blocked);
      const start = (flow.id === 'network' ? nodeTimes.get(from) || 0 : cursor) + 160;
      const travel = Math.max(520, Math.min(1250, edge.length / 0.24));
      schedule.push({ edge, start, travel, index: i });
      arrivals[i] = start + travel;
      nodeTimes.set(event.node, arrivals[i]);
      cursor = Math.max(cursor, arrivals[i]);
    }
    duration = cursor + 500;
    const liveIds = new Set(schedule.map(s => s.edge.id));
    for (const edge of edges.values()) {
      const visible = liveIds.has(edge.id);
      edge.group.style.opacity = visible ? '1' : '0';
      if (!visible) edge.packet.style.opacity = '0';
    }
    for (const node of nodes.values()) if (node.binding) {
      const control = flow.defaults.find(c => c.id === node.binding);
      node.state.textContent = flow.control_states[node.binding]?.[String(settings[node.binding])] || control.options.find(o => o.value === settings[node.binding]).label;
      node.group.setAttribute('aria-description', `${control.label}. ${ui.live.toggle}`);
      if (!control.options) node.group.setAttribute('aria-pressed', String(settings[node.binding]));
    }
    elapsed = 0;
    if (!animate || prefersReducedMotion()) elapsed = limit === null ? duration : arrivals[limit];
    else if (preserve && oldSchedule.length) {
      // Keep a packet on a shared segment. If its branch disappeared, resume
      // from the first changed branch instead of clearing the entire scene.
      const same = oldCurrent && schedule.find(s => s.edge.from === oldCurrent.edge.from && s.edge.to === oldCurrent.edge.to);
      if (same) elapsed = same.start + (oldElapsed - oldCurrent.start) / oldCurrent.travel * same.travel;
      else {
        const changed = schedule.find(s => !oldSchedule.some(old => old.edge === s.edge));
        elapsed = changed ? changed.start : oldElapsed >= oldDuration ? duration : Math.min(oldElapsed, duration);
      }
    }
    lastIndex = -1;
    running = animate && !prefersReducedMotion() && elapsed < duration;
    paint();
    if (running) play();
    return running;
  }

  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const reduce = () => { if (media.matches) { pause(); elapsed = duration; paint(); } };
  media.addEventListener('change', reduce);
  return { id: flow.id, svg, show, pause, play,
    seek(fraction) { pause(); lastIndex = -1; elapsed = Math.max(0, Math.min(1, fraction)) * duration; paint(); },
    setSpeed(value) { speed = value; },
    get finished() { return elapsed >= duration; },
    dispose() { pause(); media.removeEventListener('change', reduce); },
  };
}
