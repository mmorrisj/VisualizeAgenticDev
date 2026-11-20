"""Part C, bring your own test (spec section 10.3), as engine functions the app calls step by step.

    1. create_test      the prompt, optional files, an optional check
    2. assess           the AI's tier, scores, missing information and rewrites
    3. record_verdict   the student agrees or disagrees with the tier and each
                        invented assumption, and chooses what to keep
    4. draft_rubric / approve_rubric
                        approved before any result exists
    5. run_test         the student's prompt and the rewrites they kept, on 2 or 3
                        models, 3 runs each; checks first, then the judge
    6. summarize        scores per prompt and model, and whether the AI's
                        recommended tier actually scored higher (closing the loop)

Students may bring real work: section 13 applies. Tests expire after the
retention period and are purged with their runs. Exports leave out prompts and
outputs unless the student asks for them.
"""

from __future__ import annotations

import json
import secrets
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from . import assess
from .backends import BackendError, Request, backend_for
from .config import ModelConfig
from .custom_checks import CustomCheck, run_check
from .judge import judge_request
from .runner import run_parallel
from .store import CustomTest, Run, Store
from .tokens import Usage

MAX_PROMPT_CHARS = 20_000
MAX_FILES_CHARS = 200_000
MAX_FILES = 3
YOURS = "yours"


class InputError(ValueError):
    """Something the student can fix: shown to them as is."""


def _files_text(files: dict[str, str]) -> str:
    return "\n\n".join(f"File: {name}\n```\n{text.rstrip()}\n```" for name, text in files.items())


# --- 1. create ------------------------------------------------------------------------

def create_test(store: Store, prompt: str, files: dict[str, str] | None = None, check: CustomCheck | None = None,
                *, student: str = "", retention_days: int = 30, allow_command_checks: bool = False) -> CustomTest:
    prompt = (prompt or "").strip()
    files = {name: text for name, text in (files or {}).items() if text.strip()}
    check = check or CustomCheck()
    if not prompt:
        raise InputError("Write a prompt first.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise InputError(f"The prompt is longer than {MAX_PROMPT_CHARS:,} characters.")
    if len(files) > MAX_FILES or sum(len(t) for t in files.values()) > MAX_FILES_CHARS:
        raise InputError(f"Attach at most {MAX_FILES} text files, {MAX_FILES_CHARS // 1000} KB in total.")
    if check.kind == "command" and not allow_command_checks:
        raise InputError("Command checks are turned off on this server. Use an expected value or phrases instead.")
    now = datetime.now(timezone.utc)
    test = CustomTest(id=secrets.token_hex(16), created=now, expires=now + timedelta(days=retention_days),
                      student=student.strip()[:64], prompt=prompt, files=files, check=check.model_dump())
    return store.add(test)


# --- 2. assess ----------------------------------------------------------------------------

def run_assessment(store: Store, test: CustomTest, judge: ModelConfig) -> CustomTest:
    value, call = assess.assess_prompt(test.prompt, test.files, judge)
    test.assessment_call = call
    if value is None:
        test.error = f"The assessment did not work: {call['error']}"
    else:
        test.assessment, test.status, test.error = value.model_dump(), "assessed", ""
    return store.update(test)


def assessment_of(test: CustomTest) -> assess.Assessment:
    return assess.Assessment.model_validate(test.assessment)


# --- 3. verdict -----------------------------------------------------------------------------

def record_verdict(store: Store, test: CustomTest, *, tier_agree: bool, tier_reason: str = "",
                   invented: dict[str, dict] | None = None, run_tiers: list[str] | None = None) -> CustomTest:
    """invented: "<tier>/<id>" -> {"agree": bool, "reason": str, "keep": bool}.

    Every invented assumption gets a verdict. `keep` defaults to the verdict: an
    assumption the student disagrees with is left out unless they keep it.
    """
    if not test.assessment:
        raise InputError("There is no assessment to respond to yet.")
    if test.status in ("running", "done"):
        raise InputError("Your answers are fixed once the test has run.")
    assessment = assessment_of(test)
    invented = invented or {}
    expected = {f"{r.tier}/{i.id}" for r in assessment.rewrites for i in r.invented}
    missing = sorted(expected - set(invented))
    if missing:
        raise InputError(f"Say whether you agree with every invented assumption ({len(missing)} left).")
    tiers = [t for t in (run_tiers if run_tiers is not None else [r.tier for r in assessment.rewrites])
             if assessment.rewrite(t)]
    test.verdict = {
        "tier": {"ai": assessment.tier, "agree": tier_agree, "reason": tier_reason.strip()[:300]},
        "invented": {key: {"agree": bool(v.get("agree")), "reason": str(v.get("reason", "")).strip()[:300],
                           "keep": bool(v.get("keep", v.get("agree")))} for key, v in invented.items()
                     if key in expected},
        "run_tiers": tiers,
    }
    return store.update(test)


def prompts_to_run(test: CustomTest) -> dict[str, str]:
    """label -> prompt text: the student's own, then each rewrite they chose, with only the kept assumptions."""
    prompts = {YOURS: test.prompt}
    if not test.verdict:
        return prompts
    assessment = assessment_of(test)
    for tier in test.verdict["run_tiers"]:
        rewrite = assessment.rewrite(tier)
        keep = {i.id for i in rewrite.invented if test.verdict["invented"].get(f"{tier}/{i.id}", {}).get("keep")}
        prompts[f"rewrite-{tier}"] = rewrite.compose(keep)
    return prompts


# --- 4. rubric --------------------------------------------------------------------------------

def run_rubric_draft(store: Store, test: CustomTest, judge: ModelConfig) -> CustomTest:
    value, call = assess.draft_rubric(test.prompt, test.files, judge)
    test.rubric_call = call
    if value is None:
        test.error = f"The rubric draft did not work: {call['error']}"
    else:
        test.rubric, test.rubric_approved, test.error = value.model_dump(), False, ""
    return store.update(test)


def approve_rubric(store: Store, test: CustomTest, rubric: assess.Rubric) -> CustomTest:
    if test.status in ("running", "done"):
        raise InputError("The rubric is fixed once results exist.")
    test.rubric, test.rubric_approved = rubric.model_dump(), True
    if test.verdict:
        test.status = "ready"
    return store.update(test)


# --- 5. run -----------------------------------------------------------------------------------------

def plan_run(store: Store, test: CustomTest, models: list[ModelConfig], judge: ModelConfig,
             repeats: int = 3) -> CustomTest:
    if test.status in ("running", "done"):
        raise InputError("This test has already run.")
    if not test.verdict:
        raise InputError("Respond to the assessment first.")
    if not test.rubric_approved:
        raise InputError("Approve the rubric before running: it has to be fixed before any result exists.")
    if not 2 <= len(models) <= 3:
        raise InputError("Choose 2 or 3 models.")
    test.plan = {"prompts": prompts_to_run(test), "models": [m.id for m in models], "judge": judge.id,
                 "repeats": repeats,
                 "judge_is_tested": judge.id in {m.id for m in models},
                 "judge_family_tested": judge.family in {m.family for m in models}}
    test.status = "running"
    return store.update(test)


def _one(test: CustomTest, label: str, prompt: str, model: ModelConfig, repeat: int, judge: ModelConfig,
         check: CustomCheck, backend=None) -> Run:
    message = prompt + ("\n\n" + _files_text(test.files) if test.files else "")
    run = Run(profile="byot", mode="one-shot", task=test.task_key, variant=label, model=model.id,
              gateway_id=model.gateway_id, repeat=repeat, effort=model.effort or "", prompt=message,
              chars_sent=len(message))
    request = Request(messages=[{"role": "user", "content": message}], meta={"role": "custom_answer"})
    try:
        response = (backend or backend_for(model)).complete(request, model)
    except BackendError as err:
        run.status, run.error, run.tokens, run.label = "error", str(err), Usage().to_dict(), "error"
        return run
    run.output, run.chars_received = response.text, len(response.text)
    run.tokens, run.latency_s, run.stop = response.usage.to_dict(), round(response.latency_s, 3), response.stop
    run.served_model = response.served_model
    run.status = {"end": "ok", "refusal": "refused", "max_tokens": "max_tokens"}.get(response.stop, "ok")
    result = run_check(check, response.text, test.files)
    if result is not None:
        run.score = result.score
        run.check_details = json.loads(json.dumps(result.to_dict(), default=str))
    run.label = ("synthetic" if response.usage.synthetic else
                 "checked" if result is not None else "ai-judged")
    # The judge sees what the student asked for, never the model or which prompt produced the answer.
    run.judge = judge_request(test.prompt, test.files, response.text, test.rubric, judge)
    run.judge["self_preference"] = judge.family == model.family
    return run


def run_test(store: Store, test: CustomTest, models: dict[str, ModelConfig], *, workers: int = 2,
             on_run: Callable[[Run], None] | None = None, backend=None) -> CustomTest:
    """Run the plan (plan_run first). Each run is stored as it finishes; the summary is written at the end."""
    plan = test.plan
    judge = models[plan["judge"]]
    check = CustomCheck.model_validate(test.check)
    jobs = [(lambda label=label, prompt=prompt, mid=mid, rep=rep:
             store.add(_one(test, label, prompt, models[mid], rep, judge, check, backend)))
            for label, prompt in plan["prompts"].items() for mid in plan["models"]
            for rep in range(1, plan["repeats"] + 1)]
    run_parallel(jobs, workers=workers, on_done=on_run)
    test.summary = summarize(test, store.runs(task=test.task_key))
    test.status = "done"
    return store.update(test)


# --- 6. summary ------------------------------------------------------------------------------------

def _mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 4) if values else None


def _measure(run: Run, checked: bool):
    """The primary score: the check when there is one (spec section 7.1), else the judge."""
    return run.score if checked else (run.judge or {}).get("score")


def summarize(test: CustomTest, runs: list[Run]) -> dict:
    checked = CustomCheck.model_validate(test.check).active
    cells = defaultdict(list)
    for r in runs:
        cells[(r.variant, r.model)].append(r)
    rows = []
    for (label, model), rs in sorted(cells.items()):
        ok = [r for r in rs if r.status != "error"]
        outputs = [r.tokens.get("output") for r in ok if isinstance(r.tokens.get("output"), int)]
        inputs = [r.tokens.get("input") for r in ok if isinstance(r.tokens.get("input"), int)]
        rows.append({"prompt": label, "model": model, "runs": len(rs), "errors": len(rs) - len(ok),
                     "check": _mean([r.score for r in ok]) if checked else None,
                     "judge": _mean([(r.judge or {}).get("score") for r in ok]),
                     "input_tokens": _mean(inputs), "output_tokens": _mean(outputs),
                     "labels": sorted({r.label for r in rs})})
    by_prompt = {label: _mean([_measure(r, checked) for r in runs if r.variant == label and r.status != "error"])
                 for label in test.plan.get("prompts", {})}
    return {"measure": "checks" if checked else "AI judge", "rows": rows, "by_prompt": by_prompt,
            "loop": close_the_loop(test, by_prompt),
            "judge": test.plan.get("judge"), "judge_is_tested": test.plan.get("judge_is_tested", False),
            "judge_family_tested": test.plan.get("judge_family_tested", False)}


def close_the_loop(test: CustomTest, by_prompt: dict) -> dict:
    """Did the AI's recommended tier actually score higher than the student's prompt?"""
    assessment = assessment_of(test)
    recommended = assessment.recommended_tier
    yours = by_prompt.get(YOURS)
    if recommended == assessment.tier:
        return {"recommended": recommended, "outcome": "no-change",
                "text": f"The AI judged your prompt already at the tier it recommends ({recommended}), "
                        "so there is no rewrite to compare."}
    theirs = by_prompt.get(f"rewrite-{recommended}")
    if theirs is None or yours is None:
        return {"recommended": recommended, "outcome": "not-run",
                "text": f"The AI recommended the {recommended} tier, but that rewrite was not run, "
                        "so its recommendation was not tested."}
    outcome = "higher" if theirs > yours + 0.05 else "lower" if theirs < yours - 0.05 else "same"
    verdicts = {"higher": "The recommendation was borne out.",
                "same": "The rewrite did no better than your prompt.",
                "lower": "Your prompt did better than the AI's recommendation."}
    return {"recommended": recommended, "outcome": outcome, "yours": yours, "recommended_score": theirs,
            "text": f"The AI recommended the {recommended} tier. Its rewrite scored {theirs:.2f} against your "
                    f"prompt's {yours:.2f}. {verdicts[outcome]}"}


# --- export and instructor summary ---------------------------------------------------------------

def export_test(test: CustomTest, runs: list[Run], include_text: bool = False) -> dict:
    """Scores, tiers, verdicts and token counts. Prompts and outputs only if the student asks (section 13)."""
    out = {"format": 1, "kind": "bring-your-own-test", "created": test.created.date().isoformat(),
           "tier": test.assessment.get("tier"), "recommended_tier": test.assessment.get("recommended_tier"),
           "technique": test.assessment.get("technique"), "information": test.assessment.get("information"),
           "verdict": test.verdict, "rubric": test.rubric, "summary": test.summary,
           "runs": [{"prompt": r.variant, "model": r.model, "repeat": r.repeat, "status": r.status,
                     "label": r.label, "check": r.score, "judge": (r.judge or {}).get("score"),
                     "tokens": r.tokens} for r in runs]}
    if include_text:
        out["prompt"], out["files"] = test.prompt, test.files
        out["prompts_run"] = test.plan.get("prompts", {})
        for record, r in zip(out["runs"], runs):
            record["output"] = r.output
    return out


def verdict_summary(store: Store) -> dict:
    """Where the tier model fits students' real work and where it does not: counts only, no text."""
    tiers = defaultdict(lambda: {"agree": 0, "disagree": 0})
    invented = {"agree": 0, "disagree": 0, "kept": 0, "deleted": 0}
    tests = [t for t in store.all(CustomTest) if t.verdict]
    for t in tests:
        tiers[t.verdict["tier"]["ai"]]["agree" if t.verdict["tier"]["agree"] else "disagree"] += 1
        for v in t.verdict["invented"].values():
            invented["agree" if v["agree"] else "disagree"] += 1
            invented["kept" if v["keep"] else "deleted"] += 1
    loops = defaultdict(int)
    for t in tests:
        if t.summary:
            loops[t.summary["loop"]["outcome"]] += 1
    return {"tests": len(tests), "tier_verdicts": dict(tiers), "invented": invented,
            "recommendation_outcomes": dict(loops)}
