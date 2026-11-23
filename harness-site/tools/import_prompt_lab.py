#!/usr/bin/env python3
"""Build content/prompt-lab-results.json from a Prompt Lab results file (spec: PROMPT_LAB_SPEC section 14).

The site stays static and offline: it never reads the Prompt Lab database or
lists folders. This script reads one committed results file (section 12),
computes the aggregates the "Prompts across model generations" page draws,
and writes them as content. Run it again after committing a new study.

    python3 tools/import_prompt_lab.py                     # newest prompt-lab/results/study-*.json
    python3 tools/import_prompt_lab.py --results FILE      # any results file, e.g. a mock-study sample

Standard library only. Then run tools/check.py.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from collections import defaultdict

SITE_ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS_DIR = SITE_ROOT.parent / "prompt-lab" / "results"
OUT = SITE_ROOT / "content" / "prompt-lab-results.json"

ONE_SHOT_ORDER = ["terse", "technique", "informed", "full", "ai-expanded", "ai-interviewed"]
HARNESS_ORDER = ["h-terse", "h-discoverable-gap", "h-private-gap", "h-full"]
# Disagreement between the judge and the checks, on 0 to 1. "Lenient" is prediction P10's own rule.
HIGH, LOW = 0.75, 0.5
PASS = 0.999            # a run "passed" when its checks scored this or more
QUOTE_CHARS = 240


def newest_study(folder: pathlib.Path) -> pathlib.Path:
    files = sorted(folder.glob("study-*.json"))
    if not files:
        raise SystemExit(f"No study-*.json in {folder}. Run the study first, or pass --results FILE.")
    return files[-1]


def mean(values, digits=1):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(statistics.mean(values), digits) if values else None


def total_tokens(run: dict) -> int | None:
    """Input (cached or not) plus output, if the provider reported input and output."""
    tokens = run.get("tokens") or {}
    base = [tokens.get("input"), tokens.get("output")]
    if not all(isinstance(v, int) for v in base):
        return None
    extra = [tokens.get(k) for k in ("cache_read", "cache_write")]
    return sum(base) + sum(v for v in extra if isinstance(v, int))


def chars(run: dict) -> int:
    c = run.get("chars") or {}
    return (c.get("sent") or 0) + (c.get("received") or 0)


def passed(run: dict) -> bool:
    score = (run.get("checks") or {}).get("score")
    return isinstance(score, (int, float)) and score >= PASS


def ordered(present: set[str], order: list[str]) -> list[str]:
    return [v for v in order if v in present] + sorted(present - set(order))


def build(doc: dict, source: str) -> dict:
    runs = [r for r in doc.get("runs", []) if r.get("status") != "error"]
    models = sorted(doc.get("models", []), key=lambda m: (m["family"], m["generation"]))
    one_shot = [r for r in runs if r["mode"] == "one-shot"]
    harness = [r for r in runs if r["mode"] == "harness"]

    cells = defaultdict(list)
    for r in one_shot:
        cells[(r["task"], r["model"], r["variant"])].append(r)
    one_shot_cells = [{"task": t, "model": m, "variant": v,
                       "scores": [round(r["checks"]["score"], 4) for r in rs if r["checks"]["score"] is not None]}
                      for (t, m, v), rs in sorted(cells.items())]

    hcells = defaultdict(list)
    for r in harness:
        hcells[(r["task"], r["model"], r["variant"])].append(r)
    harness_cells = []
    for (t, m, v), rs in sorted(hcells.items()):
        split = {part: mean([((r.get("tokens") or {}).get("split") or {}).get(part) for r in rs])
                 for part in ("fixed", "conversation", "tool_results")}
        split["output"] = mean([(r.get("tokens") or {}).get("output") for r in rs])
        split["reasoning"] = mean([(r.get("tokens") or {}).get("reasoning") for r in rs])
        harness_cells.append({
            "task": t, "model": m, "variant": v,
            "scores": [round(r["checks"]["score"], 4) for r in rs if r["checks"]["score"] is not None],
            "requests": mean([r.get("requests") for r in rs]),
            "hit_limit": sum(r.get("status") == "hit_limit" for r in rs),
            "runs": len(rs),
            "failed_calls": mean([(r.get("session") or {}).get("tool_calls_failed") for r in rs]),
            "tokens": mean([total_tokens(r) for r in rs], 0),
            "chars": mean([chars(r) for r in rs], 0),
            "split": split,
        })

    per_correct = []
    for m in models:
        row = {"model": m["id"]}
        for mode, pool in (("one_shot", one_shot), ("harness", harness)):
            rs = [r for r in pool if r["model"] == m["id"]]
            if not rs:
                row[mode] = None
                continue
            correct = sum(passed(r) for r in rs)
            tokens = [total_tokens(r) for r in rs]
            tokens_total = sum(tokens) if all(t is not None for t in tokens) else None
            chars_total = sum(chars(r) for r in rs)
            row[mode] = {"runs": len(rs), "correct": correct, "tokens": tokens_total, "chars": chars_total,
                         "tokens_per_correct": round(tokens_total / correct) if correct and tokens_total else None,
                         "chars_per_correct": round(chars_total / correct) if correct else None}
        per_correct.append(row)

    points = []
    for r in runs:
        judge = r.get("judge") or {}
        check, score = (r.get("checks") or {}).get("score"), judge.get("score")
        if check is None or score is None:
            continue
        kind = "lenient" if score >= HIGH and check < LOW else "harsh" if score < LOW and check >= HIGH else None
        point = {"id": r["id"], "task": r["task"], "model": r["model"], "variant": r["variant"],
                 "mode": r["mode"], "check": round(check, 4), "judge": round(score, 4), "disagree": kind}
        if kind:
            point["evidence"] = [{"criterion": c.get("id", ""), "score": c.get("score"),
                                  "quote": str(c.get("quote", ""))[:QUOTE_CHARS],
                                  "reason": str(c.get("reason", ""))[:QUOTE_CHARS]}
                                 for c in judge.get("criteria", [])]
        points.append(point)

    return {
        "generated_by": "tools/import_prompt_lab.py",
        "source": source,
        "created": doc.get("created"),
        "profile": doc.get("profile"),
        "synthetic": bool(doc.get("synthetic")),
        "note": doc.get("note", ""),
        "tasks": sorted({r["task"] for r in runs}),
        "models": [{k: m[k] for k in ("id", "display", "family", "generation")} for m in models],
        "judges": doc.get("judges"),
        "one_shot": {"variants": ordered({r["variant"] for r in one_shot}, ONE_SHOT_ORDER), "cells": one_shot_cells},
        "harness": {"variants": ordered({r["variant"] for r in harness}, HARNESS_ORDER), "cells": harness_cells},
        "per_correct": per_correct,
        "judge": {"rule": {"high": HIGH, "low": LOW}, "points": points, "validation": doc.get("judge_validation")},
        "predictions": [{k: p.get(k) for k in ("id", "outcome", "rule", "n")} for p in doc.get("predictions", [])],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--results", type=pathlib.Path, help="results file (default: newest study-*.json)")
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    args = parser.parse_args(argv)
    source = args.results or newest_study(RESULTS_DIR)
    doc = json.loads(source.read_text(encoding="utf-8"))
    if doc.get("format") != 1:
        raise SystemExit(f"{source} is not a format 1 results file")
    data = build(doc, source.name)
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out.relative_to(SITE_ROOT) if args.out.is_relative_to(SITE_ROOT) else args.out} "
          f"from {source.name}: {len(data['one_shot']['cells'])} one-shot cells, "
          f"{len(data['harness']['cells'])} harness cells, {len(data['judge']['points'])} judged runs"
          + (" (synthetic)" if data["synthetic"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
