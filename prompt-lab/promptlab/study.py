"""The study pipeline (spec sections 7, 9, 10.1, 12): run, judge, sample for humans, export.

    run     every task x variant x model x repeat in the profile; resumable
    judge   the primary judge on every answered run; the cross-check judge on a
            fixed share; self-preference flags
    sample  a fixed sample of judged runs for instructors to score by hand
    export  the results file the site reads, with model outputs beside it and a
            first, automatic reading of the predictions for instructors to review
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import Path

from . import LAB_ROOT
from .config import ModelConfig
from .judge import judge as judge_answer
from .judge import load_rubric
from .profiles import Profile
from .runner import run_one
from .store import Run, Store
from .tasks import load_task
from .variants import invented_count

RESULTS_DIR = LAB_ROOT / "results"
NOTE = "Classroom demonstration on four tasks; not a benchmark."
JUDGEABLE = {"ok", "max_tokens", "refused"}


# --- run ----------------------------------------------------------------------

def run_study(profile: Profile, models: dict[str, ModelConfig], store: Store,
              on_run: Callable[[Run], None] | None = None) -> dict:
    """Run everything in the profile that has not already run successfully."""
    profile.check_models(models)
    done = {r.key for r in store.runs(profile=profile.name) if r.status != "error"}
    stats = {"ran": 0, "skipped_done": 0, "missing_variants": set()}
    for task_id in profile.task_list():
        available = set(load_task(task_id).variants())
        for variant in profile.variants:
            if variant not in available:
                stats["missing_variants"].add(f"{task_id}/{variant}")
                continue
            for model_id in profile.models:
                for rep in range(1, profile.repeats + 1):
                    key = f"{task_id}--{variant}--{model_id}--{rep}"
                    if key in done:
                        stats["skipped_done"] += 1
                        continue
                    run = run_one(task_id, variant, models[model_id], repeat=rep, profile=profile.name, store=store)
                    stats["ran"] += 1
                    if on_run:
                        on_run(run)
    stats["missing_variants"] = sorted(stats["missing_variants"])
    return stats


# --- judge --------------------------------------------------------------------

def in_cross_check_sample(run: Run, share: float) -> bool:
    """A fixed, reproducible share of runs, chosen by hashing the run's identity."""
    digest = hashlib.sha256(run.key.encode()).hexdigest()
    return int(digest[:8], 16) % 1000 < share * 1000


def judge_study(profile: Profile, models: dict[str, ModelConfig], store: Store,
                on_run: Callable[[Run], None] | None = None, seed: int = 7) -> dict:
    if not profile.judge:
        raise ValueError(f"profile {profile.name} has no judge")
    primary = models[profile.judge.primary]
    cross = models.get(profile.judge.cross_check) if profile.judge.cross_check else None
    pending = [r for r in store.runs(profile=profile.name) if r.status in JUDGEABLE and not r.judge]
    random.Random(seed).shuffle(pending)  # judge in shuffled order, not grouped by model or variant
    for run in pending:
        task = load_task(run.task)
        meta = {"check_score": run.score}  # read only by the mock judge; never sent to a real model
        result = judge_answer(task, run.output, primary, meta)
        result["self_preference"] = models[run.model].family == primary.family
        if cross and in_cross_check_sample(run, profile.judge.cross_check_share):
            result["cross_check"] = judge_answer(task, run.output, cross, meta)
        run.judge = result
        store.update(run)
        if on_run:
            on_run(run)
    return {"judged": len(pending)}


# --- human validation sample ------------------------------------------------------

def write_human_sample(profile: Profile, store: Store, out_dir: Path, n: int = 40, seed: int = 11) -> Path:
    """Write n judged runs, their outputs, and a blank scoring sheet for instructors."""
    judged = [r for r in store.runs(profile=profile.name) if r.judge.get("score") is not None]
    sample = random.Random(seed).sample(judged, min(n, len(judged)))
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for run in sample:
        (out_dir / f"{run.key}.txt").write_text(run.output, encoding="utf-8")
        for c in load_rubric(load_task(run.task))["criteria"]:
            rows.append({"run": run.key, "task": run.task, "criterion": c["id"], "human_score_1_to_5": ""})
    sheet = out_dir / "scores.csv"
    with sheet.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run", "task", "criterion", "human_score_1_to_5"])
        writer.writeheader()
        writer.writerows(rows)
    return sheet


def judge_validation(runs: list[Run], human_csv: Path | None) -> dict:
    """Agreement of the judge with instructors (within 1 point on a criterion) and with the checks
    (judge score and check score on the same side of 0.5)."""
    judged = [r for r in runs if r.judge.get("score") is not None and r.score is not None]
    with_checks = (sum((r.judge["score"] >= 0.5) == (r.score >= 0.5) for r in judged) / len(judged)) if judged else None
    result = {"sample": 0, "agreement_with_humans": None, "agreement_with_checks": with_checks}
    if human_csv and human_csv.is_file():
        by_key = {r.key: {c["id"]: c["score"] for c in r.judge.get("criteria", [])} for r in judged}
        pairs, scored_runs = [], set()
        with human_csv.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                human = row.get("human_score_1_to_5", "").strip()
                machine = by_key.get(row["run"], {}).get(row["criterion"])
                if human and machine is not None:
                    pairs.append(abs(int(human) - machine) <= 1)
                    scored_runs.add(row["run"])
        result["sample"] = len(scored_runs)
        result["agreement_with_humans"] = (sum(pairs) / len(pairs)) if pairs else None
    return result


# --- predictions (spec section 9): a first, automatic reading ---------------------

def _mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def evaluate_predictions(runs: list[Run], models: dict[str, ModelConfig]) -> list[dict]:
    """Rules are deliberately simple and printed with each outcome, so instructors can check them."""
    one_shot = [r for r in runs if r.mode == "one-shot" and r.score is not None]
    cell = defaultdict(list)  # (task, model, variant) -> scores
    for r in one_shot:
        cell[(r.task, r.model, r.variant)].append(r.score)
    tasks = sorted({r.task for r in one_shot})
    families = defaultdict(list)
    for mid in sorted({r.model for r in one_shot}, key=lambda m: models[m].generation):
        families[models[mid].family].append(mid)

    def m(task, model, variant):
        return _mean(cell.get((task, model, variant), []))

    def sensitivity(task, model):
        means = [v for v in (m(task, model, var) for var in ("terse", "technique", "informed", "full")) if v is not None]
        return (max(means) - min(means)) if len(means) >= 2 else None

    def verdict(yes, no, total):
        if total == 0:
            return "not evaluated"
        return "supported" if yes > total / 2 else "contradicted" if no > total / 2 else "mixed"

    out = []
    # P1: sensitivity falls with each newer model in a family.
    pairs = [(t, a, b) for ladder in families.values() for a, b in zip(ladder, ladder[1:]) for t in tasks]
    diffs = [(sensitivity(t, b), sensitivity(t, a)) for t, a, b in pairs]
    diffs = [(new, old) for new, old in diffs if new is not None and old is not None]
    out.append({"id": "P1", "outcome": verdict(sum(n < o for n, o in diffs), sum(n > o for n, o in diffs), len(diffs)),
                "rule": "per task, newer model's best-minus-worst one-shot score vs the previous model in its family",
                "n": len(diffs)})
    newest = [ladder[-1] for ladder in families.values()]
    oldest = [ladder[0] for ladder in families.values() if len(ladder) > 1]
    # P2: on the newest models, technique ~ terse and informed clearly higher.
    p2 = [(m(t, mid, "technique"), m(t, mid, "terse"), m(t, mid, "informed")) for t in tasks for mid in newest]
    p2 = [x for x in p2 if None not in x]
    out.append({"id": "P2", "outcome": verdict(sum(abs(tq - tr) < 0.1 and inf - max(tq, tr) >= 0.2 for tq, tr, inf in p2),
                                               sum(tq - tr >= inf - max(tq, tr) for tq, tr, inf in p2), len(p2)),
                "rule": "newest per family: |technique - terse| < 0.1 and informed beats both by >= 0.2", "n": len(p2)})
    # P3: on the oldest models, technique beats terse.
    p3 = [(m(t, mid, "technique"), m(t, mid, "terse")) for t in tasks for mid in oldest]
    p3 = [x for x in p3 if None not in x]
    out.append({"id": "P3", "outcome": verdict(sum(tq - tr >= 0.1 for tq, tr in p3), sum(tq <= tr for tq, tr in p3), len(p3)),
                "rule": "oldest per family: technique beats terse by >= 0.1", "n": len(p3)})
    # P4: ai-expanded invents requirements and does not beat informed.
    p4 = []
    for t in tasks:
        invented = invented_count(load_task(t), "ai-expanded")
        for mid in {r.model for r in one_shot}:
            exp, inf = m(t, mid, "ai-expanded"), m(t, mid, "informed")
            if invented is not None and exp is not None and inf is not None:
                p4.append((invented, exp, inf))
    out.append({"id": "P4", "outcome": verdict(sum(i > 0 and e <= i_ for i, e, i_ in p4),
                                               sum(i == 0 and e >= i_ for i, e, i_ in p4), len(p4)),
                "rule": "confirmed invented requirements > 0 and ai-expanded scores no higher than informed",
                "n": len(p4)})
    # P5: ai-interviewed close to informed.
    p5 = [(m(t, mid, "ai-interviewed"), m(t, mid, "informed"), m(t, mid, "ai-expanded"))
          for t in tasks for mid in {r.model for r in one_shot}]
    p5 = [x for x in p5 if None not in x]
    out.append({"id": "P5", "outcome": verdict(sum(abs(iv - inf) <= 0.1 for iv, inf, _ in p5),
                                               sum(iv <= ex for iv, _, ex in p5), len(p5)),
                "rule": "ai-interviewed within 0.1 of informed (contradicted if no better than ai-expanded)",
                "n": len(p5)})
    for pid in ("P6", "P7", "P8"):
        out.append({"id": pid, "outcome": "not evaluated", "rule": "harness mode (phase L3)", "n": 0})
    # P9: newer models vary less across repeats with terse prompts.
    def spread(t, mid):
        scores = cell.get((t, mid, "terse"), [])
        return statistics.pstdev(scores) if len(scores) >= 2 else None
    p9 = [(spread(t, b), spread(t, a)) for ladder in families.values() for a, b in zip(ladder, ladder[1:]) for t in tasks]
    p9 = [x for x in p9 if None not in x]
    out.append({"id": "P9", "outcome": verdict(sum(n < o for n, o in p9), sum(n > o for n, o in p9), len(p9)),
                "rule": "spread across repeats of terse runs: newer vs previous model in family", "n": len(p9)})
    # P10: the judge is too lenient on some incorrect outputs.
    judged = [r for r in one_shot if r.judge.get("score") is not None]
    lenient = sum(r.judge["score"] >= 0.75 and r.score < 0.5 for r in judged)
    out.append({"id": "P10", "outcome": ("supported" if lenient else "contradicted") if judged else "not evaluated",
                "rule": "any run the judge scored >= 0.75 while its checks scored < 0.5", "n": lenient})
    for p in out:
        p["note"] = "automatic first reading; an instructor reviews it before publishing"
    return out


# --- export -------------------------------------------------------------------------

def export(profile: Profile, models: dict[str, ModelConfig], store: Store, out_dir: Path = RESULTS_DIR,
           human_csv: Path | None = None, created: str | None = None) -> Path:
    runs = store.runs(profile=profile.name)
    created = created or date.today().isoformat()
    outputs = out_dir / "outputs" / f"{profile.name}-{created}"
    outputs.mkdir(parents=True, exist_ok=True)
    used = sorted({r.model for r in runs}, key=lambda m: (models[m].family, models[m].generation))
    data = {
        "format": 1,
        "created": created,
        "profile": profile.name,
        "note": NOTE,
        "synthetic": any(models[m].api == "mock" for m in used),
        "models": [{"id": m, "display": models[m].display, "gateway_id": models[m].gateway_id,
                    "family": models[m].family, "generation": models[m].generation} for m in used],
        "judges": profile.judge.model_dump() if profile.judge else None,
        "runs": [],
    }
    for r in runs:
        ref = None
        if r.output:
            ref = f"outputs/{profile.name}-{created}/{r.key}.txt"
            (out_dir / ref).write_text(r.output, encoding="utf-8")
        judge = r.judge or {}
        data["runs"].append({
            "id": r.key, "mode": r.mode, "task": r.task, "variant": r.variant, "model": r.model,
            "repeat": r.repeat, "status": r.status, "label": r.label,
            "checks": {"score": r.score, "details": (r.check_details or {}).get("details", {})},
            "judge": ({"score": judge.get("score"), "criteria": judge.get("criteria", []),
                       "unsupported_claims": judge.get("unsupported_claims"),
                       "cross_check": (judge.get("cross_check") or {}).get("score"),
                       "self_preference": judge.get("self_preference", False),
                       "error": judge.get("error", "")} if judge else None),
            "tokens": r.tokens, "chars": {"sent": r.chars_sent, "received": r.chars_received},
            "requests": r.requests, "stop": r.stop, "latency_s": r.latency_s, "output_ref": ref, "error": r.error,
        })
    data["judge_validation"] = judge_validation(runs, human_csv)
    data["predictions"] = evaluate_predictions(runs, models)
    path = out_dir / f"{profile.name}-{created}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
