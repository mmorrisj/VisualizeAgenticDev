"""Scripted harness sessions for the mock models (spec phase L3).

Each session is a fixed script of tool calls, picked by the model's
`mock_quality` and the harness variant. The step is the number of assistant
turns so far, so the script does not read tool results. It mimics the pattern
predictions P6 to P8 describe, but it is a script, not evidence: results are
labelled synthetic.

- high: explores the working directory, explores more when the discoverable
  facts were not given, then delivers the good answer if the private facts
  were given and a bad answer otherwise. Exploration cannot recover private facts.
- low: starts with a failed tool call. Given everything (h-full) it gets there
  in more requests. Given only the discoverable facts it delivers a bad answer.
  Without the discoverable facts it never settles and lists files until the
  session hits its request limit.
"""

from __future__ import annotations

import time

from ..config import ModelConfig
from ..extract import extract
from ..tokens import NOT_REPORTED, Usage, estimate_tokens
from .base import BackendError, Request, Response

PRIVATE_GIVEN = {"h-full", "h-discoverable-gap"}
DISCOVERABLE_GIVEN = {"h-full", "h-private-gap"}
HEREDOC_END = "PROMPTLAB_EOF"


def _tool(name: str, inp: dict, say: str) -> tuple:
    return ("tool", name, inp, say)


def _deliver(task, answer: str) -> list[tuple]:
    spec = task.spec.harness.deliverable
    if spec.kind == "message":
        return [("text", answer)]
    path = spec.path if spec.kind == "file" else f"test_{next(iter(task.spec.harness.files))}"
    code = extract(answer, "python")
    command = f"cat > {path} <<'{HEREDOC_END}'\n{code}{HEREDOC_END}"
    return [_tool("run_command", {"command": command, "description": f"write {path}"}, f"Writing {path}."),
            ("text", f"Done: I wrote {path}.")]


def script(task, variant: str, quality: str | None) -> list[tuple]:
    harness = task.spec.harness
    explore = [_tool("list_files", {"path": "."}, "Let me see what is here.")]
    explore += [_tool("read_file", {"path": f}, f"Reading {f}.") for f in harness.files]
    if harness.database:
        explore.append(_tool("run_sql", {"query": "SELECT * FROM services"}, "Checking the services table."))
    if harness.database:
        extra = [_tool("run_sql", {"query": "SELECT DISTINCT severity FROM incidents"}, "How is severity stored?"),
                 _tool("run_sql", {"query": "SELECT COUNT(*) FROM incidents WHERE duplicate_of IS NOT NULL"},
                       "Are there duplicates?")]
    else:
        extra = [_tool("search", {"pattern": "def |^#"}, "Looking for structure."),
                 _tool("run_command", {"command": "ls -la", "description": "list files with sizes"},
                       "Checking file sizes.")]
    bad = next(name for name in task.answers() if name.startswith("bad"))
    if quality == "high":
        steps = explore + ([] if variant in DISCOVERABLE_GIVEN else extra)
        return steps + _deliver(task, task.answer("good" if variant in PRIVATE_GIVEN else bad))
    fail = _tool("read_file", {"path": "README.md"}, "Reading the README first.")
    if variant == "h-full":
        return [fail] + explore + extra + _deliver(task, task.answer("good"))
    if variant == "h-private-gap":
        return [fail] + explore + _deliver(task, task.answer(bad))
    return [fail, _tool("list_files", {"path": "."}, "Let me look again.")]  # repeats until the limit


def respond(task, request: Request, model: ModelConfig) -> Response:
    if task.spec.harness is None:
        raise BackendError(f"task {task.id} has no harness block")
    start = time.perf_counter()
    steps = script(task, request.meta.get("variant", ""), model.mock_quality)
    step = sum(1 for m in request.messages if m["role"] == "assistant")
    item = steps[min(step, len(steps) - 1)]
    if item[0] == "text":
        content = [{"type": "text", "text": item[1]}]
    else:
        _, name, inp, say = item
        content = [{"type": "text", "text": say},
                   {"type": "tool_use", "id": f"mock_{step}", "name": name, "input": inp}]
    usage = Usage(input=estimate_tokens({"system": request.system, "tools": request.tools,
                                         "messages": request.messages}),
                  output=estimate_tokens(content), reasoning=NOT_REPORTED, cache_read=0, cache_write=0,
                  synthetic=True)
    stop = "tool_use" if content[-1]["type"] == "tool_use" else "end"
    text = "".join(b["text"] for b in content if b["type"] == "text")
    return Response(text=text, usage=usage, stop=stop, latency_s=time.perf_counter() - start,
                    served_model=f"mock:{model.id}", content=content)
