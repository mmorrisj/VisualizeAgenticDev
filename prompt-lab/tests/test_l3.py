"""Phase L3: tool calls in the backends, harness sessions through mini-harness, limits, accounting."""

import json
import sqlite3
import subprocess
import sys

import httpx
import httpx2
import pytest
from sqlalchemy import create_engine, inspect, text

from promptlab import study
from promptlab.backends import BackendError, Request, Response
from promptlab.backends.openai_compat import OpenAICompatBackend, to_openai_messages
from promptlab.config import ModelConfig, load_models
from promptlab.harness_adapter import (HARNESS_VARIANTS, MINI_HARNESS_DIR, Limits, build_workdir,
                                       load_mini_harness, run_session, run_sql, sum_usage)
from promptlab.profiles import HarnessSettings, Profile, load_profile
from promptlab.store import Store
from promptlab.tasks import load_task, task_ids
from promptlab.tokens import INCLUDED_IN_OUTPUT, NOT_REPORTED, Usage

from test_backends import anthropic_backend, sse


@pytest.fixture()
def store(tmp_path):
    return Store(f"sqlite:///{tmp_path / 'lab.db'}")


@pytest.fixture()
def models():
    return load_models()


def real_model(**kw):
    base = dict(id="real", display="Real", gateway_id="gw-real", family="f", generation=1, api="openai_compat",
                base_url_env="TEST_GATEWAY_URL", api_key_env="TEST_GATEWAY_KEY")
    base.update(kw)
    return ModelConfig(**base)


TOOLS = [{"name": "read_file", "description": "Read a file.",
          "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}]


# --- tool calls in the backends ------------------------------------------------------

def test_openai_converts_the_harness_conversation():
    messages = [
        {"role": "user", "content": "fix it"},
        {"role": "assistant", "content": [{"type": "text", "text": "Looking."},
                                          {"type": "tool_use", "id": "c1", "name": "read_file", "input": {"path": "a"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "x = 1",
                                      "is_error": False}]},
    ]
    out = to_openai_messages(messages)
    assert out[0] == {"role": "user", "content": "fix it"}
    assert out[1]["tool_calls"][0]["function"] == {"name": "read_file", "arguments": '{"path": "a"}'}
    assert out[2] == {"role": "tool", "tool_call_id": "c1", "content": "x = 1"}


def test_openai_sends_tools_and_parses_tool_calls(monkeypatch):
    monkeypatch.setenv("TEST_GATEWAY_URL", "https://gw.internal/v1")
    seen = {}
    reply = {"model": "gw", "usage": {"prompt_tokens": 30, "completion_tokens": 4},
             "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
                 {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}},
                 {"id": "c2", "type": "function", "function": {"name": "read_file", "arguments": "{not json"}}]}}]}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=reply)

    backend = OpenAICompatBackend(client=httpx.Client(transport=httpx.MockTransport(handler)))
    resp = backend.complete(Request(messages=[{"role": "user", "content": "go"}], system="s", tools=TOOLS), real_model())
    assert seen["body"]["tools"][0]["function"]["parameters"] == TOOLS[0]["input_schema"]
    assert resp.stop == "tool_use" and resp.text == ""
    assert resp.tool_calls[0] == {"type": "tool_use", "id": "c1", "name": "read_file", "input": {"path": "a.py"}}
    assert resp.tool_calls[1]["input"] == {"_unparseable_arguments": "{not json"}  # kept, so it counts as a failed call


def test_anthropic_tool_use_round_trips():
    message = {"id": "m", "type": "message", "role": "assistant", "model": "claude-opus-5", "content": [],
               "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 50, "output_tokens": 1}}
    body = sse(
        ("message_start", {"type": "message_start", "message": message}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "input_json_delta", "partial_json": '{"path": "b.py"}'}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                           "usage": {"output_tokens": 9}}),
        ("message_stop", {"type": "message_stop"}),
    )
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, text=body, headers={"content-type": "text/event-stream"})

    resp = anthropic_backend(handler).complete(Request(messages=[{"role": "user", "content": "go"}], tools=TOOLS),
                                               real_model(api="anthropic"))
    assert seen["body"]["tools"] == TOOLS
    assert resp.stop == "tool_use"
    assert resp.content == [{"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "b.py"}}]


# --- the course harness ---------------------------------------------------------------------

def test_mini_harness_loads_without_leaking_its_module_names():
    mini = load_mini_harness()
    assert hasattr(mini, "Harness") and "backends" not in sys.modules


def test_mini_harness_still_runs_on_its_own(tmp_path):
    """The course harness must behave as before for students (its own CLI and mock scenarios)."""
    (tmp_path / "src").mkdir()
    result = subprocess.run([sys.executable, str(MINI_HARNESS_DIR / "harness.py"), "--workdir", str(tmp_path),
                             "--backend", "mock", "--scenario", str(MINI_HARNESS_DIR / "scenarios" / "investigate.json"),
                             "--prompt", "why is the login test failing?", "--no-color"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "request 5" in result.stdout


# --- working directories and run_sql -------------------------------------------------------------

def test_every_task_has_a_harness_block_and_four_variants():
    for tid in task_ids():
        task = load_task(tid)
        assert task.spec.harness is not None
        assert tuple(sorted(task.harness_variants())) == tuple(sorted(HARNESS_VARIANTS))
        assert not set(task.harness_variants()) & set(task.variants())  # one-shot runs never pick these up


def test_workdir_has_the_inputs_and_never_the_hidden_files(tmp_path):
    for tid in task_ids():
        work = build_workdir(load_task(tid), tmp_path / tid)
        names = {p.relative_to(work).as_posix() for p in work.rglob("*") if p.is_file()}
        assert names == set(load_task(tid).spec.harness.files) | (
            {"incidents.db"} if tid == "data-question" else set())


def test_run_sql_is_read_only_and_bounded(tmp_path):
    work = build_workdir(load_task("data-question"), tmp_path / "w")
    db = work / "incidents.db"
    assert run_sql(db, "SELECT COUNT(*) AS n FROM services").splitlines()[0] == "n"
    with pytest.raises(sqlite3.Error):
        run_sql(db, "DELETE FROM incidents")
    with pytest.raises(sqlite3.Error):
        run_sql(db, "SELECT 1; SELECT 2")
    many = run_sql(db, "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n LIMIT 500) SELECT i FROM n")
    assert many.endswith("(first 200 rows shown)") and len(many.splitlines()) == 202
    with pytest.raises(sqlite3.Error):  # the step limit stops runaway queries
        run_sql(db, "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT COUNT(*) FROM n")


# --- sessions on the mock models -------------------------------------------------------------------

@pytest.mark.parametrize("task_id", ["data-question", "refactor", "summarize", "write-tests"])
def test_sessions_run_end_to_end_and_are_checked(task_id, store, models):
    good = run_session(task_id, "h-full", models["mock-new"], store=store)
    blind = run_session(task_id, "h-private-gap", models["mock-new"], store=store)
    assert good.status == "ok" and good.stop == "finished" and good.score == 1.0 and good.mode == "harness"
    assert blind.status == "ok" and blind.score < 1.0  # exploring cannot recover what only the user knows
    saved = store.runs(id=good.id)[0]
    assert saved.label == "synthetic" and saved.requests == len(saved.session["per_request"]) > 1
    assert saved.session["tool_calls"] == saved.requests - 1 and saved.session["tool_calls_failed"] == 0


def test_request_limit_ends_the_session_as_a_failure(store, models):
    run = run_session("refactor", "h-terse", models["mock-old"], store=store)
    assert (run.status, run.stop, run.score, run.requests) == ("hit_limit", "hit limit", 0.0, 25)
    assert run.session["limits"]["hit"] == "25 requests"
    assert "hit its limit" in run.check_details["scored_as_failure"]
    assert run.session["tool_calls_failed"] == 1  # mock-old reads a README that is not there


def test_input_token_limit_ends_the_session(store, models):
    run = run_session("summarize", "h-full", models["mock-old"], store=store, limits=Limits(max_input_tokens=2000))
    assert run.status == "hit_limit" and run.session["limits"]["hit"] == "2000 input tokens"
    assert run.session["limits"]["input_tokens_counted"] >= 2000
    before_last = sum(r["input"] for r in run.session["per_request"][:-1])
    assert before_last < 2000  # the last request was allowed because the total was still under the limit


def test_per_request_accounting(store, models):
    run = run_session("data-question", "h-discoverable-gap", models["mock-new"], store=store)
    per = run.session["per_request"]
    assert [r["request"] for r in per] == list(range(1, len(per) + 1))
    assert sum(r["input"] for r in per) == run.tokens["input"]
    assert {k: sum(r["split"][k] for r in per) for k in ("fixed", "conversation", "tool_results")} == run.tokens["split"]
    assert per[0]["split"]["tool_results"] == 0 and per[-1]["split"]["tool_results"] > 0
    assert "run_sql" in run.session["tools_used"] and run.session["final_message"].startswith(run.output.strip()[:20])


class Scripted:
    """A real-model-shaped backend: replies in order and does not report input tokens."""

    def __init__(self, *contents, fail_at=None):
        self.contents, self.fail_at, self.calls = list(contents), fail_at, 0

    def complete(self, request, model):
        self.calls += 1
        if self.calls == self.fail_at:
            raise BackendError("gateway down")
        content = self.contents.pop(0)
        return Response(text="", usage=Usage(input=NOT_REPORTED, output=5, reasoning=INCLUDED_IN_OUTPUT),
                        stop="tool_use" if any(b["type"] == "tool_use" for b in content) else "end",
                        latency_s=0.01, content=content)


def tool(name, inp, i):
    return [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]


def test_failed_tool_calls_and_unreported_tokens(store):
    backend = Scripted(tool("no_such_tool", {}, 1), tool("read_file", {"_unparseable_arguments": "{"}, 2),
                       tool("read_file", {"path": "billing.py"}, 3), [{"type": "text", "text": "done"}])
    run = run_session("refactor", "h-terse", real_model(), store=store, backend=backend)
    assert run.status == "ok" and run.label == "checked" and run.requests == 4
    assert run.session["tool_calls"] == 3 and run.session["tool_calls_failed"] == 2
    assert run.tokens["input"] == NOT_REPORTED and run.tokens["output"] == 20
    assert run.tokens["reasoning"] == INCLUDED_IN_OUTPUT
    assert run.session["limits"]["counted_from"] == "estimated"  # the limit still works, and says how
    assert run.score < 1.0  # billing.py was never changed


def test_backend_error_mid_session_is_stored(store):
    backend = Scripted(tool("list_files", {}, 1), fail_at=2)
    run = run_session("summarize", "h-full", real_model(), store=store, backend=backend)
    saved = store.runs(id=run.id)[0]
    assert saved.status == "error" and saved.score is None and "gateway down" in saved.error
    assert saved.requests == 1 and saved.stop == "error"


def test_no_new_test_file_scores_zero(store):
    backend = Scripted([{"type": "text", "text": "Here are some tests: ```python\nassert True\n```"}])
    run = run_session("write-tests", "h-full", real_model(), store=store, backend=backend)
    assert run.session["deliverable"] == "no new files" and run.score == 0.0


def test_sum_usage_never_reports_a_partial_sum():
    a = Usage(input=10, output=5, reasoning=INCLUDED_IN_OUTPUT, cache_read=0, cache_write=NOT_REPORTED)
    b = Usage(input=NOT_REPORTED, output=6, reasoning=INCLUDED_IN_OUTPUT, cache_read=3, cache_write=NOT_REPORTED)
    total = sum_usage([a, b])
    assert (total.input, total.output, total.reasoning, total.cache_read, total.cache_write) == (
        NOT_REPORTED, 11, INCLUDED_IN_OUTPUT, 3, NOT_REPORTED)
    assert sum_usage([]).input == NOT_REPORTED


# --- storage, profiles, study -------------------------------------------------------------------

def test_store_adds_the_session_column_to_an_older_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:  # the L2 schema, before `session` existed
        conn.execute(text("CREATE TABLE runs (id INTEGER PRIMARY KEY, task VARCHAR(64), variant VARCHAR(64), "
                          "model VARCHAR(64), status VARCHAR(16))"))
    Store(url)
    assert "session" in {c["name"] for c in inspect(engine).get_columns("runs")}


def test_profiles_with_harness_settings(models):
    study_profile = load_profile("study")
    assert study_profile.harness.repeats == 3 and study_profile.harness_models() == study_profile.models
    assert (study_profile.harness.max_requests, study_profile.harness.max_input_tokens) == (25, 60_000)
    assert load_profile("class").harness is None
    for name in ("study", "class", "mock-study"):
        load_profile(name).check_models(models)


def test_study_runs_judges_and_exports_harness_sessions(tmp_path, models):
    store = Store(f"sqlite:///{tmp_path / 's.db'}")
    profile = Profile(name="h", tasks=["data-question"], variants=["terse"], models=["mock-old", "mock-new"],
                      harness=HarnessSettings(tasks=["data-question", "refactor"]))
    first = study.run_study(profile, models, store)
    assert first["ran"] == 2 + 2 * 4 * 2 and first["missing_variants"] == []
    assert study.run_study(profile, models, store)["ran"] == 0  # resumable
    harness_runs = [r for r in store.runs(profile="h") if r.mode == "harness"]
    assert len(harness_runs) == 16 and sum(r.status == "hit_limit" for r in harness_runs) == 4

    from promptlab.profiles import JudgeSettings
    profile.judge = JudgeSettings(primary="mock-judge")
    judged = study.judge_study(profile, models, store)["judged"]
    assert judged == 2 + 12  # sessions that hit their limit are not judged

    path = study.export(profile, models, store, out_dir=tmp_path / "results", created="2026-12-01")
    data = json.loads(path.read_text())
    session = next(r for r in data["runs"] if r["mode"] == "harness")["session"]
    assert {"stop", "limits", "tool_calls", "tool_calls_failed", "per_request", "transcript_ref"} <= set(session)
    transcript = json.loads((tmp_path / "results" / session["transcript_ref"]).read_text())
    assert transcript[0]["role"] == "user"
    readings = {p["id"]: p for p in data["predictions"]}
    for pid in ("P6", "P7", "P8"):
        assert readings[pid]["outcome"] == "supported" and readings[pid]["n"] > 0  # the mock script's pattern
