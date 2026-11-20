"""One-shot runs (spec section 6.1): one request in, one answer out, then the checks."""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Iterable

from .backends import BackendError, Request, backend_for
from .config import ModelConfig
from .store import Run, Store
from .tasks import load_task
from .tokens import Usage

STATUS_FOR_STOP = {"end": "ok", "refusal": "refused", "max_tokens": "max_tokens"}


def run_one(task_id: str, variant: str, model: ModelConfig, *, repeat: int = 1,
            profile: str = "adhoc", store: Store | None = None, backend=None) -> Run:
    """Run one task with one prompt variant on one model, check it, and store it.

    A failed request is stored as status "error" with no score, so failures are
    visible in results rather than silently dropped. A refusal or a truncated
    answer is still checked (it usually scores zero) and keeps its status.
    """
    task = load_task(task_id)
    user_message = task.build_user_message(variant)
    request = Request(messages=[{"role": "user", "content": user_message}],
                      meta={"task": task_id, "variant": variant})
    run = Run(profile=profile, mode="one-shot", task=task_id, variant=variant, model=model.id,
              gateway_id=model.gateway_id, repeat=repeat, effort=model.effort or "",
              prompt=user_message, chars_sent=len(user_message))
    backend = backend or backend_for(model)
    try:
        response = backend.complete(request, model)
    except BackendError as err:
        run.status, run.error, run.tokens, run.label = "error", str(err), Usage().to_dict(), "error"
    else:
        run.output = response.text
        run.chars_received = len(response.text)
        run.tokens = response.usage.to_dict()
        run.latency_s = round(response.latency_s, 3)
        run.stop = response.stop
        run.served_model = response.served_model
        run.status = STATUS_FOR_STOP.get(response.stop, "ok")
        result = task.check(response.text)
        run.score = result.score
        run.check_details = json.loads(json.dumps(result.to_dict(), default=str))
        run.label = "synthetic" if response.usage.synthetic else "checked"
    return (store or Store()).add(run)


def run_matrix(task_ids: Iterable[str], variants: Iterable[str] | None, models: Iterable[ModelConfig],
               repeats: int = 1, *, profile: str = "adhoc", store: Store | None = None,
               on_run: Callable[[Run], None] | None = None) -> list[Run]:
    """Every task x variant x model x repeat. Variants default to each task's own list."""
    store = store or Store()
    runs = []
    models = list(models)
    for task_id in task_ids:
        task_variants = list(variants) if variants else load_task(task_id).variants()
        for variant, model, rep in itertools.product(task_variants, models, range(1, repeats + 1)):
            run = run_one(task_id, variant, model, repeat=rep, profile=profile, store=store)
            runs.append(run)
            if on_run:
                on_run(run)
    return runs
