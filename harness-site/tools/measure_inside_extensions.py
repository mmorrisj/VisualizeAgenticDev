#!/usr/bin/env python3
"""Measure the data for "Inside an extension" (spec section 6.7) from the course.

Runs the course's own Module 5 examples and practice-app, and writes the
measured parts of content/inside-extensions.json: "measured", "session", and
"ledger". Hand-written parts of that file (concept, lenses, copy) are kept.

    python3 tools/measure_inside_extensions.py [--course ../course]

What is real and what is scripted:
- Real: every tool result (test output, the triage script's output, file
  contents, the MCP server's replies, the hook's exit codes), the skill and
  agent files, the plugin manifests, and every token count.
- Scripted: the model's tool calls and text, and the subagent's summary. The
  course harness cannot run MCP servers, skills, or subagents, so the order of
  the session is written here. Events carry "scripted": true where that applies.

Tokens use the course harness's own estimator (mini-harness/backends.py:
about 4 characters per token, applied to the JSON that would be sent). Each
part is estimated on its own; the request total is the sum of its parts.

Python standard library only. Needs git (practice-app's setup.sh uses it).
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

SITE = pathlib.Path(__file__).resolve().parent.parent
OUT = SITE / "content" / "inside-extensions.json"

TASK = ("The tests are failing. Find out why, fix it, add a regression test, "
        "and check whether any user has an empty password.")

MECHANISMS = ["mcp", "skill", "subagent"]


def args_():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--course", default=str(SITE.parent / "course"))
    return p.parse_args()


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> tuple[str, str, dict]:
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    fm, body = m.group(1), m.group(2)
    fields = dict(line.split(": ", 1) for line in fm.splitlines() if ": " in line)
    return fm, body, fields


# Recorded text shows the practice-app copy as ~/practice-app, wherever it ran,
# so sizes do not depend on the temporary directory's name.
LAB_SHOWN = "~/practice-app"


def run(cmd, cwd, stdin=None):
    res = subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True)
    res.stdout = res.stdout.replace(str(cwd), LAB_SHOWN)
    res.stderr = res.stderr.replace(str(cwd), LAB_SHOWN)
    return res


def pin_ts(text: str) -> str:
    """practice-app logs a wall-clock timestamp; fix it so every run measures the same."""
    return re.sub(r'"ts": [0-9.]+', '"ts": 1790000000.0', text)


def mcp_session(server: pathlib.Path, calls: list[dict]) -> list[dict]:
    """Drive the stdio MCP server and record every line on the wire, verbatim."""
    proc = subprocess.Popen([sys.executable, str(server)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    wire = []
    for msg in calls:
        line = json.dumps(msg)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        wire.append({"dir": "out", "method": msg["method"], "line": line})
        if "id" in msg:
            reply = proc.stdout.readline().strip()
            wire.append({"dir": "in", "method": msg["method"], "line": reply})
    proc.stdin.close()
    proc.wait(timeout=10)
    return wire


def main() -> int:
    a = args_()
    course = pathlib.Path(a.course).resolve()
    sys.path.insert(0, str(course / "mini-harness"))
    from backends import estimate_tokens  # the course's estimator
    import harness as mini                 # for its base instructions and tool definitions

    ext = course / "modules" / "05-extensibility" / "examples"
    plugin = ext / "internal-marketplace" / "plugins" / "practice-toolkit"
    skill_md = read(plugin / "skills" / "practice-test-triage" / "SKILL.md")
    agent_md = read(plugin / "agents" / "test-reviewer.md")
    failures_py = plugin / "skills" / "practice-test-triage" / "scripts" / "failures.py"
    hook_py = plugin / "hooks" / "no_test_weakening.py"

    # ---- a fresh practice-app copy -----------------------------------------
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="lab-"))
    lab = tmp / "practice-app"
    setup = run(["bash", str(course / "practice-app" / "setup.sh"), str(lab)], cwd=tmp)
    if setup.returncode:
        print(setup.stderr, file=sys.stderr)
        return 1
    try:
        return measure(course, ext, plugin, skill_md, agent_md, failures_py, hook_py,
                       lab, estimate_tokens, mini)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def measure(course, ext, plugin, skill_md, agent_md, failures_py, hook_py, lab, est, mini):
    tok = lambda obj: est(obj)  # noqa: E731

    # ---- skill and subagent files ---------------------------------------------
    skill_fm, skill_body, skill_fields = frontmatter(skill_md)
    agent_fm, agent_body, agent_fields = frontmatter(agent_md)
    skill_listing = f"{skill_fields['name']}: {skill_fields['description']}"
    agent_listing = f"{agent_fields['name']}: {agent_fields['description']}"

    # ---- tests before the fix --------------------------------------------------
    full_before = pin_ts(run([sys.executable, "run_tests.py"], lab).stdout)
    triage_before = run([sys.executable, str(failures_py)], lab).stdout
    auth_py = read(lab / "src" / "auth.py")

    # ---- MCP server, driven over stdio ---------------------------------------
    calls = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "harness", "version": "0.1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "run_select", "arguments": {
             "sql": "SELECT name, created FROM users WHERE password_hash = ''"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "run_select", "arguments": {
             "sql": "SELECT ts, success FROM login_events WHERE user = 'carol'"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "run_select", "arguments": {
             "sql": "UPDATE users SET password_hash = NULL WHERE name = 'carol'"}}},
    ]
    wire = mcp_session(ext / "mcp-server" / "practice_db_server.py", calls)
    replies = {json.loads(w["line"])["id"]: json.loads(w["line"])
               for w in wire if w["dir"] == "in"}
    mcp_tools = replies[2]["result"]["tools"]
    # In the request, MCP tools appear under the harness's prefixed names.
    mcp_tool_defs = [{"name": f"mcp__practice-db__{t['name']}", "description": t["description"],
                      "input_schema": t["inputSchema"]} for t in mcp_tools]
    mcp_text = lambda i: replies[i]["result"]["content"][0]["text"]  # noqa: E731
    mcp_error = lambda i: replies[i]["result"]["isError"]  # noqa: E731

    # ---- the fix and the regression test, checked by the real hook ----------
    fix_old = "    if not stored_hash:\n        return True"
    fix_new = "    if not stored_hash:\n        return False"
    test_old = ('def test_empty_hash_is_rejected():\n    user = make_user(stored_hash="")\n'
                '    assert verify_password("anything", user.hash) is False\n')
    test_new = test_old + ('\n\ndef test_empty_password_does_not_match_empty_hash():\n'
                           '    user = make_user(stored_hash="")\n'
                           '    assert verify_password("", user.hash) is False\n')
    hook_runs = []
    for rel, old, new in [("src/auth.py", fix_old, fix_new),
                          ("tests/test_login.py", test_old, test_new)]:
        event = {"tool_name": "Edit", "tool_input": {
            "file_path": str(lab / rel), "old_string": old, "new_string": new}}
        res = run([sys.executable, str(hook_py)], lab, stdin=json.dumps(event))
        hook_runs.append({"file": rel, "exit_code": res.returncode,
                          "stderr": res.stderr.strip()})
        path = lab / rel
        text = read(path)
        assert text.count(old) == 1, f"edit target not found in {rel}"
        path.write_text(text.replace(old, new), encoding="utf-8")
    # A weakening edit, to show the hook can say no (shown in the plugin lens).
    weak = {"tool_name": "Edit", "tool_input": {
        "file_path": str(lab / "tests" / "test_login.py"),
        "old_string": test_old, "new_string": test_old.replace(
            '    assert verify_password("anything", user.hash) is False\n', "    pass\n")}}
    res = run([sys.executable, str(hook_py)], lab, stdin=json.dumps(weak))
    hook_blocked = {"file": "tests/test_login.py", "exit_code": res.returncode,
                    "stderr": res.stderr.strip()}

    full_after = pin_ts(run([sys.executable, "run_tests.py"], lab).stdout)
    triage_after = run([sys.executable, str(failures_py)], lab).stdout
    test_login_after = read(lab / "tests" / "test_login.py")
    grep_out = run(["grep", "-rnE", r"skip|xfail|assert True", "tests"], lab).stdout or "(no matches)"

    # ---- tool-use and tool-result blocks, as the request would carry them ----
    uid = itertools.count(1)

    def use(name, inp, text=None):
        content = ([{"type": "text", "text": text}] if text else []) + \
                  [{"type": "tool_use", "id": f"toolu_{next(uid):02d}", "name": name, "input": inp}]
        return {"role": "assistant", "content": content}

    def result(content, is_error=False):
        block = {"type": "tool_result", "tool_use_id": "toolu_xx", "content": content}
        if is_error:
            block["is_error"] = True
        return {"role": "user", "content": [block]}

    events = []

    def add(eid, ctx, role, label, payload, when=None, request=False, scripted=False,
            mechanism=None, show=None, scales=False):
        events.append({"id": eid, "ctx": ctx, "role": role, "label": label,
                       "tokens": tok(payload), "when": when, "request_after": request,
                       "scripted": scripted, "mechanism": mechanism, "scales": scales,
                       "show": show if show is not None else (payload if isinstance(payload, str) else None)})

    add("task", "main", "user", "Your request", {"role": "user", "content": TASK},
        request=True, show=TASK)
    # Triage: with the skill, load it and run its script; without, run the full tests.
    add("use-skill", "main", "model", "Model picks the skill",
        use("Skill", {"skill": "practice-test-triage"}, "This looks like a test failure; I'll use the triage skill."),
        when="skill", scripted=True, mechanism="skill")
    add("skill-body", "main", "skill", "Skill body loads", result(skill_body),
        when="skill", request=True, mechanism="skill", show=skill_body)
    add("run-triage", "main", "model", "Model runs failures.py",
        use("run_command", {"command": "python3 ${CLAUDE_SKILL_DIR}/scripts/failures.py",
                            "description": "Compact failure summary"}),
        when="skill", scripted=True, mechanism="skill")
    add("triage-out", "main", "result", "Two-line summary", result(triage_before),
        when="skill", request=True, mechanism="skill", show=triage_before)
    add("run-tests", "main", "model", "Model runs the tests",
        use("run_command", {"command": "python3 run_tests.py", "description": "Run the tests"}),
        when="!skill", scripted=True)
    add("tests-out", "main", "result", "Full test output", result(full_before),
        when="!skill", request=True, show=full_before, scales=True)
    add("read-auth", "main", "model", "Model reads src/auth.py",
        use("read_file", {"path": "src/auth.py"}), scripted=True)
    add("auth-out", "main", "result", "src/auth.py", result(auth_py), request=True, show=auth_py)
    # The password question, through the MCP server.
    for i, (eid, label) in enumerate([("q-empty", "Users with an empty hash"),
                                      ("q-logins", "Carol's logins"),
                                      ("q-update", "Attempted UPDATE")], start=3):
        sql = calls[i]["params"]["arguments"]["sql"]
        add(f"{eid}-call", "main", "model", f"Model calls run_select ({label.lower()})",
            use("mcp__practice-db__run_select", {"sql": sql}), when="mcp", scripted=True,
            mechanism="mcp", show=sql)
        add(f"{eid}-out", "main", "result", label, result(mcp_text(i), mcp_error(i)),
            when="mcp", request=True, mechanism="mcp", show=mcp_text(i))
    # The fix and the regression test. The hook checks each edit; it adds no context.
    add("edit-auth", "main", "model", "Model edits src/auth.py",
        use("edit_file", {"path": "src/auth.py", "old_text": fix_old, "new_text": fix_new}), scripted=True)
    add("edit-auth-out", "main", "result", "Edit applied", result("Edited src/auth.py"), request=True)
    add("edit-test", "main", "model", "Model adds a regression test",
        use("edit_file", {"path": "tests/test_login.py", "old_text": test_old, "new_text": test_new}),
        scripted=True)
    add("edit-test-out", "main", "result", "Edit applied", result("Edited tests/test_login.py"), request=True)
    add("rerun", "main", "model", "Model re-runs the tests",
        use("run_command", {"command": "python3 ${CLAUDE_SKILL_DIR}/scripts/failures.py",
                            "description": "Re-run tests"}), when="skill", scripted=True, mechanism="skill")
    add("rerun-out", "main", "result", "Tests pass", result(triage_after), when="skill", request=True,
        mechanism="skill", show=triage_after)
    add("rerun-full", "main", "model", "Model re-runs the tests",
        use("run_command", {"command": "python3 run_tests.py", "description": "Re-run tests"}),
        when="!skill", scripted=True)
    add("rerun-full-out", "main", "result", "Tests pass", result(full_after), when="!skill", request=True,
        show=full_after, scales=True)
    # Review of the new test: in a subagent, or in the main conversation.
    delegation = ("Review the change to tests/test_login.py: one test was added, "
                  "test_empty_password_does_not_match_empty_hash. Report any weakening.")
    add("delegate", "main", "model", "Model delegates to test-reviewer",
        use("Task", {"subagent_type": "test-reviewer", "prompt": delegation}),
        when="subagent", scripted=True, mechanism="subagent", show=delegation)
    sub_tools = [t for t in mini.TOOL_DEFINITIONS if t["name"] in ("read_file", "list_files", "search")]
    add("sub-system", "sub", "system", "Subagent system prompt (the agent file)", agent_body,
        when="subagent", mechanism="subagent", show=agent_body)
    add("sub-tools", "sub", "tools", "Read-only tools", sub_tools, when="subagent", mechanism="subagent")
    add("sub-task", "sub", "user", "Delegated task", {"role": "user", "content": delegation},
        when="subagent", request=True, mechanism="subagent", show=delegation)
    review_summary = ("No weakening found. tests/test_login.py: one test added "
                      "(test_empty_password_does_not_match_empty_hash) with one new assertion; "
                      "no assertions removed; no skips, xfails, or always-true assertions.")
    for ctx, cond, prefix in [("sub", "subagent", "sub-"), ("main", "!subagent", "")]:
        mech = "subagent" if ctx == "sub" else None
        add(f"{prefix}read-test", ctx, "model", "Reads tests/test_login.py",
            use("read_file", {"path": "tests/test_login.py"}), when=cond, scripted=True, mechanism=mech)
        add(f"{prefix}test-out", ctx, "result", "tests/test_login.py", result(test_login_after),
            when=cond, request=True, mechanism=mech, show=test_login_after)
        add(f"{prefix}grep", ctx, "model", "Searches tests/ for skips",
            use("search", {"pattern": "skip|xfail|assert True", "path": "tests"}),
            when=cond, scripted=True, mechanism=mech)
        add(f"{prefix}grep-out", ctx, "result", "Search results", result(grep_out),
            when=cond, request=True, mechanism=mech, show=grep_out)
    add("sub-answer", "sub", "model", "Subagent's final answer",
        {"role": "assistant", "content": review_summary}, when="subagent", scripted=True,
        mechanism="subagent", show=review_summary)
    add("summary", "main", "subagent", "Subagent summary returns", result(review_summary),
        when="subagent", request=True, mechanism="subagent", show=review_summary)
    add("final", "main", "model", "Final answer", {"role": "assistant", "content": (
        "Fixed: verify_password accepted an empty stored hash. It now rejects it, and a "
        "regression test covers an empty password. Carol has an empty hash and logged in "
        "twice; the server refused my attempt to change her row, so that needs a human.")},
        when=None, scripted=True)

    # ---- always-on blocks -------------------------------------------------------
    system_text = mini.BASE_INSTRUCTIONS
    always = {
        "system": {"role": "system", "label": "System prompt", "tokens": tok(system_text), "when": None},
        "tools": {"role": "tools", "label": "Built-in tool definitions",
                  "tokens": tok(mini.TOOL_DEFINITIONS), "when": None},
        "mcp-tools": {"role": "tools", "label": "practice-db tool definitions",
                      "tokens": tok(mcp_tool_defs), "when": "mcp", "mechanism": "mcp"},
        "skill-listing": {"role": "skill", "label": "Skill description",
                          "tokens": tok(skill_listing), "when": "skill", "mechanism": "skill"},
        "agent-listing": {"role": "subagent", "label": "Subagent description",
                          "tokens": tok(agent_listing), "when": "subagent", "mechanism": "subagent"},
    }

    session = {"always": always, "events": events}
    ledger = {"expected": {}}
    for n in range(len(MECHANISMS) + 1):
        for combo in itertools.combinations(MECHANISMS, n):
            ledger["expected"][",".join(combo) or "none"] = compose(session, set(combo))

    triage = {
        "full_chars": len(full_before), "full_tokens": tok(result(full_before)),
        "condensed_chars": len(triage_before), "condensed_tokens": tok(result(triage_before)),
        "full_text": full_before, "condensed_text": triage_before,
    }
    measured = {
        "estimator": "mini-harness/backends.py estimate_tokens: len(json) // 4",
        "skill": {"listing": skill_listing, "listing_tokens": tok(skill_listing),
                  "body": skill_body, "body_tokens": tok(skill_body),
                  "source": "modules/05-extensibility/examples/internal-marketplace/plugins/practice-toolkit/skills/practice-test-triage/SKILL.md"},
        "subagent": {"listing": agent_listing, "listing_tokens": tok(agent_listing),
                     "system_prompt": agent_body, "system_tokens": tok(agent_body),
                     "tools_allowed": [t.strip() for t in agent_fields["tools"].split(",")],
                     "tools_locked": ["Edit", "Write", "Bash"],
                     "source": "modules/05-extensibility/examples/internal-marketplace/plugins/practice-toolkit/agents/test-reviewer.md"},
        "mcp": {"server": "practice-db", "tool_defs_tokens": tok(mcp_tool_defs),
                "tools_list_tokens": tok(mcp_tools),
                "tool_names": [t["name"] for t in mcp_tools],
                "source": "modules/05-extensibility/examples/mcp-server/practice_db_server.py"},
        "hook": {"event": "PreToolUse", "matcher": "Edit|Write", "context_tokens": 0,
                 "runs": hook_runs, "blocked_example": hook_blocked,
                 "source": "modules/05-extensibility/examples/internal-marketplace/plugins/practice-toolkit/hooks/no_test_weakening.py"},
        "plugin": {"manifest": read(plugin / ".claude-plugin" / "plugin.json"),
                   "hooks_json": read(plugin / "hooks" / "hooks.json"),
                   "mcp_json": read(plugin / ".mcp.json"),
                   "always_tokens": always["mcp-tools"]["tokens"] + always["skill-listing"]["tokens"]
                   + always["agent-listing"]["tokens"]},
        "triage": triage,
        "wire": wire,
        "claude_code_reported": {
            "source": "modules/05-extensibility/README.md, Lab D (claude plugin details)",
            "always_on": 119,
            "skill": {"always_on": 80, "on_invoke": 190},
            "subagent": {"always_on": 40, "on_invoke": 130},
            "note": "Claude Code's own count; it excludes the MCP tool schemas.",
        },
    }

    data = json.loads(read(OUT)) if OUT.exists() else {}
    data.update({"task": TASK, "measured": measured, "session": session, "ledger": ledger})
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    e = ledger["expected"]
    print(f"wrote {OUT.relative_to(SITE)}")
    print(f"  triage: full {triage['full_chars']} chars / {triage['full_tokens']} tok; "
          f"condensed {triage['condensed_chars']} chars / {triage['condensed_tokens']} tok")
    print(f"  skill listing {tok(skill_listing)}, body {tok(skill_body)}; "
          f"agent listing {tok(agent_listing)}, system {tok(agent_body)}; "
          f"mcp tool defs {tok(mcp_tool_defs)}")
    print(f"  hook runs: {[r['exit_code'] for r in hook_runs]}, weakening edit: {hook_blocked['exit_code']}")
    for k, v in e.items():
        print(f"  {k:22} requests {v['requests']:2}  total input {v['total_input']:6}  "
              f"final context {v['final_context']:5}  subagent input {v['sub_input']:5}")
    return 0


def active(when, on: set) -> bool:
    if when is None:
        return True
    return (when[1:] not in on) if when.startswith("!") else (when in on)


def compose(session: dict, on: set, scale: float = 1) -> dict:
    """Build each request of the main conversation for a set of enabled mechanisms.

    `scale` multiplies events marked "scales" (the full test output), for the
    page's illustrative test-suite-size control; the triage script's two lines
    do not grow with the suite. Stored totals are for scale 1, as measured.

    Mirrors composeLedger() in assets/js/inside-extensions.js; check.py runs it
    too, so the page, the checker, and this script agree on every total.
    """
    always = sum(b["tokens"] for b in session["always"].values() if active(b.get("when"), on))
    conv, sub_conv, requests, sub_requests = 0, 0, [], []
    for ev in session["events"]:
        if not active(ev["when"], on):
            continue
        tokens = round(ev["tokens"] * scale) if ev.get("scales") else ev["tokens"]
        if ev["ctx"] == "sub":
            sub_conv += tokens
            if ev["request_after"]:
                sub_requests.append(sub_conv)
            continue
        conv += tokens
        if ev["request_after"]:
            requests.append(always + conv)
    return {"requests": len(requests), "request_sizes": requests,
            "total_input": sum(requests), "final_context": requests[-1] if requests else 0,
            "sub_requests": len(sub_requests), "sub_input": sum(sub_requests)}


if __name__ == "__main__":
    sys.exit(main())
