# Prompt Lab

Measures how prompt quality and model generation affect results and token cost. The full design is in [`../docs/PROMPT_LAB_SPEC.md`](../docs/PROMPT_LAB_SPEC.md). This README is for instructors and maintainers.

**Built so far: phases L1 and L2.**
- **L1:** the engine, the four tasks with their checks, one-shot runs, token accounting, storage, and the command line.
- **L2:** the AI-assisted prompt variants, the blind judge, study profiles, and the results file.

Still to come: L3 adds harness mode, L4 the class app, and L5 the site section.

## Install

Python 3.11 or newer.

```bash
cd prompt-lab
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock      # pinned; point pip at the internal mirror on the secure network
```

Run commands from this folder with `PYTHONPATH=.`, or install the package with `pip install -e .` to get the `prompt-lab` command.

## Check the kit works (no model needed)

```bash
python -m promptlab.cli selftest      # every task: known-good answers pass, known-bad answers fail
python -m pytest -q                   # engine tests: backends, checks, runner, storage
python -m promptlab.cli run --model mock-old --model mock-new --repeats 2
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
| `summary` | Mean score, spread across repeats, and output tokens per task, model, and variant |
| `variants --model M [--task T]` | Writes the `ai-expanded` and `ai-interviewed` prompts with model M (the primary judge) |
| `study run --profile P` | Runs everything in a profile; resumable: completed runs are skipped |
| `study judge --profile P` | Judges every answered run that has no judgement yet |
| `study sample --profile P --n 40 --out DIR` | Writes a sample of judged runs and a blank sheet for instructors to score |
| `study export --profile P [--human CSV]` | Writes `results/<profile>-<date>.json` and the model outputs beside it |

Every command takes `--db URL` (default `PROMPTLAB_DB_URL`, else `data/lab.db`) and `--models FILE`.

## Running the study (part A)

Profiles in `config/` say which tasks, variants, models, repeats, and judges each part uses:
- `study.yaml`: all 8 models, 6 variants, 5 repeats;
- `class.yaml`: 2 models, 2 tasks, checks only;
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

   Read the `predictions` block before publishing. Each prediction gets an automatic first reading, with the rule printed beside the outcome. An instructor confirms or corrects each one. Then commit `results/study-<date>.json` and its `outputs/` folder; the site reads the newest file.

### The judge

- **It is blind.** It sees what the requester wanted, the attached files, and the answer, but never the model or the prompt variant. Answers are judged in shuffled order.
- **Every score must quote the answer.** A quote that isn't in the answer is rejected and the judge is asked once more. If it still fails, the criterion is recorded as missing, never guessed.
- **Summaries get a claim check.** The judge also lists each factual claim and must quote the report for every claim it calls supported, so invented facts get counted.
- **A second judge from another family re-scores a fixed 20% of runs.** Where the tested model shares a family with the judge, the result is flagged as possible self-preference.
- **Replies are plain JSON,** requested in the prompt and validated by the lab, rather than one provider's structured-output feature. That way any model on the gateway can be the judge.

The checks with known answers stay the primary score. Agreement between the judge, the checks and the instructors is reported in `judge_validation`.

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
- **No refusal fallbacks.** A refusal is recorded as `refused` rather than silently answered by a different model.
- **Model-written code runs in a separate process,** with a scrubbed environment, a temporary directory and a 30-second timeout. That contains honest mistakes, but it is not a security boundary. Run the lab where model output may safely execute.
