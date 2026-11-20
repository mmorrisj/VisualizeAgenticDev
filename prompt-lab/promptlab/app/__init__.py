"""The Prompt Lab app (spec section 11.4): the class kit, bring your own test, and the collector.

A small FastAPI app with server-rendered pages and no front-end build step.
Progress pages refresh themselves; nothing needs JavaScript.

    prompt-lab serve            (or: uvicorn --factory promptlab.app:create_app)

Run it as one process: jobs run in threads of that process. It is meant for an
internal host or the instructor's machine. There are no accounts: a student's
pages are reachable by their random address only, so treat the address as private.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from markupsafe import Markup

from .. import assess, byot, classkit
from ..config import load_models
from ..custom_checks import CustomCheck
from ..profiles import load_profile
from ..replay import Recorded
from ..runner import OWN
from ..store import Collected, CustomTest, Store
from ..tasks import load_task
from .charts import dot_chart
from .jobs import Job, JobRunner
from .settings import Settings

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
MAX_UPLOAD = byot.MAX_FILES_CHARS


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    models = load_models(settings.models_path)
    profile = load_profile(settings.class_profile)
    profile.check_models(models)
    store = Store(settings.db_url)
    store.purge_expired()
    recorded = Recorded(settings.replay) if settings.replay else None
    study_doc = (json.loads(Path(settings.study_results).read_text(encoding="utf-8"))
                 if settings.study_results and Path(settings.study_results).is_file() else None)
    jobs = JobRunner(inline=settings.inline_jobs)
    judge = models.get(settings.judge) if settings.judge else None
    byot_models = [models[m] for m in settings.byot_models if m in models]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        jobs.shutdown()

    app = FastAPI(title="Prompt Lab", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings, app.state.store, app.state.jobs = settings, store, jobs

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, name, {"settings": settings, "replay": recorded is not None,
                                                          **context}, status_code=status_code)

    # --- home ----------------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "index.html", profile=profile, judge=judge,
                    study=study_doc is not None, study_synthetic=bool(study_doc and study_doc.get("synthetic")))

    # --- part B: the class kit ---------------------------------------------------------------
    def reference_prompts():
        return {t: {v: load_task(t).prompt(v) for v in profile.variants} for t in profile.task_list()}

    @app.get("/class", response_class=HTMLResponse)
    def class_form(request: Request):
        return page(request, "class_form.html", profile=profile, references=reference_prompts())

    @app.post("/class")
    async def class_start(request: Request):
        form = await request.form()
        own = {t: str(form.get(f"own_{t}", "")) for t in profile.task_list()}
        harness_round = bool(form.get("harness_round")) and profile.harness is not None
        items = classkit.plan(profile, own, harness_round)
        sid = classkit.new_session_profile()
        skipped = classkit.skipped_in_replay(items, recorded) if recorded else []
        job = Job(id=sid, total=len(items) - len(skipped),
                  info={"student": str(form.get("student", ""))[:64], "own": {t: p for t, p in own.items() if p.strip()},
                        "skipped": [{"key": i.key, "why": why} for i, why in skipped]})

        def work(job: Job):
            def counter(item, record):
                job.requests[item.key] = record["request"]
            classkit.run_class(items, models, store, sid, recorded=recorded, workers=settings.concurrency,
                               on_run=job.tick, on_request=counter)

        jobs.start(job, work)
        return RedirectResponse(f"/class/{sid}", status_code=303)

    def class_runs(sid: str):
        if not sid.startswith("class-"):
            raise HTTPException(404)
        return store.runs(profile=sid)

    @app.get("/class/{sid}", response_class=HTMLResponse)
    def class_page(request: Request, sid: str):
        runs = class_runs(sid)
        job = jobs.get(sid)
        if job is None and not runs:
            raise HTTPException(404, "No class run here. Runs from before a restart keep their results only.")
        running = job is not None and job.status == "running"
        charts, tables = {}, {}
        for task in profile.task_list():
            variants = list(profile.variants) + ([OWN] if any(r.variant == OWN and r.task == task for r in runs) else [])
            mine = [(r.variant, r.model, r.score) for r in runs if r.task == task and r.mode == "one-shot"]
            study = [(r["variant"], r["model"], r["checks"]["score"]) for r in (study_doc or {}).get("runs", [])
                     if r["task"] == task and r["mode"] == "one-shot" and r["model"] in profile.models]
            charts[task] = Markup(dot_chart(f"{task}: your runs over the study's", variants, profile.models,
                                            mine, study))
            tables[task] = _table(runs, task, "one-shot")
        harness = [r for r in runs if r.mode == "harness"]
        return page(request, "class_run.html", sid=sid, job=job, running=running, runs=runs, charts=charts,
                    tables=tables, harness=harness, profile=profile, study=study_doc is not None,
                    study_synthetic=bool(study_doc and study_doc.get("synthetic")))

    def class_document(sid: str) -> dict:
        runs = class_runs(sid)
        job = jobs.get(sid)
        return classkit.class_results(runs, models, sid, student=(job.info.get("student", "") if job else ""),
                                      recorded=recorded is not None)

    @app.get("/class/{sid}/results.json")
    def class_download(sid: str):
        doc = class_document(sid)
        return JSONResponse(doc, headers={"content-disposition": f'attachment; filename="{sid}.json"'})

    @app.post("/class/{sid}/submit", response_class=HTMLResponse)
    def class_submit(request: Request, sid: str):
        doc = class_document(sid)
        if settings.collector_url:
            try:
                httpx.post(settings.collector_url.rstrip("/") + "/collect", json=doc, timeout=20).raise_for_status()
            except httpx.HTTPError as err:
                return page(request, "message.html", status_code=502, title="Not submitted",
                            text=f"The collector did not accept the results: {err}", back=f"/class/{sid}")
        elif settings.collector:
            store.add(Collected(student=doc["student"], document=doc))
        else:
            return page(request, "message.html", status_code=400, title="No collector",
                        text="This app has no collector. Download your results file and hand it in instead.",
                        back=f"/class/{sid}")
        return page(request, "message.html", title="Submitted", text="Your results are on the projector chart.",
                    back=f"/class/{sid}")

    # --- the collector -------------------------------------------------------------------------
    @app.post("/collect")
    async def collect(request: Request):
        if not settings.collector:
            raise HTTPException(404)
        try:
            doc = await request.json()
        except ValueError:
            raise HTTPException(400, "send a class results file as JSON") from None
        if not isinstance(doc, dict) or doc.get("format") != 1 or doc.get("kind") != "class" \
                or not isinstance(doc.get("runs"), list):
            raise HTTPException(400, "not a class results file (format 1)")
        store.add(Collected(student=str(doc.get("student", ""))[:64], document=doc))
        return {"ok": True, "collected": len(store.all(Collected))}

    @app.get("/projector", response_class=HTMLResponse)
    def projector(request: Request):
        if not settings.collector:
            raise HTTPException(404)
        docs = [c.document for c in store.all(Collected)]
        runs = [r for d in docs for r in d.get("runs", []) if r.get("mode") == "one-shot"]
        charts = {}
        for task in profile.task_list():
            variants = list(dict.fromkeys(list(profile.variants) + [r["variant"] for r in runs if r["task"] == task]))
            points = [(r["variant"], r["model"], r["checks"]["score"]) for r in runs if r["task"] == task]
            models_seen = list(dict.fromkeys([r["model"] for r in runs if r["task"] == task])) or profile.models
            charts[task] = Markup(dot_chart(f"{task}: the whole room", variants, models_seen, points))
        means = defaultdict(list)
        for r in runs:
            if r["checks"]["score"] is not None:
                means[(r["task"], r["variant"], r["model"])].append(r["checks"]["score"])
        rows = [{"task": t, "variant": v, "model": m, "n": len(s), "mean": statistics.mean(s)}
                for (t, v, m), s in sorted(means.items())]
        return page(request, "projector.html", students=len(docs), charts=charts, rows=rows)

    # --- part C: bring your own test --------------------------------------------------------------
    def need_judge():
        if judge is None:
            raise HTTPException(503, "No judge model is configured (PROMPTLAB_JUDGE).")
        return judge

    def get_test(test_id: str) -> CustomTest:
        test = store.get(CustomTest, test_id) if len(test_id) == 32 else None
        if test is None:
            raise HTTPException(404, "No test here. Tests are deleted after the retention period.")
        return test

    @app.get("/byot", response_class=HTMLResponse)
    def byot_form(request: Request):
        return page(request, "byot_new.html", error="", values={})

    @app.post("/byot", response_class=HTMLResponse)
    async def byot_create(request: Request, prompt: str = Form(""), student: str = Form(""),
                          check_kind: str = Form("none"), expected: str = Form(""), phrases: str = Form(""),
                          command: str = Form(""), files: list[UploadFile] | None = None):
        values = {"prompt": prompt, "student": student, "check_kind": check_kind, "expected": expected,
                  "phrases": phrases, "command": command}
        try:
            if recorded is not None:
                raise byot.InputError("This server is in replay mode: nothing can be sent to a model.")
            texts = {}
            for upload in files or []:
                if not upload.filename:
                    continue
                raw = await upload.read(MAX_UPLOAD + 1)
                if len(raw) > MAX_UPLOAD:
                    raise byot.InputError(f"{upload.filename} is larger than {MAX_UPLOAD // 1000} KB.")
                try:
                    texts[Path(upload.filename).name] = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raise byot.InputError(f"{upload.filename} is not a text file. Attach text files only.") from None
            try:
                check = CustomCheck(kind=check_kind, expected=expected,
                                    phrases=[p.strip() for p in phrases.splitlines() if p.strip()], command=command)
            except ValueError as err:
                raise byot.InputError(str(err).split("\n")[-1].strip()) from None
            test = byot.create_test(store, prompt, texts, check, student=student,
                                    retention_days=settings.retention_days,
                                    allow_command_checks=settings.allow_command_checks)
        except byot.InputError as err:
            return page(request, "byot_new.html", status_code=400, error=str(err), values=values)
        # A model call: off the event loop, so other students' pages keep working meanwhile.
        await run_in_threadpool(byot.run_assessment, store, test, need_judge())
        return RedirectResponse(f"/byot/{test.id}", status_code=303)

    @app.get("/byot/{test_id}", response_class=HTMLResponse)
    def byot_page(request: Request, test_id: str):
        test = get_test(test_id)
        context = {"test": test, "expires": test.expires.date().isoformat()}
        if not test.assessment:
            return page(request, "byot_assess_failed.html", **context)
        assessment = byot.assessment_of(test)
        context["assessment"] = assessment
        context["tiers"] = assess.TIERS
        context["tier_meaning"] = assess.TIER_MEANING
        if not test.verdict:
            return page(request, "byot_assessment.html", **context)
        if not test.rubric_approved:
            if not test.rubric:
                byot.run_rubric_draft(store, test, need_judge())
            return page(request, "byot_rubric.html", **context, rubric=test.rubric)
        if test.status == "ready":
            return page(request, "byot_run.html", **context, choices=byot_models, judge=judge,
                        prompts=byot.prompts_to_run(test), error="")
        job = jobs.get(test.id)
        runs = store.runs(task=test.task_key)
        return page(request, "byot_results.html", **context, job=job, runs=runs,
                    running=test.status == "running" and job is not None and job.status == "running",
                    summary=test.summary, judge_failed=sum(1 for r in runs if r.judge and r.judge.get("score") is None))

    @app.post("/byot/{test_id}/assess")
    def byot_reassess(test_id: str):
        test = get_test(test_id)
        if not test.assessment:
            byot.run_assessment(store, test, need_judge())
        return RedirectResponse(f"/byot/{test_id}", status_code=303)

    @app.post("/byot/{test_id}/verdict", response_class=HTMLResponse)
    async def byot_verdict(request: Request, test_id: str):
        test = get_test(test_id)
        form = await request.form()
        assessment = byot.assessment_of(test)
        invented = {}
        for rewrite in assessment.rewrites:
            for item in rewrite.invented:
                key = f"{rewrite.tier}/{item.id}"
                choice = form.get(f"agree::{key}")
                if choice in ("agree", "disagree"):
                    invented[key] = {"agree": choice == "agree", "reason": str(form.get(f"reason::{key}", "")),
                                     "keep": bool(form.get(f"keep::{key}"))}
        try:
            byot.record_verdict(store, test, tier_agree=form.get("tier_agree") == "agree",
                                tier_reason=str(form.get("tier_reason", "")), invented=invented,
                                run_tiers=[str(t) for t in form.getlist("run_tier")])
        except byot.InputError as err:
            return page(request, "byot_assessment.html", status_code=400, test=test, assessment=assessment,
                        tiers=assess.TIERS, tier_meaning=assess.TIER_MEANING, error=str(err),
                        expires=test.expires.date().isoformat())
        return RedirectResponse(f"/byot/{test_id}", status_code=303)

    @app.post("/byot/{test_id}/rubric", response_class=HTMLResponse)
    async def byot_rubric(request: Request, test_id: str):
        test = get_test(test_id)
        form = await request.form()
        criteria = []
        for i in range(5):
            cid = str(form.get(f"id_{i}", "")).strip()
            if not cid:
                continue
            criteria.append({"id": cid, "name": str(form.get(f"name_{i}", "")).strip(),
                             "description": str(form.get(f"description_{i}", "")).strip(),
                             "anchors": {a: str(form.get(f"anchor{a}_{i}", "")).strip() for a in ("1", "3", "5")}})
        try:
            rubric = assess.Rubric.model_validate({"criteria": criteria})
            byot.approve_rubric(store, test, rubric)
        except (ValueError, byot.InputError) as err:
            message = str(err) if isinstance(err, byot.InputError) else (
                "Give 3 to 5 criteria, each with a lowercase id (letters, digits, hyphens) and all three anchors.")
            return page(request, "byot_rubric.html", status_code=400, test=test, assessment=byot.assessment_of(test),
                        rubric={"criteria": criteria}, error=message, expires=test.expires.date().isoformat())
        return RedirectResponse(f"/byot/{test_id}", status_code=303)

    @app.post("/byot/{test_id}/run", response_class=HTMLResponse)
    async def byot_run(request: Request, test_id: str):
        test = get_test(test_id)
        form = await request.form()
        chosen = [models[m] for m in form.getlist("model") if m in {c.id for c in byot_models}]
        try:
            byot.plan_run(store, test, chosen, need_judge())
        except byot.InputError as err:
            return page(request, "byot_run.html", status_code=400, test=test, assessment=byot.assessment_of(test),
                        choices=byot_models, judge=judge, prompts=byot.prompts_to_run(test), error=str(err),
                        expires=test.expires.date().isoformat())
        total = len(test.plan["prompts"]) * len(test.plan["models"]) * test.plan["repeats"]
        jobs.start(Job(id=test.id, total=total),
                   lambda job: byot.run_test(store, test, models, workers=settings.concurrency, on_run=job.tick))
        return RedirectResponse(f"/byot/{test_id}", status_code=303)

    @app.get("/byot/{test_id}/export.json")
    def byot_export(test_id: str, text: bool = False):
        test = get_test(test_id)
        doc = byot.export_test(test, store.runs(task=test.task_key), include_text=text)
        return JSONResponse(doc, headers={"content-disposition": f'attachment; filename="my-test-{test_id[:8]}.json"'})

    return app


def _table(runs, task: str, mode: str) -> list[dict]:
    cells = defaultdict(list)
    for r in runs:
        if r.task == task and r.mode == mode:
            cells[(r.variant, r.model)].append(r)
    rows = []
    for (variant, model), rs in sorted(cells.items()):
        scores = [r.score for r in rs if r.score is not None]
        outs = [r.tokens.get("output") for r in rs if isinstance((r.tokens or {}).get("output"), int)]
        rows.append({"variant": variant, "model": model, "runs": len(rs),
                     "scores": ", ".join(f"{s:.2f}" for s in scores) or "-",
                     "mean": f"{statistics.mean(scores):.2f}" if scores else "-",
                     "output_tokens": f"{statistics.mean(outs):.0f}" if outs else "not reported",
                     "labels": ", ".join(sorted({r.label for r in rs})),
                     "errors": sum(r.status == "error" for r in rs)})
    return rows
