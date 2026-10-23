// Optional development check: node harness-site/tools/test_flows.mjs
// No npm install or browser required; does not participate in site runtime.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildTrace } from '../assets/js/flow-model.js';

const data = JSON.parse(readFileSync(new URL('../content/flows.json', import.meta.url)));
let cases = 0;
function combinations(controls, i = 0, settings = {}) {
  if (i === controls.length) return [settings];
  const control = controls[i];
  const values = control.options ? control.options.map((o) => o.value) : [false, true];
  return values.flatMap((value) => combinations(controls, i + 1, { ...settings, [control.id]: value }));
}
for (const flow of data.flows) {
  const nodeIds = new Set(flow.nodes.map((n) => n.id));
  for (const settings of combinations(flow.defaults)) {
    cases++;
    const trace = buildTrace(flow.id, settings);
    assert(trace.length > 1);
    for (const event of trace) {
      assert(nodeIds.has(event.node), `unknown node ${event.node}`);
      assert(flow.messages[event.key], `missing content ${flow.id}/${event.key}`);
      if (event.from) assert(nodeIds.has(event.from));
    }
    assert.deepEqual(trace, buildTrace(flow.id, settings), 'trace must be repeatable');
    const keys = trace.map((e) => e.key);
    const visits = (id) => trace.some((e) => e.node === id);
    if (flow.id === 'permissions') {
      assert.equal(trace.at(-1).node, 'return');
      assert.equal(visits('execution'), keys.includes('executed') || keys.includes('sandbox_block'));
      if (settings.hook && settings.request === 'edit') {
        assert(keys.includes('hook_block'));
        assert(!visits('deny') && !visits('approval') && !visits('execution'));
      } else if (settings.deny) {
        assert(keys.includes('deny_block'));
        assert(!visits('ask') && !visits('allow') && !visits('approval') && !visits('execution'));
      } else {
        assert.equal(visits('approval'), settings.ask || !settings.allow);
        assert.equal(visits('allow'), !settings.ask, 'ask must take precedence over allow');
        const permitted = !(settings.ask || !settings.allow) || settings.approve === 'yes';
        assert.equal(visits('execution'), permitted);
        if (permitted) {
          assert.equal(keys.includes('sandbox_block'), settings.request === 'network' && settings.sandbox);
          assert.equal(keys.includes('success_result'), !(settings.request === 'network' && settings.sandbox));
        } else assert(keys.includes('declined') && keys.includes('blocked_result'));
      }
    } else if (flow.id === 'verification') {
      assert(keys.includes('green'), 'both changes must expose the misleading green summary');
      const verdict = trace.find((e) => e.node === 'verdict').key;
      if (settings.change === 'fix' && settings.diff && settings.mutation) assert.equal(verdict, 'accept');
      else if (settings.change === 'weaken' && (settings.diff || settings.mutation)) assert.equal(verdict, 'reject');
      else assert.equal(verdict, 'incomplete', 'missing evidence must not imply acceptance');
      if (settings.mutation) assert(keys.includes(settings.change === 'fix' ? 'mutation_fix' : 'mutation_weaken'));
    } else {
      assert.equal(visits('gateway'), settings.internal);
      assert.equal(visits('endpoint'), settings.internal);
      const copies = new Set(trace.filter((e) => e.retain).map((e) => e.node));
      assert.equal(copies.has('gateway'), settings.internal && settings.gateway);
      assert.equal(copies.has('endpoint'), settings.internal && settings.endpoint);
      assert.equal(copies.has('transcript'), settings.transcript);
      assert.equal(copies.has('telemetry'), settings.telemetry);
      if (!settings.internal) assert(keys.includes(settings.egress ? 'public_model_blocked' : 'public_model_sent'));
      assert.equal(keys.includes('nonessential_off'), settings.nonessential);
      assert.equal(keys.includes('nonessential_blocked'), !settings.nonessential && settings.egress);
      assert.equal(keys.includes('nonessential_sent'), !settings.nonessential && !settings.egress);
      for (const event of trace) {
        if (event.retain) assert(!event.blocked && !event.disabled);
      }
    }
  }
}
console.log(`PASS: ${cases} flow configurations; precedence, evidence, routes, retention, message references, and repeatability.`);
