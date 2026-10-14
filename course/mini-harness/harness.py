#!/usr/bin/env python3
"""mini-harness: a small, readable agent harness. Standard library only.

This is the reference implementation used throughout the course. It shows every
part of a harness in one place:

  * the agent loop .................. Harness.run_turn()
  * tools ........................... Harness.tool_* methods, TOOL_DEFINITIONS
  * permissions (hard controls) ..... Policy.check(), split_command()
  * hooks (hard controls) ........... Policy.run_hooks()
  * context and memory .............. Harness.build_system(), Harness.compact()
  * observability ................... Harness.log(), /usage and /context

Run it against the practice app with a scripted mock model (no network needed):

    python3 harness.py --workdir ~/practice-app \\
        --backend mock --scenario scenarios/investigate.json \\
        --prompt "The login test is failing. Find out why, but don't change anything yet."

See the module READMEs for real-model configuration.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import uuid

from backends import BackendError, estimate_tokens, make_backend

HERE = pathlib.Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Tool definitions: this exact JSON is sent to the model on every request.
# --------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read a text file inside the working directory.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                         "required": ["path"]},
    },
    {
        "name": "list_files",
        "description": "List files under a directory inside the working directory.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "search",
        "description": "Search files for a regular expression. Returns path:line: text matches.",
        "input_schema": {"type": "object",
                         "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                         "required": ["pattern"]},
    },
    {
        "name": "run_command",
        "description": "Run a shell command in the working directory. "
                       "Give a short description of what it does.",
        "input_schema": {"type": "object",
                         "properties": {"command": {"type": "string"},
                                        "description": {"type": "string"}},
                         "required": ["command"]},
    },
    {
        "name": "edit_file",
        "description": "Replace one exact occurrence of old_text with new_text in a file.",
        "input_schema": {"type": "object",
                         "properties": {"path": {"type": "string"},
                                        "old_text": {"type": "string"},
                                        "new_text": {"type": "string"}},
                         "required": ["path", "old_text", "new_text"]},
    },
]

BASE_INSTRUCTIONS = """You are a coding agent working in a local repository.
Use the tools to inspect files and run commands. Prefer small, verifiable changes.
Explain what you are about to do before calling tools. When finished, summarize
what you changed and how you verified it."""

INSTRUCTION_FILES = ["AGENTS.md", "CLAUDE.md"]

# Shell operators that join several commands into one string.
COMMAND_SEPARATORS = re.compile(r"\|\||&&|;|\||&|\n")
# Constructs whose real behavior a simple splitter cannot know.
UNANALYZABLE = re.compile(r"\$\(|`|<\(|>\(")


def split_command(command: str):
    """Split a compound shell command into subcommands.

    Returns None when the command contains substitution (`$(...)`, backticks,
    process substitution). Those can hide arbitrary commands, so an allow rule
    must never approve them.
    """
    if UNANALYZABLE.search(command):
        return None
    parts = [p.strip() for p in COMMAND_SEPARATORS.split(command)]
    return [p for p in parts if p]


class Color:
    enabled = sys.stdout.isatty()

    @classmethod
    def wrap(cls, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if cls.enabled else text

    blue = classmethod(lambda c, t: c.wrap("94", t))
    green = classmethod(lambda c, t: c.wrap("92", t))
    red = classmethod(lambda c, t: c.wrap("91", t))
    yellow = classmethod(lambda c, t: c.wrap("93", t))
    dim = classmethod(lambda c, t: c.wrap("2", t))


# --------------------------------------------------------------------------
# Policy: permission rules and hooks. These are HARD controls: they run in
# harness code, so the model cannot talk its way past them.
# --------------------------------------------------------------------------
class Policy:
    """Rules look like "tool" or "tool(pattern)".

    The pattern is matched (fnmatch) against the path for file tools, or against
    EACH subcommand for run_command. Precedence: deny, then ask, then allow,
    then the default "mode".
    """

    def __init__(self, path: pathlib.Path | None):
        data = {}
        if path:
            data = json.loads(path.read_text(encoding="utf-8"))
        self.path = path
        self.base_dir = path.parent if path else HERE
        self.mode = data.get("mode", "ask")
        self.allow = list(data.get("allow", []))
        self.ask = list(data.get("ask", []))
        self.deny = list(data.get("deny", []))
        self.pre_tool_hooks = list(data.get("hooks", {}).get("pre_tool", []))
        self.command_timeout = data.get("command_timeout", 60)
        self.scrub_env = data.get("scrub_env", False)
        self.sandbox_prefix = list(data.get("sandbox_prefix", []))
        self.max_output_chars = data.get("max_output_chars", 8000)
        # Set false to see why naive whole-string matching is dangerous (Module 2).
        self.split_compound = data.get("split_compound", True)

    @staticmethod
    def _parse(rule: str):
        m = re.fullmatch(r"(\w+)(?:\((.*)\))?", rule.strip())
        if not m:
            raise ValueError(f"Bad rule: {rule!r}")
        return m.group(1), m.group(2)

    def _matches(self, rules, tool: str, subject: str | None) -> str | None:
        for rule in rules:
            name, pattern = self._parse(rule)
            if name != tool:
                continue
            if pattern is None or (subject is not None and fnmatch.fnmatch(subject, pattern)):
                return rule
        return None

    def check(self, tool: str, subjects: list | None):
        """Return (decision, rule). decision is 'allow', 'ask' or 'deny'.

        subjects is the list of things to match: [path] for file tools, the
        subcommands for run_command, or None when the command is unanalyzable.
        """
        items = subjects if subjects is not None else [None]
        for subject in items:  # deny if ANY part matches a deny rule
            rule = self._matches(self.deny, tool, subject)
            if rule:
                return "deny", rule
        for subject in items:  # ask if ANY part matches an ask rule
            rule = self._matches(self.ask, tool, subject)
            if rule:
                return "ask", rule
        if subjects is None:
            return ("deny" if self.mode == "deny" else "ask"), "unanalyzable command"
        allowed = [self._matches(self.allow, tool, s) for s in items]
        if all(allowed):  # allow only if EVERY part matches an allow rule
            return "allow", ", ".join(sorted(set(allowed)))
        return self.mode, "default mode"

    def run_hooks(self, tool: str, tool_input: dict, workdir: pathlib.Path):
        """Run pre_tool hooks. Exit code 2 blocks the call; stderr is the reason."""
        payload = json.dumps({"event": "pre_tool", "tool": tool, "input": tool_input,
                              "workdir": str(workdir)})
        for hook in self.pre_tool_hooks:
            proc = subprocess.run(["bash", "-c", hook], input=payload, capture_output=True,
                                  text=True, cwd=self.base_dir, timeout=30)
            if proc.returncode == 2:
                return hook, (proc.stderr.strip() or "blocked by hook")
            if proc.returncode != 0:
                print(Color.yellow(f"  [hook warning] {hook} exited {proc.returncode}: "
                                   f"{proc.stderr.strip()[:200]}"))
        return None, None


# --------------------------------------------------------------------------
# The harness
# --------------------------------------------------------------------------
class Harness:
    def __init__(self, args):
        self.args = args
        self.workdir = pathlib.Path(args.workdir).expanduser().resolve()
        if not self.workdir.is_dir():
            raise SystemExit(f"Working directory not found: {self.workdir}")
        policy_path = pathlib.Path(args.policy).resolve() if args.policy else None
        self.policy = Policy(policy_path)
        self.backend = make_backend(args)
        self.session_id = uuid.uuid4().hex[:8]
        self.messages: list = []
        self.request_index = 0
        self.records: list = []
        log_path = args.log or (self.workdir / ".mini-harness" / "usage.jsonl")
        self.log_path = pathlib.Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.system = self.build_system()

    # ---- context and memory ---------------------------------------------
    def build_system(self) -> str:
        """Everything here is re-sent on EVERY request."""
        parts = [BASE_INSTRUCTIONS,
                 f"Environment: working directory {self.workdir}; "
                 f"platform {sys.platform}; date {time.strftime('%Y-%m-%d')}."]
        self.loaded_files = []
        for name in INSTRUCTION_FILES:
            path = self.workdir / name
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                parts.append(f"Project instructions from {name}:\n{text}")
                self.loaded_files.append(f"{name} ({len(text.splitlines())} lines)")
        return "\n\n".join(parts)

    def request_size(self) -> int:
        return estimate_tokens({"system": self.system, "tools": TOOL_DEFINITIONS,
                                "messages": self.messages})

    def compact(self):
        """Lossy compaction: drop the bodies of older tool results.

        Real harnesses usually ask the model to write a summary instead. Either
        way, detail is lost and cannot be recovered from the conversation.
        """
        limit = self.args.context_limit
        before = self.request_size()
        if before < 0.8 * limit:
            return
        keep_recent = 4
        for msg in self.messages[:-keep_recent]:
            if isinstance(msg["content"], list):
                for block in msg["content"]:
                    if block.get("type") == "tool_result" and \
                            not block["content"].startswith("[removed during compaction"):
                        size = len(block["content"])
                        block["content"] = f"[removed during compaction: {size} characters]"
        after = self.request_size()
        print(Color.yellow(f"  [compacted context: ~{before} -> ~{after} tokens]"))
        self.log({"type": "compaction", "before_tokens": before, "after_tokens": after})

    # ---- observability ----------------------------------------------------
    def log(self, record: dict):
        record = {"ts": round(time.time(), 3), "session": self.session_id, **record}
        self.records.append(record)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    # ---- path safety ------------------------------------------------------
    def resolve(self, rel: str) -> pathlib.Path:
        """The file tools' scope check. Note: this does NOT constrain run_command."""
        path = (self.workdir / rel).resolve()
        if path != self.workdir and self.workdir not in path.parents:
            raise PermissionError(f"{rel} is outside the working directory")
        return path

    def rel(self, path: str) -> str:
        try:
            return str(self.resolve(path).relative_to(self.workdir))
        except (PermissionError, ValueError):
            return path

    # ---- tools ------------------------------------------------------------
    def tool_read_file(self, inp):
        return self.resolve(inp["path"]).read_text(encoding="utf-8", errors="replace")

    def tool_list_files(self, inp):
        base = self.resolve(inp.get("path", "."))
        files = [str(p.relative_to(self.workdir)) for p in sorted(base.rglob("*"))
                 if p.is_file() and not {".git", ".mini-harness"} & set(p.parts)]
        return "\n".join(files) or "(no files)"

    def tool_search(self, inp):
        regex = re.compile(inp["pattern"])
        base = self.resolve(inp.get("path", "."))
        hits = []
        for p in sorted(base.rglob("*")):
            if not p.is_file() or {".git", ".mini-harness"} & set(p.parts):
                continue
            # Apply read_file deny rules here too; otherwise search would leak
            # the contents of files the policy says the agent may not read.
            if self.policy.check("read_file", [str(p.relative_to(self.workdir))])[0] == "deny":
                continue
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(lines, 1):
                if regex.search(line):
                    hits.append(f"{p.relative_to(self.workdir)}:{n}: {line.strip()}")
        return "\n".join(hits) or "no matches"

    def tool_run_command(self, inp):
        env = os.environ.copy()
        if self.policy.scrub_env:  # don't hand the agent your credentials
            env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TERM") if k in os.environ}
        argv = self.policy.sandbox_prefix + ["bash", "-c", inp["command"]]
        proc = subprocess.run(argv, cwd=self.workdir, capture_output=True, text=True,
                              env=env, timeout=self.policy.command_timeout)
        out = (proc.stdout + proc.stderr).strip()
        limit = self.policy.max_output_chars
        if len(out) > limit:  # truncation: the model never sees the middle
            out = out[: limit // 2] + f"\n[... {len(out) - limit} characters truncated ...]\n" \
                  + out[-limit // 2:]
        return f"exit code {proc.returncode}\n{out}"

    def tool_edit_file(self, inp):
        path = self.resolve(inp["path"])
        text = path.read_text(encoding="utf-8")
        count = text.count(inp["old_text"])
        if count != 1:
            raise ValueError(f"old_text must appear exactly once in {inp['path']} "
                             f"(found {count})")
        path.write_text(text.replace(inp["old_text"], inp["new_text"]), encoding="utf-8")
        return f"Edited {inp['path']}"

    # ---- permission flow ----------------------------------------------------
    def subjects_for(self, name: str, inp: dict):
        if name == "run_command":
            if not self.policy.split_compound:
                return [inp.get("command", "")]  # naive: match the whole string
            return split_command(inp.get("command", ""))
        if "path" in inp or name in ("list_files", "search"):
            return [self.rel(inp.get("path", "."))]
        return []

    def describe(self, name: str, inp: dict) -> str:
        if name == "run_command":
            return inp.get("command", "")
        if name == "search":
            return f"{inp.get('pattern', '')!r}, {inp.get('path', '.')}"
        return inp.get("path", "")

    def preview_edit(self, inp):
        try:
            old = self.resolve(inp["path"]).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return
        new = old.replace(inp["old_text"], inp["new_text"], 1)
        for line in difflib.unified_diff(old.splitlines(), new.splitlines(),
                                         inp["path"], inp["path"], lineterm="", n=2):
            colour = Color.red if line.startswith("-") else Color.green \
                if line.startswith("+") else Color.dim
            print("    " + colour(line))

    def ask_user(self, name: str, inp: dict, reason: str):
        print(Color.yellow(f"  [permission needed] {name}  ({reason})"))
        if name == "run_command":
            print("    command:     " + inp.get("command", ""))
            print(Color.dim("    description: " + inp.get("description", "(none given)")
                            + "   <- written by the model"))
        elif name == "edit_file":
            self.preview_edit(inp)
        else:
            print("    " + json.dumps(inp))
        prompt = "  Allow? [y] once  [a] always this session  [n] deny (or type a reason): "
        try:
            answer = input(prompt).strip()
        except EOFError:
            answer = ""
            print()
        if answer.lower() in ("y", "yes"):
            return "allow", "user (once)", None
        if answer.lower() in ("a", "always"):
            subjects = self.subjects_for(name, inp) or []
            for s in subjects:
                rule = f"{name}({s})" if s else name
                self.policy.allow.append(rule)
                print(Color.dim(f"    added session rule: allow {rule}"))
            return "allow", "user (always)", None
        why = answer if len(answer) > 1 and answer.lower() not in ("no",) else None
        return "deny", "user", why

    def authorize(self, name: str, inp: dict):
        hook, hook_reason = self.policy.run_hooks(name, inp, self.workdir)
        if hook:
            return "deny", f"hook: {hook}", hook_reason
        decision, rule = self.policy.check(name, self.subjects_for(name, inp))
        if decision == "allow":
            return "allow", f"rule: {rule}", None
        if decision == "deny":
            return "deny", f"rule: {rule}", f"Blocked by policy rule {rule}"
        return self.ask_user(name, inp, rule)

    def execute(self, block: dict) -> dict:
        name, inp = block["name"], block["input"]
        print(f"• {Color.green(name)}({self.describe(name, inp)})")
        start = time.time()
        decision, source, reason = self.authorize(name, inp)
        if decision == "deny":
            content = f"Permission denied ({source})." + (f" Reason: {reason}" if reason else "")
            print(Color.red(f"    denied by {source}" + (f": {reason}" if reason else "")))
            is_error = True
        else:
            try:
                content = getattr(self, f"tool_{name}")(inp)
                is_error = False
            except Exception as err:  # noqa: BLE001 - errors go back to the model
                content, is_error = f"Error: {err}", True
            all_lines = content.splitlines()
            first = all_lines[0] if all_lines else ""
            print(Color.dim(f"    -> {first[:70]}" +
                            (f"  ({len(all_lines)} lines)" if len(all_lines) > 1 else "")))
            if name == "run_command":  # show the start of command output
                for line in all_lines[1:4]:
                    print(Color.dim(f"       {line[:90]}"))
        self.log({"type": "tool", "tool": name, "target": self.describe(name, inp)[:160],
                  "decision": decision, "source": source,
                  "result_chars": len(content), "duration_ms": int((time.time() - start) * 1000)})
        result = {"type": "tool_result", "tool_use_id": block["id"], "content": content}
        if is_error:
            result["is_error"] = True
        return result

    # ---- the agent loop -----------------------------------------------------
    def run_turn(self, user_text: str):
        print(Color.blue(f"> {user_text}"))
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(self.args.max_steps):
            self.compact()
            self.request_index += 1
            if self.args.show_requests:
                print(Color.dim(json.dumps({"system": self.system[:200] + "...",
                                            "tools": [t["name"] for t in TOOL_DEFINITIONS],
                                            "messages": self.messages}, indent=2)))
            start = time.time()
            try:
                response = self.backend.complete(self.system, TOOL_DEFINITIONS, self.messages)
            except BackendError as err:
                print(Color.red(f"  [backend error] {err}"))
                self.messages.pop() if self.messages[-1]["role"] == "user" else None
                return
            usage = response["usage"]
            tool_calls = [b for b in response["content"] if b["type"] == "tool_use"]
            self.log({"type": "api_request", "request": self.request_index,
                      "backend": self.backend.name, "model": self.backend.model,
                      "estimated": response["estimated"], "messages": len(self.messages),
                      "tool_calls": [b["name"] for b in tool_calls],
                      "duration_ms": int((time.time() - start) * 1000), **usage})
            for block in response["content"]:
                if block["type"] == "text" and block["text"].strip():
                    print("• " + block["text"].strip().replace("\n", "\n  "))
            self.messages.append({"role": "assistant", "content": response["content"]})
            self.print_status(usage, response["estimated"])
            if not tool_calls:
                return
            results = [self.execute(b) for b in tool_calls]
            self.messages.append({"role": "user", "content": results})
        print(Color.yellow(f"  [stopped after {self.args.max_steps} steps]"))

    def print_status(self, usage, estimated):
        context = usage["input_tokens"] + usage["cache_read_tokens"] + usage["cache_write_tokens"]
        pct = 100 * context / self.args.context_limit
        flag = " (estimated)" if estimated else ""
        print(Color.dim(f"  context: {pct:.0f}% of {self.args.context_limit} tokens{flag}"
                        f"  ·  request {self.request_index}"))

    # ---- interactive commands -----------------------------------------------
    def show_usage(self):
        reqs = [r for r in self.records if r["type"] == "api_request"]
        tot = {k: sum(r[k] for r in reqs) for k in
               ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")}
        print(f"  requests: {len(reqs)}   " + "   ".join(f"{k}: {v}" for k, v in tot.items()))
        print(Color.dim(f"  full log: {self.log_path}"))

    def show_context(self):
        sizes = {"system prompt": estimate_tokens(self.system),
                 "tool definitions": estimate_tokens(TOOL_DEFINITIONS)}
        conv = res = 0
        for msg in self.messages:
            if isinstance(msg["content"], str):
                conv += estimate_tokens(msg["content"])
                continue
            for b in msg["content"]:
                if b["type"] == "tool_result":
                    res += estimate_tokens(b["content"])
                else:
                    conv += estimate_tokens(b)
        sizes["messages"] = conv
        sizes["tool results"] = res
        total = sum(sizes.values())
        for k, v in sizes.items():
            print(f"  {k:<17} ~{v:>6} tokens  {100 * v / max(total, 1):5.1f}%")
        print(f"  {'total':<17} ~{total:>6} tokens  of {self.args.context_limit} limit")

    def banner(self):
        print(Color.yellow("mini-harness") + Color.dim(f"  session {self.session_id}"))
        print(f"  model:   {self.backend.model} ({self.backend.name})")
        print(f"  cwd:     {self.workdir}")
        print(f"  loaded:  {', '.join(self.loaded_files) or 'no instructions file'}")
        print(f"  policy:  {self.policy.path or 'none (ask for everything)'}"
              f"  · default mode: {self.policy.mode}")

    def repl(self):
        print(Color.dim("  commands: /usage /context /clear /quit"))
        while True:
            try:
                text = input(Color.blue("> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not text:
                continue
            if text == "/quit":
                return
            if text == "/usage":
                self.show_usage()
            elif text == "/context":
                self.show_context()
            elif text == "/clear":
                self.messages.clear()
                print(Color.dim("  conversation cleared; system prompt and tools remain"))
            else:
                self.run_turn(text)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--workdir", required=True, help="repository the agent works in")
    p.add_argument("--backend", choices=["mock", "anthropic", "openai"], default="mock")
    p.add_argument("--scenario", help="mock backend: scripted responses (JSON)")
    p.add_argument("--base-url", default=os.environ.get("MINI_HARNESS_BASE_URL"),
                   help="model endpoint base, e.g. https://llm.internal/v1")
    p.add_argument("--model", default=os.environ.get("MINI_HARNESS_MODEL"))
    p.add_argument("--api-key", default=os.environ.get("MINI_HARNESS_API_KEY"))
    p.add_argument("--auth-style", choices=["x-api-key", "bearer"])
    p.add_argument("--ca-file", default=os.environ.get("MINI_HARNESS_CA_FILE"),
                   help="PEM bundle for an internal certificate authority")
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--policy", default=str(HERE / "policies" / "default.json"))
    p.add_argument("--prompt", help="run one request and exit (otherwise interactive)")
    p.add_argument("--context-limit", type=int, default=32000)
    p.add_argument("--max-steps", type=int, default=25)
    p.add_argument("--log", help="usage log path (default: <workdir>/.mini-harness/usage.jsonl)")
    p.add_argument("--show-requests", action="store_true", help="print each request body")
    p.add_argument("--no-color", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.no_color:
        Color.enabled = False
    harness = Harness(args)
    harness.banner()
    if args.prompt:
        harness.run_turn(args.prompt)
    else:
        harness.repl()


if __name__ == "__main__":
    main()
