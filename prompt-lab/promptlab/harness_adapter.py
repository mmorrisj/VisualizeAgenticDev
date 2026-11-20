"""Harness mode (spec section 6.2): drive the course's mini-harness for any configured model.

One session:

1. builds a fresh working directory from the task's `harness:` block in task.yaml;
2. runs mini-harness's own loop, tools and system prompt, so only the model
   changes between sessions. Tasks with a database get one extra tool, run_sql,
   which is read-only;
3. ends at the limits: 25 requests or 60,000 input tokens per session. Reaching
   either is recorded as "hit limit" and scored as a failure;
4. runs the task's checks on what the session left behind (a file it edited,
   test files it created, or its final message).

Model requests go through the lab's own backends, so retries, credentials,
effort and token normalization are the same as in one-shot mode. Every request
is recorded with its reported usage and an estimated split of its input into
fixed overhead (system prompt and tool definitions), conversation, and tool
results, the split the site's token pages draw.
"""

from __future__ import annotations

import contextlib
import fnmatch
import importlib.util
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from . import CONFIG_DIR, LAB_ROOT
from .backends import BackendError, Request, backend_for
from .config import ModelConfig
from .store import Run, Store
from .tasks import Task, load_task
from .tokens import NOT_REPORTED, Usage, estimate_tokens

MINI_HARNESS_DIR = LAB_ROOT.parent / "course" / "mini-harness"
POLICY = CONFIG_DIR / "harness-policy.json"
HARNESS_VARIANTS = ("h-terse", "h-discoverable-gap", "h-private-gap", "h-full")
SPLIT_BASIS = "estimated: about 4 characters per token, from the request text"
IGNORED_PARTS = {".mini-harness", "__pycache__", ".git"}
CONSOLE_TAIL = 20_000  # characters of the harness's console output kept per session

SQL_ROW_LIMIT = 200
SQL_STEP_LIMIT = 2_000_000  # SQLite VM steps; stops runaway queries

RUN_SQL_TOOL = {
    "name": "run_sql",
    "description": "Run one read-only SQL query against the SQLite database in the working directory "
                   f"and return the rows (at most {SQL_ROW_LIMIT}).",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
}


@dataclass(frozen=True)
class Limits:
    max_requests: int = 25
    max_input_tokens: int = 60_000


# --- loading the course harness -------------------------------------------------------

_MINI_HARNESS = None


def load_mini_harness():
    """Import course/mini-harness/harness.py without leaving its folder on sys.path.

    harness.py does `from backends import ...`, so its backends.py is visible as
    `backends` only while harness.py is being imported.
    """
    global _MINI_HARNESS
    if _MINI_HARNESS is not None:
        return _MINI_HARNESS
    if not (MINI_HARNESS_DIR / "harness.py").is_file():
        raise FileNotFoundError(f"mini-harness not found at {MINI_HARNESS_DIR}")

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    backends = load("promptlab_mini_harness_backends", MINI_HARNESS_DIR / "backends.py")
    previous = sys.modules.get("backends")
    sys.modules["backends"] = backends
    try:
        _MINI_HARNESS = load("promptlab_mini_harness", MINI_HARNESS_DIR / "harness.py")
    finally:
        if previous is None:
            sys.modules.pop("backends", None)
        else:
            sys.modules["backends"] = previous
    return _MINI_HARNESS


# --- the working directory ----------------------------------------------------------------

def build_workdir(task: Task, dest: Path) -> Path:
    spec = task.spec.harness
    if spec is None:
        raise ValueError(f"task {task.id} has no harness block in task.yaml")
    dest.mkdir(parents=True, exist_ok=True)
    for target, source in spec.files.items():
        path = dest / target
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(task.path(*PurePosixPath(source).parts), path)
    if spec.database:
        db = sqlite3.connect(dest / spec.database.path)
        try:
            for script in spec.database.scripts:
                db.executescript(task.read(*PurePosixPath(script).parts))
            db.commit()
        finally:
            db.close()
    return dest


def snapshot(workdir: Path) -> set[str]:
    return {p.relative_to(workdir).as_posix() for p in workdir.rglob("*")
            if p.is_file() and not IGNORED_PARTS & set(p.relative_to(workdir).parts)}


def run_sql(database: Path, query: str) -> str:
    """One read-only query. Errors are raised; the harness returns them to the model."""
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only = ON")
    steps = {"n": 0}

    def guard():
        steps["n"] += 1
        return 1 if steps["n"] > SQL_STEP_LIMIT // 1000 else 0

    db.set_progress_handler(guard, 1000)
    try:
        cursor = db.execute(query)
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(SQL_ROW_LIMIT + 1)
    finally:
        db.close()
    if not columns:
        return "(the statement returned no rows)"
    lines = ["\t".join(columns)] + ["\t".join("NULL" if v is None else str(v) for v in row)
                                    for row in rows[:SQL_ROW_LIMIT]]
    if len(rows) > SQL_ROW_LIMIT:
        lines.append(f"(first {SQL_ROW_LIMIT} rows shown)")
    return "\n".join(lines)


def collect_deliverable(task: Task, workdir: Path, before: set[str], final_message: str) -> tuple[str, str]:
    """(text for the task's checks, what it came from)."""
    spec = task.spec.harness.deliverable
    if spec.kind == "message":
        return final_message, "final message"
    if spec.kind == "file":
        path = workdir / spec.path
        return (_fence(path.read_text(encoding="utf-8", errors="replace")) if path.is_file() else ""), spec.path
    new = sorted(rel for rel in snapshot(workdir) - before
                 if fnmatch.fnmatch(PurePosixPath(rel).name, spec.pattern or "*"))
    if not new:
        return "", "no new files"
    text = "\n\n".join((workdir / rel).read_text(encoding="utf-8", errors="replace").rstrip() for rel in new)
    return _fence(text), ", ".join(new)


def _fence(code: str) -> str:
    return f"```python\n{code.rstrip()}\n```\n"


# --- accounting -------------------------------------------------------------------------------

def split_input(system: str, tools: list, messages: list) -> dict:
    """Estimated split of one request's input, as the harness's /context command draws it."""
    conversation = tool_results = 0
    for msg in messages:
        if isinstance(msg["content"], str):
            conversation += estimate_tokens(msg["content"])
            continue
        for block in msg["content"]:
            if block.get("type") == "tool_result":
                tool_results += estimate_tokens(block["content"])
            else:
                conversation += estimate_tokens(block)
    return {"fixed": estimate_tokens(system) + estimate_tokens(tools),
            "conversation": conversation, "tool_results": tool_results}


def sum_usage(usages: list[Usage]) -> Usage:
    """Session totals. A field is summed only if every request reported it; a partial sum
    would look like a real count, so a gap makes the whole field "not reported"."""
    total = Usage(synthetic=any(u.synthetic for u in usages))
    for name in ("input", "output", "reasoning", "cache_read", "cache_write"):
        values = [getattr(u, name) for u in usages]
        if values and all(isinstance(v, int) for v in values):
            setattr(total, name, sum(values))
        elif values and len(set(values)) == 1:
            setattr(total, name, values[0])  # every request has the same label
        else:
            setattr(total, name, NOT_REPORTED)
    return total


class SessionModel:
    """Sits between mini-harness and a lab backend: enforces the limits and records each request.

    mini-harness calls complete(system, tools, messages) and expects its own
    response shape; that conversion happens here.
    """

    name = "prompt-lab"

    def __init__(self, model: ModelConfig, backend, limits: Limits, meta: dict, course_error):
        self.config, self.backend, self.limits, self.meta = model, backend, limits, meta
        self.model = model.gateway_id
        self.course_error = course_error
        self.records: list[dict] = []
        self.usages: list[Usage] = []
        self.input_total = 0
        self.limit_basis = "reported"
        self.stop: str | None = None   # set when the session ends early: "hit limit" or "error"
        self.limit_hit = ""
        self.error = ""
        self.chars_sent = self.chars_received = 0
        self.last_stop = ""
        self.served_model = ""

    def _end(self, stop: str, why: str):
        self.stop = stop
        if stop == "hit limit":
            self.limit_hit = why
        else:
            self.error = why
        raise self.course_error(why)

    def complete(self, system: str, tools: list, messages: list) -> dict:
        if len(self.records) >= self.limits.max_requests:
            self._end("hit limit", f"{self.limits.max_requests} requests")
        if self.input_total >= self.limits.max_input_tokens:
            self._end("hit limit", f"{self.limits.max_input_tokens} input tokens")
        body = {"system": system, "tools": tools, "messages": messages}
        request = Request(messages=json.loads(json.dumps(messages)), system=system, tools=tools,
                          meta={**self.meta, "role": "harness"})
        try:
            response = self.backend.complete(request, self.config)
        except BackendError as err:
            self._end("error", str(err))
        usage = response.usage
        reported = usage.total_input()
        if reported is None:
            # The limit still has to work; the estimate is used only for that and is labelled.
            reported = estimate_tokens(body)
            self.limit_basis = "estimated"
        self.input_total += reported
        content = response.content or ([{"type": "text", "text": response.text}] if response.text else [])
        calls = [b for b in content if b.get("type") == "tool_use"]
        sent, received = len(json.dumps(body)), len(json.dumps(content))
        self.chars_sent += sent
        self.chars_received += received
        self.last_stop, self.served_model = response.stop, response.served_model or self.served_model
        self.usages.append(usage)
        self.records.append({
            "request": len(self.records) + 1,
            **{k: v for k, v in usage.to_dict().items() if k != "synthetic"},
            "split": split_input(system, tools, messages),
            "chars": {"sent": sent, "received": received},
            "tool_calls": [b["name"] for b in calls],
            "stop": response.stop,
            "latency_s": round(response.latency_s, 3),
        })

        def count(value):
            return value if isinstance(value, int) else 0

        return {"content": content, "stop_reason": "tool_use" if calls else "end_turn",
                "usage": {"input_tokens": count(usage.input), "output_tokens": count(usage.output),
                          "cache_read_tokens": count(usage.cache_read), "cache_write_tokens": count(usage.cache_write)},
                "estimated": usage.synthetic}


def _lab_harness_class(mini):
    class LabHarness(mini.Harness):
        """mini-harness, unattended, with run_sql for tasks that have a database."""

        def __init__(self, args, backend, database: Path | None):
            super().__init__(args, backend=backend)
            self.database = database
            if database is not None:
                self.tools.append(RUN_SQL_TOOL)
            self.calls = Counter()
            self.failed_calls = 0

        def ask_user(self, name, inp, reason):
            return "deny", "prompt-lab", "this session runs unattended; nobody can approve it"

        def execute(self, block):
            result = super().execute(block)
            self.calls[block["name"]] += 1
            self.failed_calls += bool(result.get("is_error"))
            return result

        def tool_run_sql(self, inp):
            if self.database is None:
                raise ValueError("this task has no database")
            return run_sql(self.database, inp["query"])

    return LabHarness


def _final_message(messages: list) -> str:
    for msg in reversed(messages):
        if msg["role"] == "assistant" and isinstance(msg["content"], list):
            if any(b.get("type") == "tool_use" for b in msg["content"]):
                return ""
            return "".join(b.get("text", "") for b in msg["content"] if b.get("type") == "text").strip()
    return ""


# --- one session ----------------------------------------------------------------------------------

def run_session(task_id: str, variant: str, model: ModelConfig, *, repeat: int = 1, profile: str = "adhoc",
                store: Store | None = None, backend=None, limits: Limits = Limits(),
                keep_dir: Path | None = None) -> Run:
    """Run one harness session, check what it left behind, and store it as a run (mode "harness")."""
    task = load_task(task_id)
    prompt = task.harness_prompt(variant)
    run = Run(profile=profile, mode="harness", task=task_id, variant=variant, model=model.id,
              gateway_id=model.gateway_id, repeat=repeat, effort=model.effort or "", prompt=prompt)
    mini = load_mini_harness()
    session_model = SessionModel(model, backend or backend_for(model), limits,
                                 {"task": task_id, "variant": variant}, mini.BackendError)
    console = io.StringIO()
    with tempfile.TemporaryDirectory(prefix=f"promptlab-{task_id}-") as tmp:
        workdir = build_workdir(task, Path(tmp) / "work")
        before = snapshot(workdir)
        database = workdir / task.spec.harness.database.path if task.spec.harness.database else None
        args = SimpleNamespace(workdir=str(workdir), policy=str(POLICY), log=str(Path(tmp) / "usage.jsonl"),
                               context_limit=model.context_window or 200_000,
                               max_steps=limits.max_requests + 1,  # the request limit ends the loop, not this
                               show_requests=False)
        harness = _lab_harness_class(mini)(args, session_model, database)
        start = time.perf_counter()
        with contextlib.redirect_stdout(console):
            harness.run_turn(prompt)
        run.latency_s = round(time.perf_counter() - start, 3)
        final = _final_message(harness.messages)
        answer, source = collect_deliverable(task, workdir, before, final)
        if keep_dir is not None:
            shutil.copytree(workdir, keep_dir / run.key, dirs_exist_ok=True)

    stop = session_model.stop or "finished"
    usage = sum_usage(session_model.usages)
    split = {part: sum(r["split"][part] for r in session_model.records)
             for part in ("fixed", "conversation", "tool_results")}
    run.tokens = {**usage.to_dict(), "split": split, "split_basis": SPLIT_BASIS}
    run.requests = len(session_model.records)
    run.stop = stop
    run.served_model = session_model.served_model
    run.chars_sent, run.chars_received = session_model.chars_sent, session_model.chars_received
    run.output = answer
    run.error = session_model.error
    run.session = {
        "stop": stop,
        "limits": {"max_requests": limits.max_requests, "max_input_tokens": limits.max_input_tokens,
                   "hit": session_model.limit_hit or None, "input_tokens_counted": session_model.input_total,
                   "counted_from": session_model.limit_basis},
        "tool_calls": sum(harness.calls.values()),
        "tool_calls_failed": harness.failed_calls,
        "tools_used": dict(harness.calls),
        "deliverable": source,
        "final_message": final,
        "per_request": session_model.records,
        "messages": harness.messages,
        "console": console.getvalue()[-CONSOLE_TAIL:],
    }
    if stop == "error":
        run.status, run.label = "error", "error"
    else:
        result = json.loads(json.dumps(task.check(answer).to_dict(), default=str))
        run.label = "synthetic" if usage.synthetic else "checked"
        if stop == "hit limit":
            run.status, run.score = "hit_limit", 0.0
            run.check_details = {**result, "scored_as_failure": f"the session hit its limit ({session_model.limit_hit})"}
        else:
            run.status = "refused" if session_model.last_stop == "refusal" else "ok"
            run.score, run.check_details = result["score"], result
    return (store or Store()).add(run)
