/* Pure, deterministic traces. Every outcome is derived from the selected
   setup; the renderer never decides whether an action was allowed or fixed. */
export function permissionTrace(s) {
  const trace = [{ node: "request", key: "request" }];
  const add = (node, key) => trace.push({ node, key });
  const finish = (key) => { add("result", key); add("return", "return"); return trace; };
  if (s.request === "edit" && s.hook) {
    add("hook", "hook_block");
    return finish("blocked_result");
  }
  add("hook", "hook_pass");
  if (s.deny) {
    add("deny", "deny_block");
    return finish("blocked_result");
  }
  add("deny", "deny_pass");
  add("ask", s.ask ? "ask_match" : "ask_pass");
  if (!s.ask) add("allow", s.allow ? "allow_match" : "allow_miss");
  if (s.ask || !s.allow) {
    add("approval", s.approve === "yes" ? "approved" : "declined");
    if (s.approve !== "yes") return finish("blocked_result");
  }
  const networkBlocked = s.request === "network" && s.sandbox;
  add("execution", networkBlocked ? "sandbox_block" : "executed");
  return finish(networkBlocked ? "failed_result" : "success_result");
}

export function verificationTrace(s) {
  const realFix = s.change === "fix";
  // Missing checks are not treated as passing evidence. Either observed
  // failure is sufficient to reject; acceptance needs both positive checks.
  const verdict = !realFix && (s.diff || s.mutation) ? "reject"
    : s.diff && s.mutation ? "accept" : "incomplete";
  return [
    { node: "baseline", key: "baseline" },
    { node: "red", key: "red" },
    { node: "edit", key: realFix ? "edit_fix" : "edit_weaken" },
    { node: "green", key: "green" },
    { node: "diff", key: s.diff ? (realFix ? "diff_fix" : "diff_weaken") : "diff_skipped" },
    { node: "mutation", key: s.mutation ? (realFix ? "mutation_fix" : "mutation_weaken") : "mutation_skipped" },
    { node: "verdict", key: verdict },
    { node: "return", key: `return_${verdict}` },
  ];
}

export function networkTrace(s) {
  // `from` is the data source, not the previous timeline event. Local
  // persistence branches from context even when the model route is denied.
  const trace = [{ node: "files", key: "files" }, { node: "context", from: "files", key: "context" }];
  if (s.internal) {
    trace.push({ node: "gateway", from: "context", key: s.gateway ? "gateway_saved" : "gateway_transient", retain: s.gateway });
    trace.push({ node: "endpoint", from: "gateway", key: s.endpoint ? "endpoint_saved" : "endpoint_transient", retain: s.endpoint });
  } else {
    trace.push({ node: "public", from: "context", key: s.egress ? "public_model_blocked" : "public_model_sent", blocked: s.egress });
  }
  trace.push({ node: "transcript", from: "context", key: s.transcript ? "transcript_saved" : "transcript_off", retain: s.transcript });
  trace.push({ node: "telemetry", from: "context", key: s.telemetry ? "telemetry_content" : "telemetry_metadata", retain: s.telemetry });
  trace.push({ node: "usage", from: "context", key: "usage" });
  trace.push({ node: "public", from: "context", key: s.nonessential ? "nonessential_off" : s.egress ? "nonessential_blocked" : "nonessential_sent", blocked: !s.nonessential && s.egress, disabled: s.nonessential });
  trace.push({ node: "context", key: "finish" });
  return trace;
}

export function buildTrace(id, settings) {
  return { permissions: permissionTrace, verification: verificationTrace, network: networkTrace }[id](settings);
}

// A stable outcome fingerprint lets the UI compare cause and effect without
// declaring every toggle consequential. Unreached settings may change nothing.
export function flowOutcome(id, trace) {
  if (id === 'permissions') {
    const event = trace.find((e) => ['hook_block', 'deny_block', 'declined', 'sandbox_block', 'executed'].includes(e.key));
    return { event: trace.indexOf(event), key: event.key, copies: [] };
  }
  if (id === 'verification') {
    const event = trace.find((e) => e.node === 'verdict');
    return { event: trace.indexOf(event), key: event.key, copies: [] };
  }
  return {
    event: trace.length - 1,
    key: trace.some((e) => e.node === 'endpoint') ? 'internal' : trace.some((e) => e.key === 'public_model_sent') ? 'public' : 'blocked',
    copies: trace.filter((e) => e.retain).map((e) => e.node),
    extraTraffic: trace.find((e) => e.key.startsWith('nonessential_')).key,
  };
}
