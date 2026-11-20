# Prompt Lab

Measures how prompt quality and model generation affect results and token cost. The full design is in [`../docs/PROMPT_LAB_SPEC.md`](../docs/PROMPT_LAB_SPEC.md). This README is for instructors and maintainers.

**Built so far: phase L1.** That covers the engine, the four tasks with their checks, one-shot runs, token accounting, storage, and the command line. Phase L2 adds the AI-assisted prompt variants, the judge, and the results file. L3 adds harness mode, L4 the class app, and L5 the site section.

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

Every command takes `--db URL` (default `PROMPTLAB_DB_URL`, else `data/lab.db`) and `--models FILE`.

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
