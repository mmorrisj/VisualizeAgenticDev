# Prompt Lab

Measures how prompt quality and model generation affect results and token cost. The full design is in [`../docs/PROMPT_LAB_SPEC.md`](../docs/PROMPT_LAB_SPEC.md). This README is for instructors and maintainers.

**Built: phases L1 to L5.** What remains is running the real study on your gateway.
- **L1:** the engine, the four tasks with their checks, one-shot runs, token accounting, storage, and the command line.
- **L2:** the AI-assisted prompt variants, the blind judge, study profiles, and the results file.
- **L3:** harness mode: sessions through the course's `mini-harness`, with limits and per-request accounting.
- **L4:** the app: the class kit (part B) with replay mode and a collector, and bring your own test (part C).
- **L5:** the site section, "Prompts across model generations", drawn from a results file.

## Install

Python 3.11 or newer.

```bash
cd prompt-lab
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock      # pinned, including the app; point pip at the internal mirror
```

Run commands from this folder with `PYTHONPATH=.`, or install the package with `pip install -e .` to get the `prompt-lab` command.

## Check the kit works (no model needed)

```bash
python -m promptlab.cli selftest      # every task: known-good answers pass, known-bad answers fail
python -m pytest -q                   # engine tests: backends, checks, runner, storage
python -m promptlab.cli run --model mock-old --model mock-new --repeats 2
python -m promptlab.cli harness --model mock-old --model mock-new --task refactor
python -m promptlab.cli summary
```

`mock-old` and `mock-new` answer from each task's prepared answers. `mock-old` gives the bad answer to the terse and technique-only prompts, and `mock-new` gives the good answer to everything. Mock results are labelled `synthetic`. They prove the pipeline, not the thesis.

## Point it at real models

1. Confirm each model's `gateway_id` in [`config/models.yaml`](config/models.yaml) and set `confirmed: true`. Every real model starts unconfirmed.
2. Set the endpoint and key in the environment, never in a file in this repository:

   ```bash
   export PROMPTLAB_GATEWAY_URL=https://gateway.internal/v1     # OpenAI-compatible: Llama and GPT models
   export PROMPTLAB_GATEWAY_KEY=...
   export PROMPTLAB_ANTHROPIC_URL=https://gateway.internal/anthropic   # optional; omit for Anthropic's API
   export PROMPTLAB_ANTHROPIC_KEY=...
   ```

   If the gateway serves the Claude models in the OpenAI-compatible shape, change their `api` to `openai_compat`.
3. Try one model and one task first:

   ```bash
   python -m promptlab.cli run --model llama-3.1-8b --task data-question --variant terse
   ```

A request that fails is stored as `error` with the reason (a missing URL, missing credentials, or an HTTP error), never dropped.

**Sonnet 4.5 retires on Anthropic's API on 30 November 2026.** Check that your gateway still serves it before the study.

## Commands

| Command | What it does |
|---|---|
| `models` | Lists configured models, flagging unconfirmed gateway ids |
| `tasks` | Lists tasks, prompt variants, and how many facts are discoverable or only-you-know |
| `check TASK FILE` | Scores an answer file with a task's checks and prints every sub-check |
| `selftest` | Runs every task's known answers through its checks |
| `run --model M [--task T] [--variant V] [--repeats N]` | Runs the matrix. `--model`, `--task`, and `--variant` repeat; tasks and variants default to all |
| `harness --model M [--task T] [--variant V] [--repeats N] [--keep DIR]` | Runs harness sessions (below). `--keep` copies each session's final working directory for inspection. `--max-requests` and `--max-input-tokens` change the limits |
| `serve [--host H] [--port P]` | Starts the app (below). Settings come from `PROMPTLAB_*` variables |
| `byot summary` / `byot purge` | Part C: verdict counts for instructors (no text); delete tests past the retention period |
| `summary` | Mean score, spread across repeats, and output tokens per task, model, and variant |
| `variants --model M [--task T]` | Writes the `ai-expanded` and `ai-interviewed` prompts with model M (the primary judge) |
| `study run --profile P` | Runs everything in a profile, one-shot runs then harness sessions; resumable: completed runs are skipped |
| `study judge --profile P` | Judges every answered run that has no judgement yet |
| `study sample --profile P --n 40 --out DIR` | Writes a sample of judged runs and a blank sheet for instructors to score |
| `study export --profile P [--human CSV]` | Writes `results/<profile>-<date>.json` and the model outputs beside it |

Every command takes `--db URL` (default `PROMPTLAB_DB_URL`, else `data/lab.db`) and `--models FILE`.

## Running the study (part A)

Profiles in `config/` say which tasks, variants, models, repeats, and judges each part uses:
- `study.yaml`: all 8 models, 6 variants, 5 repeats, plus 4 harness variants with 3 repeats;
- `class.yaml`: 2 models, 2 tasks, checks only, with an optional harness round commented out;
- `mock-study.yaml`: the whole pipeline on mock models, for trying it out.

1. **Generate the AI-assisted variants once,** with the primary judge model:

   ```bash
   python -m promptlab.cli variants --model opus-5
   ```

   Each task gets `prompts/ai-expanded.md` and `prompts/ai-interviewed.md`, plus a `.meta.yaml` beside each. The meta file records how the prompt was made and lists the requirements the model **invented**, meaning requirements that aren't among the task's facts, each with a quote from the prompt. Read that list, correct it if needed, and set `confirmed_by_instructor: true`. Prediction P4 uses only confirmed lists. Commit the prompts so every run uses the same text.

   For `ai-interviewed`, the model asks its questions and a simulated requester answers them, using only the task's fact list. The spec called for a fixed script of answers. Questions aren't known in advance, so the fact list is the fixed part instead, and the whole exchange is stored.
2. **Run, judge, and sample for validation:**

   ```bash
   python -m promptlab.cli study run --profile study
   python -m promptlab.cli study judge --profile study
   python -m promptlab.cli study sample --profile study --n 40 --out validation/
   ```

   Instructors fill in `validation/scores.csv`, scoring each criterion from 1 to 5 against the rubric in the task's `rubric.yaml`.
3. **Export:**

   ```bash
   python -m promptlab.cli study export --profile study --human validation/scores.csv
   ```

   Read the `predictions` block before publishing. Each prediction gets an automatic first reading, with the rule printed beside the outcome. An instructor confirms or corrects each one. Then commit `results/study-<date>.json` and its `outputs/` folder.
4. **Publish to the site:**

   ```bash
   python3 ../harness-site/tools/import_prompt_lab.py     # the newest results/study-*.json
   python3 ../harness-site/tools/check.py
   ```

   This rewrites `harness-site/content/prompt-lab-results.json`, which the site's section 8 draws. Commit it. The synthetic-sample banner on that page goes away once the imported study is real.

### The judge

- **It is blind.** It sees what the requester wanted, the attached files, and the answer, but never the model or the prompt variant. Answers are judged in shuffled order.
- **Every score must quote the answer.** A quote that isn't in the answer is rejected and the judge is asked once more. If it still fails, the criterion is recorded as missing, never guessed.
- **Summaries get a claim check.** The judge also lists each factual claim and must quote the report for every claim it calls supported, so invented facts get counted.
- **A second judge from another family re-scores a fixed 20% of runs.** Where the tested model shares a family with the judge, the result is flagged as possible self-preference.
- **Replies are plain JSON,** requested in the prompt and validated by the lab, rather than one provider's structured-output feature. That way any model on the gateway can be the judge.

The checks with known answers stay the primary score. Agreement between the judge, the checks and the instructors is reported in `judge_validation`.

## Harness mode (part A, and the optional class round)

A harness session gives the model a working directory and tools instead of pasted files, and lets it work for several requests. The course's own [`mini-harness`](../course/mini-harness/) runs the loop, the tools, and the system prompt, so they are identical for every model; only the model changes. Requests go through the lab's backends, so credentials, retries, effort and token counting are the same as in one-shot mode.

Each task's `harness:` block in `task.yaml` says what goes in the working directory and where the checks read the answer:

| Task | Working directory | The checks read |
|---|---|---|
| `data-question` | `schema.sql` and `incidents.db`, with a read-only `run_sql` tool | the SQL in the final message |
| `refactor` | `billing.py`, `callers.py` | `billing.py` as the session left it |
| `summarize` | `docs/incident-report.md` | the final message |
| `write-tests` | `business_days.py` | any new file matching `*test*.py` |

**Four variants per task** (`prompts/harness/`): `h-terse` gives no facts, `h-discoverable-gap` gives only the facts that are not in the files, `h-private-gap` gives only the facts that are, and `h-full` gives both. The first gap asks whether a model finds what it was not told; the second shows what no amount of exploring can recover.

**Limits:** 25 requests or 60,000 input tokens per session. Reaching either ends the session; it is stored as `hit_limit` and scores 0. The counts are checked before each request, so a final answer that crosses the line still counts. Sessions that hit a limit are not judged.

**Recorded per session:** the stop reason (finished, hit limit, or error), every request's usage, tool calls made and failed, and the full conversation. Each request's input is also split into fixed overhead (system prompt and tool definitions), conversation, and tool results. That split is an estimate, from the text at about 4 characters per token, and is labelled as one; the reported totals stay the counts.

**Unattended and not sandboxed.** The policy, [`config/harness-policy.json`](config/harness-policy.json), allows every tool and never asks a person. Commands run in a scratch directory with a scrubbed environment and a 30-second timeout, but `run_command` is not confined to that directory: a model could read other files on the machine, including the tasks' `hidden/` folders. Run the lab on a machine where that is acceptable, or set `sandbox_prefix` in the policy (for example a `bwrap` command) to confine it.

The mock models play scripted sessions: `mock-new` explores and succeeds whenever the private facts are given, and `mock-old` makes a failed tool call and wanders until the request limit without the discoverable facts. As with one-shot mode, that proves the pipeline, not the thesis.

## The app: class kit and bring your own test (parts B and C)

```bash
# Try it on the mock models: no gateway needed.
PROMPTLAB_CLASS_PROFILE=class-mock PROMPTLAB_JUDGE=mock-judge \
PROMPTLAB_BYOT_MODELS=mock-old,mock-new,mock-judge-2 PROMPTLAB_COLLECTOR=1 \
python -m promptlab.cli serve           # http://127.0.0.1:8000
```

The app uses server-rendered pages and needs no JavaScript; progress pages refresh themselves. Run it as **one process** (the default): jobs run in that process's threads. For a room, run it on an internal host with `--host 0.0.0.0`.

**Class kit** (`/class`): the `class` profile, so 2 models × `refactor` and `data-question` × `terse`, `full`, and the student's own prompt, 3 runs each. Each student's runs are stored under a profile of their own, and at most 2 requests run at once per student. The results page draws the student's points over the study's, and the student can download a results file (the section 12 format, without outputs) or submit it to the projector. The optional harness round (data-question, `h-terse` against `h-full`) shows a live request counter. To offer it, uncomment the `harness:` block in `config/class.yaml`.

**Replay mode** (`PROMPTLAB_REPLAY=1`): if the gateway is slow or down, the class kit serves the newest committed `results/study-*.json` instead, labelled "recorded". Nothing is sent to any model. Students' own prompts and bring-your-own tests cannot run, and the pages say so. Replay works at the level of whole runs, so harness sessions replay too.

**Bring your own test** (`/byot`), one step per page:
1. **Your test.** A prompt, up to 3 text files, and optionally a check: an expected value, phrases that must appear, or a shell command.
2. **Assessment.** The judge model gives a tier (`terse`, `goal`, `context`, `spec`), technique and information scores, the missing information (in your files, or only you know it), and a rewrite for each tier above yours. Anything the AI made up is listed separately under its rewrite, never blended into the text. The student agrees or disagrees with the tier and with each invented item, and may untick an item to delete it before anything runs.
3. **Rubric.** The AI drafts 3 to 5 criteria; the student edits and approves them before any result exists.
4. **Run.** The student's prompt and the rewrites they kept, on 2 or 3 models they choose, 3 runs each.
5. **Results.** Checks first, then the judge with quoted evidence, and tokens. The page says whether the AI's recommended tier actually scored higher than the student's prompt. It also says if the judge graded its own answers, or answers from its own family.

**Collector** (`PROMPTLAB_COLLECTOR=1`): `/collect` accepts class results files and `/projector` shows the whole room, refreshing every 10 seconds. If students run their own copies of the app, set `PROMPTLAB_COLLECTOR_URL` on theirs to the instructor's app.

| Variable | Default | Meaning |
|---|---|---|
| `PROMPTLAB_DB_URL` | `data/lab.db` | Database (SQLite file or Postgres URL) |
| `PROMPTLAB_CLASS_PROFILE` | `class` | Profile for the class kit; `class-mock` uses the mock models |
| `PROMPTLAB_JUDGE` | the study's primary judge | Assesses prompts, drafts rubrics, and judges part C |
| `PROMPTLAB_BYOT_MODELS` | the study's models | Models a student may choose in part C |
| `PROMPTLAB_REPLAY` | off | `1` for the newest study file, or a path |
| `PROMPTLAB_STUDY_RESULTS` | the newest study file | The study drawn under students' points |
| `PROMPTLAB_RETENTION_DAYS` | 30 | Part C tests and their runs are deleted after this |
| `PROMPTLAB_ALLOW_COMMAND_CHECKS` | off | Lets students attach shell-command checks |
| `PROMPTLAB_COLLECTOR` / `PROMPTLAB_COLLECTOR_URL` | off / none | The projector chart, here or elsewhere |
| `PROMPTLAB_CONCURRENCY` | 2 | Requests at once per student |

**Data handling** (spec section 13):
- Students may bring real work. It stays in this database and goes only to the configured gateway.
- **Retention.** Tests expire after the retention period. Expired tests and their runs are deleted when the app starts. Run `prompt-lab byot purge` daily (for example from cron) on a server that stays up.
- **Exports.** By default a student's export holds scores, tiers, verdicts and token counts; prompts and answers only if they ask. The instructor summary (`byot summary`) is counts only.
- **Logs.** The app logs request paths, never prompts or outputs.

**There are no accounts.** A student's pages are reachable by their random address, so that address is effectively private. Run the app on an internal host only.

**Command checks run on the server.** They use a temporary directory, a scrubbed environment and a 30-second timeout, but they are not sandboxed, so they are off unless you turn them on.

## The tasks

Each task folder holds:
- `task.yaml`: the facts a good answer needs, each marked *discoverable* or *private* (only the user knows it);
- `input/`: what the model sees;
- `hidden/`: what only the checks see;
- `prompts/`: one file per prompt variant;
- `answers/`: the known-good and known-bad answers;
- `checks.py`: the task's checks.

| Task | The model gets | The checks |
|---|---|---|
| `data-question` | The schema of an incident database | The SQL runs, read-only, and returns 8. Six plausible mistakes each give a different number (see `task.yaml`). |
| `refactor` | A messy billing module and its callers | 11 hidden tests pin every behaviour, including rounding ties. Public signatures must stay the same, imports must be standard library only, and the module must actually change. |
| `summarize` | A 740-word incident report | Pattern matches for 10 key facts, a 200-word limit, and customer impact in the first 40 words. The judge (L2) adds a quote for each fact and catches invented claims. |
| `write-tests` | A business-day function | The tests must pass on the correct code, use the standard library only, and catch as many of the 8 planted bugs as possible. |

**Prompt variants (L1):**
- `terse`: a few words.
- `technique`: a role, step-by-step instructions and an output format, but no facts.
- `informed`: plain sentences with every fact.
- `full`: technique plus every fact.

The files attached after the prompt are identical across variants: the prompt is the only variable.

## Measurement rules worth knowing

- **Token counts are only what the provider reports.** A count the provider didn't report is stored as `not reported`. Reasoning tokens are recorded separately where the API reports them, and otherwise marked `included in output`.
- **No sampling settings are sent** (temperature and similar), because current Claude models reject them. Every model runs at its own defaults.
- **Harness totals are summed only when every request reported the field.** One unreported request makes the session total `not reported` rather than a partial sum that looks like a count.
- **No refusal fallbacks.** A refusal is recorded as `refused` rather than silently answered by a different model.
- **Model-written code runs in a separate process,** with a scrubbed environment, a temporary directory and a 30-second timeout. That contains honest mistakes, but it is not a security boundary. Run the lab where model output may safely execute.
