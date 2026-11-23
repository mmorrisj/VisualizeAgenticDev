"""Part B, the class kit (spec section 10.2): a short run each student does in class.

Two models chosen for contrast, two fast tasks, the `terse` and `full` prompts
and the student's own, 3 runs each, checks only. Optionally a harness round:
data-question, `h-terse` against `h-full`, on the newest model, with a live
request counter.

Each student's runs are stored under their own profile name, so results never
mix. At most 2 requests run at once per student; the backends back off on rate
limits. In replay mode nothing is sent to a model: recorded runs from the study
are served instead, labelled "recorded".
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .config import ModelConfig
from .harness_adapter import Limits, run_session
from .profiles import Profile
from .replay import Recorded
from .runner import OWN, run_one, run_parallel
from .store import Run, Store
from .study import run_record

NOTE = "Class kit run; one student's results, plotted over the study's."


@dataclass(frozen=True)
class Item:
    mode: str            # "one-shot" or "harness"
    task: str
    variant: str
    model: str
    repeat: int
    prompt: str | None = None  # the student's own prompt (variant "own")

    @property
    def key(self) -> str:
        return f"{self.task}--{self.variant}--{self.model}--{self.repeat}"


def new_session_profile() -> str:
    """A profile name of its own for one student's class run."""
    return f"class-{secrets.token_hex(6)}"


def plan(profile: Profile, own_prompts: dict[str, str] | None = None, harness_round: bool = False) -> list[Item]:
    """Everything a class run will do, in order. Own prompts are optional, per task."""
    own_prompts = {t: p.strip() for t, p in (own_prompts or {}).items() if p and p.strip()}
    items = []
    for task in profile.task_list():
        variants = list(profile.variants) + ([OWN] if task in own_prompts else [])
        for variant in variants:
            for model in profile.models:
                for rep in range(1, profile.repeats + 1):
                    items.append(Item("one-shot", task, variant, model, rep,
                                      own_prompts[task] if variant == OWN else None))
    if harness_round and profile.harness:
        for task in profile.harness_tasks():
            for variant in profile.harness.variants:
                for model in profile.harness_models():
                    for rep in range(1, profile.harness.repeats + 1):
                        items.append(Item("harness", task, variant, model, rep))
    return items


def skipped_in_replay(items: list[Item], recorded: Recorded) -> list[tuple[Item, str]]:
    """Items replay cannot serve, with the reason shown to the student."""
    out = []
    for item in items:
        if item.variant == OWN:
            out.append((item, "your own prompt cannot run in replay mode: it was never recorded"))
        elif not recorded.has(item.mode, item.task, item.variant, item.model):
            out.append((item, f"the recorded study has no {item.variant} runs of {item.task} on {item.model}"))
    return out


def run_class(items: list[Item], models: dict[str, ModelConfig], store: Store, session_profile: str, *,
              recorded: Recorded | None = None, workers: int = 2, harness_limits: Limits = Limits(),
              on_run: Callable[[Run], None] | None = None,
              on_request: Callable[[Item, dict], None] | None = None) -> list[Run]:
    """Run (or replay) every item. Returns the stored runs; replay skips what it cannot serve."""
    skip = {item for item, _ in skipped_in_replay(items, recorded)} if recorded else set()

    def job(item: Item):
        def go():
            if recorded is not None:
                return store.add(recorded.run(item.mode, item.task, item.variant, item.model, item.repeat,
                                              session_profile))
            if item.mode == "harness":
                return run_session(item.task, item.variant, models[item.model], repeat=item.repeat,
                                   profile=session_profile, store=store, limits=harness_limits,
                                   on_request=(lambda rec: on_request(item, rec)) if on_request else None)
            return run_one(item.task, item.variant, models[item.model], repeat=item.repeat,
                           profile=session_profile, store=store, prompt=item.prompt)
        return go

    return run_parallel([job(i) for i in items if i not in skip], workers=workers, on_done=on_run)


def class_results(runs: list[Run], models: dict[str, ModelConfig], session_profile: str, *,
                  student: str = "", recorded: bool = False, created: str | None = None) -> dict:
    """One student's results file: the section 12 format, without the outputs."""
    used = sorted({r.model for r in runs}, key=lambda m: (models[m].family, models[m].generation))
    return {
        "format": 1,
        "created": created or date.today().isoformat(),
        "profile": session_profile,
        "kind": "class",
        "student": student,
        "recorded": recorded,
        "note": NOTE + (" Replayed from recorded study runs." if recorded else ""),
        "synthetic": any(models[m].api == "mock" for m in used),
        "models": [{"id": m, "display": models[m].display, "gateway_id": models[m].gateway_id,
                    "family": models[m].family, "generation": models[m].generation} for m in used],
        "runs": [run_record(r) for r in sorted(runs, key=lambda r: (r.mode, r.task, r.variant, r.model, r.repeat))],
    }
