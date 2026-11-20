"""Phase L2: JSON replies, the judge, generated variants, and the study pipeline end to end."""

import json
import shutil

import pytest
import yaml

import promptlab.tasks as tasks_module
from promptlab import TASKS_DIR, study
from promptlab.backends import Response
from promptlab.config import load_models
from promptlab.judge import ABSENT, build_prompt, judge
from promptlab.llm import ask_json, first_json_object
from promptlab.profiles import JudgeSettings, Profile
from promptlab.store import Store
from promptlab.tasks import load_task
from promptlab.tokens import Usage
from promptlab.variants import generate, invented_count
from pydantic import BaseModel


@pytest.fixture()
def tasks_copy(tmp_path, monkeypatch):
    """A private copy of tasks/, so generated prompts never touch the repository."""
    dest = tmp_path / "tasks"
    shutil.copytree(TASKS_DIR, dest)
    monkeypatch.setattr(tasks_module, "TASKS_DIR", dest)
    load_task.cache_clear()
    yield dest
    load_task.cache_clear()


@pytest.fixture()
def models():
    return load_models()


class Scripted:
    """A backend that replies with the given texts, in order."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.requests = []

    def complete(self, request, model):
        self.requests.append(request)
        return Response(text=self.texts.pop(0), usage=Usage(input=10, output=5), stop="end", latency_s=0.0)


@pytest.fixture()
def scripted(monkeypatch):
    def install(*texts):
        backend = Scripted(*texts)
        monkeypatch.setattr("promptlab.llm.backend_for", lambda model: backend)
        return backend
    return install


# --- JSON replies ------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    '{"a": 1}',
    'Sure! ```json\n{"a": 1}\n``` done',
    'Here: {"a": 1} and {"b": 2}',
    'prose {"a": 1, "s": "a } brace"} after',
])
def test_first_json_object(text):
    assert first_json_object(text)["a"] == 1


def test_first_json_object_none():
    with pytest.raises(ValueError):
        first_json_object("no json here")


class Shape(BaseModel):
    n: int


def test_ask_json_retries_once_with_the_error(scripted, models):
    backend = scripted("not json", '{"n": 3}')
    result = ask_json(models["mock-judge"], "sys", "give n", Shape)
    assert result.value.n == 3 and len(result.responses) == 2
    assert "could not be used" in backend.requests[1].messages[0]["content"]


def test_ask_json_gives_up_after_two(scripted, models):
    scripted('{"n": "x"}', '{"m": 1}')
    result = ask_json(models["mock-judge"], "sys", "give n", Shape)
    assert result.value is None and result.error and len(result.responses) == 2


# --- judge ----------------------------------------------------------------------------

def judgement(task, quote, scores=(5, 4, 3), claims=None):
    rubric = yaml.safe_load(load_task(task).read("rubric.yaml"))
    out = {"criteria": [{"id": c["id"], "score": s, "quote": quote, "reason": "r"}
                        for c, s in zip(rubric["criteria"], scores)]}
    if claims is not None:
        out["claims"] = claims
    return json.dumps(out)


def test_judge_scores_and_records_tokens(scripted, models):
    answer = load_task("refactor").answer("good")
    scripted(judgement("refactor", "def _money(amount):"))
    result = judge(load_task("refactor"), answer, models["mock-judge"])
    assert result["score"] == round((1 + 0.75 + 0.5) / 3, 4)
    assert result["attempts"] == 1 and result["tokens"][0]["input"] == 10


def test_judge_rejects_invented_quotes_then_records_missing(scripted, models):
    answer = load_task("refactor").answer("good")
    scripted(judgement("refactor", "this text is not in the answer"), judgement("refactor", "still not there"))
    result = judge(load_task("refactor"), answer, models["mock-judge"])
    assert result["score"] is None and "not in the answer" in result["error"] and result["attempts"] == 2


def test_judge_accepts_absent_and_markdown_differences(scripted, models):
    answer = "**Impact:** About 4,300 failed."
    scripted(judgement("summarize", "Impact: about 4,300 failed", claims=[]))
    assert judge(load_task("summarize"), answer, models["mock-judge"])["score"] is not None
    scripted(judgement("summarize", ABSENT, claims=[]))
    assert judge(load_task("summarize"), answer, models["mock-judge"])["score"] is not None


def test_judge_verifies_claim_sources(scripted, models):
    task = load_task("summarize")
    good = [{"claim": "4,300 failed", "supported": True, "source_quote": "About 4,300 card authorizations failed"},
            {"claim": "made up", "supported": False}]
    bad = [{"claim": "made up", "supported": True, "source_quote": "a sentence the report never says"}]
    scripted(judgement("summarize", ABSENT, claims=good))
    result = judge(task, "x", models["mock-judge"])
    assert result["unsupported_claims"] == 1
    scripted(judgement("summarize", ABSENT, claims=bad), judgement("summarize", ABSENT, claims=bad))
    assert judge(task, "x", models["mock-judge"])["score"] is None


def test_judge_is_blind():
    prompt = build_prompt(load_task("data-question"), "SELECT 1", yaml.safe_load(
        load_task("data-question").read("rubric.yaml")))
    for word in ("mock-old", "mock-new", "terse", "technique", "llama", "gpt", "opus", "sonnet"):
        assert word not in prompt.lower()


# --- generated variants -----------------------------------------------------------------

def test_generate_variants_and_invented_requirements(tasks_copy, models):
    task = load_task("refactor")
    written = generate(task, models["mock-judge"])
    assert written == ["prompts/ai-expanded.md", "prompts/ai-expanded.meta.yaml",
                       "prompts/ai-interviewed.md", "prompts/ai-interviewed.meta.yaml"]
    assert {"ai-expanded", "ai-interviewed"} <= set(task.variants())
    expanded = yaml.safe_load(task.read("prompts", "ai-expanded.meta.yaml"))
    assert len(expanded["invented_requirements"]["items"]) == 1
    interviewed = yaml.safe_load(task.read("prompts", "ai-interviewed.meta.yaml"))
    assert interviewed["invented_requirements"]["items"] == [] and len(interviewed["transcript"]) == 2
    assert invented_count(task, "ai-expanded") is None  # not until an instructor confirms
    expanded["invented_requirements"]["confirmed_by_instructor"] = True
    task.path("prompts", "ai-expanded.meta.yaml").write_text(yaml.safe_dump(expanded))
    assert invented_count(task, "ai-expanded") == 1


# --- the study pipeline ------------------------------------------------------------------

def small_profile(**kw):
    base = dict(name="t", tasks=["data-question", "summarize"], variants=["terse", "informed", "ai-expanded"],
                models=["mock-old", "mock-new"], repeats=2,
                judge=JudgeSettings(primary="mock-judge", cross_check="mock-judge-2", cross_check_share=0.5))
    base.update(kw)
    return Profile(**base)


def test_study_end_to_end(tasks_copy, tmp_path, models):
    store = Store(f"sqlite:///{tmp_path / 's.db'}")
    profile = small_profile()
    first = study.run_study(profile, models, store)
    assert first["ran"] == 2 * 2 * 2 * 2 and first["missing_variants"] == ["data-question/ai-expanded",
                                                                           "summarize/ai-expanded"]
    for tid in ("data-question", "summarize"):
        generate(load_task(tid), models["mock-judge"], ("ai-expanded",))
    second = study.run_study(profile, models, store)
    assert second == {"ran": 8, "skipped_done": 16, "missing_variants": []}

    assert study.judge_study(profile, models, store)["judged"] == 24
    assert study.judge_study(profile, models, store)["judged"] == 0  # resumable
    runs = store.runs(profile="t")
    assert all(r.judge["score"] is not None for r in runs)
    crossed = [r for r in runs if "cross_check" in r.judge]
    assert 0 < len(crossed) < len(runs)

    sheet = study.write_human_sample(profile, store, tmp_path / "sample", n=4)
    rows = sheet.read_text().splitlines()
    sheet.write_text("\n".join([rows[0]] + [line + "3" for line in rows[1:]]) + "\n")
    path = study.export(profile, models, store, out_dir=tmp_path / "results", human_csv=sheet, created="2026-12-01")
    data = json.loads(path.read_text())
    assert path.name == "t-2026-12-01.json" and data["synthetic"] is True and data["note"].endswith("not a benchmark.")
    assert len(data["runs"]) == 24 and {p["id"] for p in data["predictions"]} == {f"P{i}" for i in range(1, 11)}
    assert data["judge_validation"]["sample"] == 4 and data["judge_validation"]["agreement_with_humans"] is not None
    run = data["runs"][0]
    assert {"id", "mode", "task", "variant", "model", "repeat", "status", "checks", "judge", "label",
            "tokens", "chars", "requests", "stop", "output_ref"} <= set(run)
    assert (tmp_path / "results" / run["output_ref"]).read_text() == store.runs(profile="t")[0].output


def test_self_preference_flag(tasks_copy, tmp_path, models):
    store = Store(f"sqlite:///{tmp_path / 's.db'}")
    profile = small_profile(tasks=["data-question"], variants=["terse"], repeats=1,
                            models=["mock-old", "mock-judge"], judge=JudgeSettings(primary="mock-judge"))
    study.run_study(profile, models, store)
    study.judge_study(profile, models, store)
    flags = {r.model: r.judge["self_preference"] for r in store.runs(profile="t")}
    assert flags == {"mock-old": False, "mock-judge": True}


def test_cross_check_share_is_about_right():
    from promptlab.store import Run
    runs = [Run(task="t", variant="v", model=f"m{i}", repeat=r) for i in range(50) for r in range(1, 5)]
    share = sum(study.in_cross_check_sample(r, 0.2) for r in runs) / len(runs)
    assert 0.13 < share < 0.27
    assert study.in_cross_check_sample(runs[0], 0.2) == study.in_cross_check_sample(runs[0], 0.2)


def test_profiles_reference_known_models(models):
    from promptlab.profiles import load_profile
    for name in ("study", "class", "mock-study"):
        load_profile(name).check_models(models)
