"""Phase L4: the app (class kit, bring your own test, collector), replay mode, and part C's engine."""

import io
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from promptlab import assess, byot, study
from promptlab.app import create_app
from promptlab.app.settings import Settings
from promptlab.config import load_models
from promptlab.custom_checks import CustomCheck, run_check
from promptlab.harness_adapter import run_session
from promptlab.profiles import HarnessSettings, Profile
from promptlab.runner import run_parallel
from promptlab.store import CustomTest, Store

LONG_PROMPT = ("Summarize the attached release notes for the support team in five bullet points, plain English, "
               "no marketing language, and flag anything that changes how customers log in.\n"
               "End with the line: ROLLBACK PLAN READY")


@pytest.fixture()
def models():
    return load_models()


def make_settings(tmp_path, **kw):
    base = dict(db_url=f"sqlite:///{tmp_path / 'app.db'}", class_profile="class-mock", judge="mock-judge",
                byot_models=["mock-old", "mock-new", "mock-judge"], inline_jobs=True, collector=True)
    base.update(kw)
    return Settings(**base)


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


# --- the class kit ------------------------------------------------------------------------

def test_home_and_forms_render(client):
    for path in ("/", "/class", "/byot", "/projector"):
        assert client.get(path).status_code == 200, path


def test_class_kit_end_to_end(client):
    own = "Refactor billing.py but keep every public function and signature, Decimal with half-up rounding, " \
          "tax on the unrounded subtotal, is_bulk for other services, standard library only, Python 3.10."
    response = client.post("/class", data={"student": "AB", "own_refactor": own, "harness_round": "1"},
                           follow_redirects=False)
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200 and "Finished: 32 runs" in page.text
    assert page.text.count("<svg") == 2 and "Harness round" in page.text and "synthetic" in page.text
    sid = response.headers["location"].rsplit("/", 1)[1]
    doc = client.get(f"/class/{sid}/results.json").json()
    assert doc["format"] == 1 and doc["kind"] == "class" and doc["student"] == "AB" and len(doc["runs"]) == 32
    assert {r["variant"] for r in doc["runs"]} == {"terse", "full", "own", "h-terse", "h-full"}
    assert all(r["output_ref"] is None for r in doc["runs"])  # outputs stay on the server

    assert "Submitted" in client.post(f"/class/{sid}/submit").text
    projector = client.get("/projector")
    assert "1 results file so far" in projector.text and "<svg" in projector.text


def test_collector_accepts_only_class_results(client):
    assert client.post("/collect", json={"format": 1, "kind": "study", "runs": []}).status_code == 400
    assert client.post("/collect", content=b"not json", headers={"content-type": "application/json"}).status_code == 400
    assert client.post("/collect", json={"format": 1, "kind": "class", "runs": []}).json()["collected"] == 1


def test_collector_is_off_unless_turned_on(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, collector=False))) as c:
        assert c.get("/projector").status_code == 404
        assert c.post("/collect", json={}).status_code == 404


@pytest.fixture()
def recorded_study(tmp_path, models):
    """A small exported study on the mock models, to replay."""
    store = Store(f"sqlite:///{tmp_path / 'study.db'}")
    profile = Profile(name="study", tasks=["refactor", "data-question"], variants=["terse", "full"],
                      models=["mock-old", "mock-new"], repeats=2,
                      harness=HarnessSettings(tasks=["data-question"], variants=["h-terse", "h-full"],
                                              models=["mock-new"]))
    study.run_study(profile, models, store)
    return study.export(profile, models, store, out_dir=tmp_path / "results", created="2026-12-01")


def test_replay_mode_needs_no_gateway(tmp_path, recorded_study, monkeypatch):
    def no_gateway(model):
        raise AssertionError("replay mode must not call any model")
    monkeypatch.setattr("promptlab.runner.backend_for", no_gateway)
    monkeypatch.setattr("promptlab.harness_adapter.backend_for", no_gateway)
    settings = make_settings(tmp_path, replay=recorded_study, study_results=recorded_study)
    with TestClient(create_app(settings)) as c:
        assert "Replay mode" in c.get("/").text
        response = c.post("/class", data={"own_refactor": "my own prompt", "harness_round": "1"})
        page = response.text
        assert "Finished: 26 runs" in page and "your own prompt cannot run in replay mode" in page
        sid = str(response.url).rsplit("/", 1)[1]
        doc = c.get(f"/class/{sid}/results.json").json()
        assert doc["recorded"] is True and {r["label"] for r in doc["runs"]} == {"recorded"}
        assert any(r["mode"] == "harness" and r["session"]["tool_calls"] for r in doc["runs"])
        assert "replay mode" in c.post("/byot", data={"prompt": "x"}).text


# --- bring your own test ------------------------------------------------------------------------

def walk_to_results(client, check_kind="expected", run_models=("mock-old", "mock-new"), **check):
    data = {"prompt": LONG_PROMPT, "student": "CD", "check_kind": check_kind, **check}
    files = [("files", ("notes.txt", b"v2.1: single sign-on now required for admins", "text/plain"))]
    response = client.post("/byot", data=data, files=files, follow_redirects=False)
    assert response.status_code == 303, response.text
    url = response.headers["location"]
    test_id = url.rsplit("/", 1)[1]

    page = client.get(url).text
    assert "What the AI thinks of your prompt" in page and "Made up by the AI" in page
    assert client.post(f"{url}/verdict", data={"tier_agree": "agree"}).status_code == 400  # every invented item needs a verdict
    test = client.app.state.store.get(CustomTest, test_id)
    form = {"tier_agree": "disagree", "tier_reason": "it is more specific than that", "run_tier": ["spec"]}
    for rewrite in test.assessment["rewrites"]:
        for item in rewrite["invented"]:
            key = f"{rewrite['tier']}/{item['id']}"
            form[f"agree::{key}"] = "disagree"
            form[f"reason::{key}"] = "not something we do"
    assert client.post(f"{url}/verdict", data=form, follow_redirects=False).status_code == 303

    rubric_page = client.get(url).text
    assert "How answers will be graded" in rubric_page and 'value="correct"' in rubric_page
    assert client.post(f"{url}/rubric", data={"id_0": "ok", "name_0": "x"}).status_code == 400  # needs 3 to 5
    rubric = {}
    for i, cid in enumerate(["accurate", "audience", "brief"]):
        rubric.update({f"id_{i}": cid, f"name_{i}": cid.title(), f"description_{i}": f"is {cid}",
                       "anchor1_" + str(i): "no", "anchor3_" + str(i): "partly", "anchor5_" + str(i): "yes"})
    assert client.post(f"{url}/rubric", data=rubric, follow_redirects=False).status_code == 303

    run_page = client.get(url).text
    assert "Run your test" in run_page and "Use British spelling" not in run_page  # the deleted assumption is gone
    assert client.post(f"{url}/run", data={"model": ["mock-old"]}).status_code == 400  # 2 or 3 models
    assert client.post(f"{url}/run", data={"model": list(run_models)}, follow_redirects=False).status_code == 303
    return url, test_id


def test_bring_your_own_test_end_to_end(client):
    url, test_id = walk_to_results(client, expected="rollback plan ready")
    page = client.get(url).text
    assert "Did the AI's advice help?" in page and "The AI recommended the spec tier" in page
    test = client.app.state.store.get(CustomTest, test_id)
    assert test.status == "done" and test.rubric_approved and [c["id"] for c in test.rubric["criteria"]] == [
        "accurate", "audience", "brief"]
    assert set(test.plan["prompts"]) == {"yours", "rewrite-spec"}
    runs = client.app.state.store.runs(task=test.task_key)
    assert len(runs) == 2 * 2 * 3 and all(r.judge.get("score") is not None for r in runs)
    assert {r.score for r in runs if r.variant == "yours"} == {1.0}  # the check found the expected value

    scores_only = client.get(f"{url}/export.json").json()
    assert "prompt" not in scores_only and all("output" not in r for r in scores_only["runs"])
    assert scores_only["verdict"]["tier"]["agree"] is False and scores_only["tier"] == "context"
    full = client.get(f"{url}/export.json?text=true").json()
    assert full["prompt"] == LONG_PROMPT and full["files"]["notes.txt"].startswith("v2.1")


def test_a_finished_test_cannot_run_or_change_again(client):
    url, _ = walk_to_results(client, expected="x")
    again = client.post(f"{url}/run", data={"model": ["mock-old", "mock-new"]})
    assert again.status_code == 400 and "already run" in again.text
    changed = client.post(f"{url}/verdict", data={"tier_agree": "agree"})
    assert changed.status_code == 400 and "fixed once the test has run" in changed.text


def test_without_a_check_results_are_ai_judged_only(client):
    url, test_id = walk_to_results(client, check_kind="none")
    assert "AI-judged only" in client.get(url).text
    runs = client.app.state.store.runs(task=f"custom:{test_id}")
    assert all(r.score is None for r in runs) and {r.label for r in runs} == {"synthetic"}
    assert client.app.state.store.get(CustomTest, test_id).summary["measure"] == "AI judge"


def test_a_judge_grading_its_own_answers_is_flagged(client):
    url, test_id = walk_to_results(client, expected="x", run_models=("mock-old", "mock-judge"))
    assert "graded its own answers" in client.get(url).text
    runs = client.app.state.store.runs(task=f"custom:{test_id}")
    assert {r.model: r.judge["self_preference"] for r in runs} == {"mock-old": False, "mock-judge": True}


def test_byot_refuses_command_checks_and_binary_files(client):
    refused = client.post("/byot", data={"prompt": "hi", "check_kind": "command", "command": "true"})
    assert refused.status_code == 400 and "Command checks are turned off" in refused.text
    binary = client.post("/byot", data={"prompt": "hi"}, files=[("files", ("x.bin", bytes([0xff, 0xfe, 0x00]), "x"))])
    assert binary.status_code == 400 and "not a text file" in binary.text
    empty = client.post("/byot", data={"prompt": "  "})
    assert empty.status_code == 400 and "Write a prompt first" in empty.text
    assert client.get("/byot/" + "0" * 32).status_code == 404


def test_expired_tests_are_purged_with_their_runs(client, models):
    url, test_id = walk_to_results(client, expected="x")
    store = client.app.state.store
    assert store.runs(task=f"custom:{test_id}")
    assert store.purge_expired(datetime.now(timezone.utc) + timedelta(days=31)) == 1
    assert store.get(CustomTest, test_id) is None and not store.runs(task=f"custom:{test_id}")
    assert client.get(url).status_code == 404


def test_verdict_summary_has_counts_only(client):
    walk_to_results(client, expected="x")
    summary = byot.verdict_summary(client.app.state.store)
    assert summary["tests"] == 1 and summary["tier_verdicts"] == {"context": {"agree": 0, "disagree": 1}}
    assert summary["invented"]["disagree"] == 1 and "not something we do" not in json.dumps(summary)


# --- part C's engine ---------------------------------------------------------------------------------

def test_assessment_rejects_assumptions_blended_into_the_prompt():
    good = assess.Assessment(tier="goal", technique=1, information=2, recommended_tier="context", rewrites=[
        assess.Rewrite(tier="context", prompt="Do X.", invented=[assess.Invented(id="a", text="Use tabs.")]),
        assess.Rewrite(tier="spec", prompt="Do X carefully.")])
    assert assess._check_assessment(good) == ""
    blended = good.model_copy(deep=True)
    blended.rewrites[0].prompt = "Do X. Use tabs."
    assert "also appear" in assess._check_assessment(blended)
    skipped = good.model_copy(update={"rewrites": good.rewrites[:1]})
    assert "one rewrite for each tier" in assess._check_assessment(skipped)
    below = good.model_copy(update={"recommended_tier": "terse"})
    assert "cannot be below" in assess._check_assessment(below)


def test_rewrite_compose_keeps_only_what_the_student_kept():
    rewrite = assess.Rewrite(tier="spec", prompt="Do X.", invented=[assess.Invented(id="a", text="Use tabs."),
                                                                    assess.Invented(id="b", text="Be brief.")])
    assert rewrite.compose({"b"}) == "Do X.\n\n- Be brief."
    assert rewrite.compose(set()) == "Do X."


def test_custom_checks():
    assert run_check(CustomCheck(), "x", {}) is None
    assert run_check(CustomCheck(kind="expected", expected="Forty  Two"), "it is forty two.", {}).score == 1.0
    phrases = run_check(CustomCheck(kind="phrases", phrases=["alpha", "beta"]), "Alpha only", {})
    assert phrases.score == 0.5 and phrases.details["missing"] == ["beta"]
    passing = run_check(CustomCheck(kind="command", command="grep -q 42 answer.txt && test -f data.csv"), "42",
                        {"data.csv": "a,b"})
    assert passing.score == 1.0
    assert run_check(CustomCheck(kind="command", command="exit 3"), "x", {}).details["exit_code"] == 3
    with pytest.raises(ValueError):
        CustomCheck(kind="phrases", phrases=[" "])


def test_close_the_loop_outcomes():
    test = CustomTest(assessment=assess.Assessment(tier="goal", technique=1, information=1, recommended_tier="spec",
                                                   rewrites=[assess.Rewrite(tier="context", prompt="a"),
                                                             assess.Rewrite(tier="spec", prompt="b")]).model_dump())
    assert byot.close_the_loop(test, {"yours": 0.2, "rewrite-spec": 0.9})["outcome"] == "higher"
    assert byot.close_the_loop(test, {"yours": 0.9, "rewrite-spec": 0.2})["outcome"] == "lower"
    assert byot.close_the_loop(test, {"yours": 0.5, "rewrite-spec": 0.52})["outcome"] == "same"
    assert byot.close_the_loop(test, {"yours": 0.5})["outcome"] == "not-run"


# --- concurrency -------------------------------------------------------------------------------------

def test_run_parallel_caps_concurrency_and_keeps_order():
    active, peak, lock = [0], [0], threading.Lock()

    def job(i):
        def go():
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with lock:
                active[0] -= 1
            return i
        return go

    assert run_parallel([job(i) for i in range(8)], workers=2) == list(range(8))
    assert peak[0] == 2


def test_parallel_harness_sessions_keep_their_own_console(tmp_path, models, monkeypatch):
    """Sessions in threads must not swap sys.stdout for each other (or for the process)."""
    real = io.StringIO()
    monkeypatch.setattr(sys, "stdout", real)
    store = Store(f"sqlite:///{tmp_path / 'p.db'}")
    jobs = [lambda v=v: run_session("data-question", v, models["mock-new"], store=store)
            for v in ("h-terse", "h-full", "h-private-gap", "h-discoverable-gap")]
    runs = run_parallel(jobs, workers=4)
    assert sys.stdout is real and real.getvalue() == ""
    for run in runs:
        assert run.session["console"].startswith("> ") and run.prompt.splitlines()[0] in run.session["console"]
