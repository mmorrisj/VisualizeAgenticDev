"""`prompt-lab` command line.

    prompt-lab models                       list configured models
    prompt-lab tasks                        list tasks, their variants and facts
    prompt-lab check TASK ANSWER_FILE       score an answer file with a task's checks
    prompt-lab selftest                     every task's known-good answers pass and known-bad fail
    prompt-lab run --task T --variant V --model M [--repeats N]
    prompt-lab summary                      scores and tokens from the database
    prompt-lab variants --model M [--task T] generate the AI-assisted prompt variants
    prompt-lab study run|judge|sample|export --profile P
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from . import study
from .config import load_models
from .profiles import load_profile
from .runner import run_matrix
from .store import Store
from .tasks import load_task, task_ids
from .variants import GENERATED
from .variants import generate as generate_variants


def cmd_models(args) -> int:
    for m in load_models(args.models).values():
        flag = "" if m.confirmed else "  [gateway id not confirmed]"
        print(f"{m.id:18} {m.family:10} gen {m.generation}  {m.api:13} {m.gateway_id}{flag}")
    return 0


def cmd_tasks(args) -> int:
    for tid in task_ids():
        task = load_task(tid)
        private = sum(f.kind == "private" for f in task.spec.facts)
        print(f"{tid:14} {task.spec.title}")
        print(f"{'':14} variants: {', '.join(task.variants())}")
        print(f"{'':14} facts: {len(task.spec.facts) - private} discoverable, {private} only-you-know")
    return 0


def cmd_check(args) -> int:
    result = load_task(args.task).check(Path(args.answer).read_text(encoding="utf-8"))
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.passed else 1


def cmd_selftest(args) -> int:
    """Checks must pass a known-good answer and fail a known-bad one (spec phase L1)."""
    failures = 0
    for tid in task_ids():
        task = load_task(tid)
        for name in task.answers():
            result = task.check(task.answer(name))
            expect_pass = name.startswith("good")
            ok = result.passed == expect_pass
            failures += not ok
            print(f"{'ok ' if ok else 'BAD'} {tid:14} {name:22} score {result.score:.3f}"
                  f"  ({'should pass' if expect_pass else 'should fail'})")
    print("selftest:", "passed" if not failures else f"{failures} problem(s)")
    return 1 if failures else 0


def cmd_run(args) -> int:
    models = load_models(args.models)
    chosen = [models[m] for m in args.model]
    tasks = args.task or task_ids()
    store = Store(args.db)

    def show(run):
        tok = run.tokens or {}
        score = f"{run.score:.2f}" if run.score is not None else "  - "
        print(f"{run.task:14} {run.variant:12} {run.model:16} #{run.repeat} {run.status:10} score {score}"
              f"  in {tok.get('input')} out {tok.get('output')}" + (f"  {run.error}" if run.error else ""))

    run_matrix(tasks, args.variant or None, chosen, args.repeats, profile=args.profile, store=store, on_run=show)
    return 0


def cmd_summary(args) -> int:
    groups = defaultdict(list)
    for run in Store(args.db).runs():
        groups[(run.task, run.model, run.variant)].append(run)
    print(f"{'task':14} {'model':16} {'variant':12} {'n':>3} {'mean':>6} {'spread':>7} {'out tok':>8}")
    for (task, model, variant), runs in sorted(groups.items()):
        scores = [r.score for r in runs if r.score is not None]
        outs = [r.tokens.get("output") for r in runs if isinstance((r.tokens or {}).get("output"), int)]
        mean = f"{statistics.mean(scores):.2f}" if scores else "-"
        spread = f"{max(scores) - min(scores):.2f}" if scores else "-"
        out = f"{statistics.mean(outs):.0f}" if outs else "-"
        print(f"{task:14} {model:16} {variant:12} {len(runs):3} {mean:>6} {spread:>7} {out:>8}")
    return 0


def cmd_variants(args) -> int:
    model = load_models(args.models)[args.model]
    for tid in args.task or task_ids():
        for path in generate_variants(load_task(tid), model, tuple(args.variant or GENERATED)):
            print(f"wrote tasks/{tid}/{path}")
    print("Review each *.meta.yaml: confirm the invented requirements, then set confirmed_by_instructor: true.")
    return 0


def cmd_study(args) -> int:
    models = load_models(args.models)
    profile = load_profile(args.profile)
    store = Store(args.db)
    if args.action == "run":
        def show(run):
            score = f"{run.score:.2f}" if run.score is not None else "  - "
            print(f"{run.key:48} {run.status:10} score {score}" + (f"  {run.error}" if run.error else ""))
        stats = study.run_study(profile, models, store, on_run=show)
        print(f"ran {stats['ran']}, already done {stats['skipped_done']}")
        if stats["missing_variants"]:
            print("variants not generated yet (run `prompt-lab variants`):", ", ".join(stats["missing_variants"]))
    elif args.action == "judge":
        def show(run):
            j = run.judge
            score = f"{j['score']:.2f}" if j.get("score") is not None else "  - "
            cross = j.get("cross_check", {}).get("score") if j.get("cross_check") else None
            print(f"{run.key:48} judge {score}" + (f"  cross-check {cross:.2f}" if cross is not None else "")
                  + ("  [self-preference]" if j.get("self_preference") else "") + (f"  {j['error']}" if j.get("error") else ""))
        print(f"judged {study.judge_study(profile, models, store, on_run=show)['judged']}")
    elif args.action == "sample":
        sheet = study.write_human_sample(profile, store, Path(args.out), n=args.n)
        print(f"wrote {sheet}; fill in human_score_1_to_5, then export with --human {sheet}")
    elif args.action == "export":
        path = study.export(profile, models, store, Path(args.out) if args.out else study.RESULTS_DIR,
                            human_csv=Path(args.human) if args.human else None)
        print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--models", type=Path, default=None, help="models.yaml (default: config/models.yaml)")
    common.add_argument("--db", default=None, help="database URL (default: PROMPTLAB_DB_URL or data/lab.db)")
    parser = argparse.ArgumentParser(prog="prompt-lab", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("models", parents=[common]).set_defaults(func=cmd_models)
    sub.add_parser("tasks", parents=[common]).set_defaults(func=cmd_tasks)
    p = sub.add_parser("check", parents=[common])
    p.add_argument("task")
    p.add_argument("answer")
    p.set_defaults(func=cmd_check)
    sub.add_parser("selftest", parents=[common]).set_defaults(func=cmd_selftest)
    p = sub.add_parser("run", parents=[common])
    p.add_argument("--task", action="append", help="repeatable; default: all tasks")
    p.add_argument("--variant", action="append", help="repeatable; default: every variant of the task")
    p.add_argument("--model", action="append", required=True, help="repeatable")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--profile", default="adhoc")
    p.set_defaults(func=cmd_run)
    sub.add_parser("summary", parents=[common]).set_defaults(func=cmd_summary)
    p = sub.add_parser("variants", parents=[common])
    p.add_argument("--model", required=True, help="the primary judge model writes the variants")
    p.add_argument("--task", action="append", help="repeatable; default: all tasks")
    p.add_argument("--variant", action="append", choices=GENERATED, help="default: both")
    p.set_defaults(func=cmd_variants)
    p = sub.add_parser("study", parents=[common])
    p.add_argument("action", choices=["run", "judge", "sample", "export"])
    p.add_argument("--profile", required=True, help="profile name in config/ (study, class, mock-study) or a path")
    p.add_argument("--n", type=int, default=40, help="sample: runs to sample for human scoring")
    p.add_argument("--out", help="sample: output folder; export: results folder (default results/)")
    p.add_argument("--human", help="export: the filled-in human scores CSV")
    p.set_defaults(func=cmd_study)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
