# Prompt Lab: build spec (v1)

A kit for measuring how prompt quality and model generation affect results and token cost, built for the course's "how AI has evolved" material. It has three parts: a prebaked study committed to the repository, a short live experiment students run in class, and a bring-your-own test where students apply the lab to their own task and get an AI assessment of their prompt that they can agree or disagree with.

Read with [`BUILD_SPEC.md`](BUILD_SPEC.md) (the site this feeds) and [`AGENT_PLAYBOOK.md`](AGENT_PLAYBOOK.md) (working conventions). Section 15 lists the questions still open.

---

## 1. Purpose

The course says prompting has changed: early models needed carefully engineered prompts; current models rely more on their training. This lab tests that claim with data, and sharpens it.

**Thesis to test:** prompt *technique* matters much less than it used to; *information* still matters. A harness lets a capable model find information that is in the repository, which turns a vague prompt from a correctness problem into a cost problem. Information that exists only in the user's head cannot be found by any model.

**Questions the lab answers:**

1. How much does output quality depend on the prompt, for each model? Does that dependence shrink across generations?
2. Which part of a prompt still matters on current models: technique or information?
3. Inside a harness, how much of a vague prompt's damage does a model repair by exploring, and what does that exploration cost in tokens?
4. How consistent is each model across repeated runs of the same prompt?
5. How far can an AI judge be trusted, against checks with known answers?

The lab is a classroom demonstration on a small set of tasks. It is not a benchmark, and every page that shows its results says so.

---

## 2. Three parts

| Part | Who runs it | When | Needs a model? | Output |
|---|---|---|---|---|
| **A. Prebaked study** | An instructor | Before the course, unattended | Yes, through the gateway | A results file committed to the repository; a static page in the site |
| **B. Class kit** | Each student | During the session, under 10 minutes | Yes, through the gateway | The student's results, plotted over the study's |
| **C. Bring your own test** | Each student | During or after the session | Yes, through the gateway | An AI assessment of the student's prompt, the student's verdict, scored results |

All three use one engine (section 11). Parts A and B share tasks, checks, and scoring, so a student's result is directly comparable to the study's.

**Assumption, to confirm:** students' machines reach models through the internal gateway. If some must run a model on the laptop itself, only Llama 3.1 8B is small enough; the kit supports a local endpoint (section 11.2), and the larger models' lines come from the prebaked study.

---

## 3. Models and roles

### 3.1 Models under test

Configured in `prompt-lab/config/models.yaml`, never in code. The initial set:

| Family | Ladder (oldest to newest) | What the ladder isolates |
|---|---|---|
| Llama (open weight) | Llama 3.1 8B, Llama 3.3 70B, Llama 4 Maverick | 3.1 8B vs 3.3 70B: mostly size, same era. 3.3 70B vs 4 Maverick: mostly generation. |
| OpenAI | GPT-4, GPT-5.4, GPT-5.6 Luna | The longest span in time. GPT-4 represents the era when technique mattered most. |
| Anthropic | Sonnet 4.5, Opus 5 | Generation and tier change together; read with care. |

The release order of the newest models is to be confirmed by the course owner (section 15).

Each model entry records: display name, the gateway's exact model identifier, family, generation rank within the family, API style (section 11.2), context window, whether it reports reasoning tokens, and price per token if the gateway prices usage.

### 3.2 Judges

- **Primary judge:** one frontier model scores every run (default: Opus 5).
- **Cross-check judge:** a frontier model from a different family re-scores a 20% sample (default: GPT-5.6 Luna). The report shows how often the two judges agree.
- **Self-preference flag:** any result where the tested model shares a family with the judge is flagged, and its cross-check score is shown beside it.
- Judge identities are configurable. The judges may also appear as tested models; checks with known answers lead every chart, so judge bias cannot carry a conclusion on its own.

### 3.3 Fairness rules

- Every model gets the same prompts, inputs, and settings: temperature, maximum output, request and token limits. No per-model prompt tuning: the prompt is the variable.
- A response that cannot be parsed or used (malformed JSON, code that does not parse, an empty answer) scores zero and is shown as a failure, not dropped.
- Every run records the gateway's model identifier and the date, so later re-runs are distinguishable.

---

## 4. Tasks

Four tasks, chosen so that correctness can be checked without opinion. Each lives in `prompt-lab/tasks/<task>/` with its inputs, its checks, its prompt variants, and a judge rubric.

| Task | Input | Checks with known answers |
|---|---|---|
| **refactor** | A messy Python module (about 120 lines) with callers and a hidden test suite | Hidden tests pass; public names and signatures unchanged; no new imports outside the standard library; diff size |
| **summarize** | A 3 to 4 page synthetic incident report, plus a prepared list of 10 key facts | Share of key facts present; count of claims not supported by the report (each claim checked against the source by the judge, with the quoted passage) |
| **data-question** | A small SQLite database (incidents, services, on-call) and a question with one correct number | The returned SQL runs; its result equals the expected number |
| **write-tests** | A function with 8 planted mutants (deliberate bugs) and the correct version | Generated tests pass on the correct version; share of mutants they catch |

All data is synthetic and self-contained, so the whole kit can cross the air gap.

### 4.1 Information each task needs

Each task defines the facts a good answer depends on, and classifies each one:

- **Discoverable:** present in the task's files, for example how callers use the module, or the database schema.
- **Only you know:** not in any file, for example "the summary is for the on-call manager, not engineers", "count incidents by opened date, not resolved date", or "keep Python 3.10 compatibility".

Each task has at least two facts of each kind. These definitions drive the prompt variants (section 5) and the predictions (section 9).

---

## 5. Prompt variants

### 5.1 One-shot mode: six variants per task

The prompts form a grid of technique against information, plus two AI-assisted variants.

| ID | Name | Technique | Information |
|---|---|---|---|
| `terse` | Terse | None | The bare intent, a few words ("refactor this") |
| `technique` | Technique only | Heavy: a role, step-by-step instructions, a strict output template, delimiters | Bare intent only |
| `informed` | Informed | None: plain sentences | Every fact from section 4.1 plus acceptance criteria |
| `full` | Full | Heavy | Every fact plus acceptance criteria |
| `ai-expanded` | AI-expanded | Whatever the AI adds | The `terse` prompt rewritten by the primary judge model, asked to "rewrite this into a detailed prompt". Run as written. |
| `ai-interviewed` | AI-interviewed | Whatever the AI adds | The AI first asks the questions it needs answered; a simulated requester answers them using only the task's fact list (section 4.1); it then writes the prompt. The questions, answers, and prompt are stored, so the study is reproducible. |

The `ai-expanded` and `ai-interviewed` prompts are generated once, stored in the task folder, and reused by every model, so all models see the same text.

When they are generated, the judge model lists every requirement in the new prompt that is not among the task's facts (section 4.1), and an instructor confirms the list. These **invented requirements** are stored with the prompt and counted for prediction P4.

### 5.2 Harness mode: four variants per task

| ID | Discoverable facts | Facts only you know |
|---|---|---|
| `h-terse` | Not given | Not given |
| `h-discoverable-gap` | Not given | Given |
| `h-private-gap` | Given | Not given |
| `h-full` | Given | Given |

`h-discoverable-gap` asks whether the model finds what it was not told. `h-private-gap` shows what no exploration can recover.

---

## 6. Modes

### 6.1 One-shot

One request per run: the task input and the prompt in, one answer out. The engine extracts the artifact (code, SQL, tests, summary) from the answer and runs the checks.

### 6.2 Harness

The course's own `mini-harness` (in `course/mini-harness/`) runs every model, so the loop, the tools, and the system prompt are identical and only the model changes. Its existing backends already report token usage per request.

- The task becomes a small working directory: the module and its callers; the report in `docs/`; the database with a read-only SQL tool; the function to test.
- Tools: the harness's standard read, list, search, run-command, and edit tools, plus `run_sql` (read-only) for the data question.
- Limits per session: 25 requests and 60,000 input tokens. Reaching either ends the session as a failure, recorded as "hit limit".
- After the session, the engine runs the same checks on the working directory.
- Models that cannot use tools reliably are still run; their failures are part of the result.

As built in phase L3:

- **The loop is the course's; the requests are the lab's.** `mini-harness` runs the loop, the tools, and the system prompt unchanged. Each request goes through the lab's own backends, so retries, credentials, effort and token normalization match one-shot mode. The harness gained two small hooks for this: an optional backend argument, and a per-instance tool list that `run_sql` is added to.
- **Where the checks read the answer:** `refactor` reads `billing.py` as the session left it; `write-tests` reads any new file matching `*test*.py`; `data-question` and `summarize` read the final message. The `data-question` and `summarize` prompts all say how to hand the answer back (SQL in a code block; reply with the summary). That line is the same in all four variants, because it is about format, not the task.
- **How the limits apply:** the counts are checked before each request, so a session that crosses 60,000 input tokens in a request that finishes still finishes. If the provider does not report input tokens, the limit counts the course estimate instead and the session records that it did.
- **Unattended:** the policy (`config/harness-policy.json`) allows every tool and never asks a person. Commands run in a scratch directory with a scrubbed environment and a 30-second timeout. That contains honest mistakes, but `run_command` is not confined to the directory; for stronger isolation, set `sandbox_prefix` in the policy.
- **Facts:** writing the harness prompts showed that `data-question`'s severity scope (SEV1 and SEV2) was in the informed prompt but missing from the fact list. It is now a private fact.

---

## 7. Evaluation

### 7.1 Order of evidence

1. **Checks with known answers** (section 4) produce a score from 0 to 1 per run. These are primary.
2. **The AI judge** scores what checks cannot: scope discipline, readability, and how faithful and well aimed a summary is.
3. **Judge validation:** instructors score a sample of 40 runs by hand before the study is published. The report shows agreement between the judge and instructors, and between the judge and the checks.

### 7.2 The judge

- **Blind:** the judge never sees the model name or the prompt variant. Outputs are shuffled.
- **One rubric per task**, stored in the task folder: 3 to 5 criteria, each on an anchored scale of 1 to 5 with a written description of 1, 3, and 5.
- **Evidence required:** for each score, the judge quotes the part of the output that justifies it. A score without a quote is rejected and re-requested once, then recorded as missing.
- **Structured output:** the judge returns JSON (criterion, score, quote, one-sentence reason), validated against a schema.
- **Pairwise comparisons** (optional, study only; not built in phase L2): for each task and model, `terse` against `full` and `ai-expanded` against `informed`, with presentation order randomized.

### 7.3 Reported labels

Every score shown anywhere carries one of two labels:

- **Checked:** at least one check with a known answer contributed.
- **AI-judged only:** no check was available. Shown in a lighter style, with the judge's quoted evidence one click away.

---

## 8. Token accounting

### 8.1 What is recorded per request

| Field | Source |
|---|---|
| Input tokens | Provider-reported |
| Output tokens | Provider-reported |
| Reasoning tokens | Provider-reported, where the API separates them; otherwise marked "included in output" or "not reported" |
| Cache read and cache write tokens | Provider-reported, where available |
| Characters sent and received | Measured by the engine |
| Cost | From the gateway's prices in `models.yaml`, when configured |
| Latency | Measured by the engine |

Any value the provider did not report is marked **not reported**, never filled with an estimate. The course estimator (about 4 characters per token) may be shown alongside, clearly labelled.

### 8.2 Harness sessions additionally record

- Requests per session and the stop reason: finished, hit limit, or error.
- Every request's input broken into fixed overhead (system prompt and tool definitions), conversation, and tool results, as the site's token pages draw them.
- Tool calls made and tool calls that failed.

The split into fixed overhead, conversation and tool results is an estimate (about 4 characters per token, from the request text) and is labelled as one. Use it for shares, not counts; the reported input total stays the count.

### 8.3 Comparing across families

Tokenizers differ between Llama, GPT, and Claude, so a token is not the same unit across families.

- Within a family, token counts compare directly.
- Across families, charts use characters, or cost when configured, and say so on the axis.

### 8.4 The common unit

**Tokens per correct result:** the total tokens of a set of runs divided by the number that passed their checks. This is the fair comparison between one-shot and harness modes, and between cheap and expensive models.

---

## 9. Predictions, written before the first run

These are recorded here before any data exists. The report states, for each one, whether the data supported it, contradicted it, or was mixed. Results are published either way.

| # | Prediction | What would contradict it |
|---|---|---|
| P1 | Prompt sensitivity (the gap between a model's best and worst one-shot variant) shrinks with each newer model in a family. | A newer model in a family shows a gap as large as or larger than its predecessor's on most tasks. |
| P2 | On the newest models, `technique` scores about the same as `terse`, while `informed` scores clearly higher than both. | `technique` beats `terse` on the newest models by as much as `informed` does. |
| P3 | On the oldest models (GPT-4, Llama 3.1 8B), `technique` scores clearly higher than `terse`. | No measurable gain from technique on the oldest models. |
| P4 | `ai-expanded` adds requirements nobody asked for, and does not consistently beat `informed`. | `ai-expanded` matches or beats `informed` on most tasks without invented requirements. |
| P5 | `ai-interviewed` scores at or near `informed`. | `ai-interviewed` scores no better than `ai-expanded`. |
| P6 | Harness, newest models: `h-discoverable-gap` reaches nearly the quality of `h-full`, at a higher token cost. | The quality gap stays large, or the token cost does not rise. |
| P7 | Harness, every model: `h-private-gap` scores clearly lower than `h-full`. | Some model scores as well with `h-private-gap` as with `h-full`. |
| P8 | Harness, oldest models: more requests, more failed tool calls, and more "hit limit" endings than newer models, for worse results. | Older models finish in as few requests with comparable results. |
| P9 | Newer models vary less across repeated runs, even with `terse` prompts. | Variance does not fall with generation. |
| P10 | The AI judge rates fluent but incorrect outputs too highly at least some of the time. | The judge never disagrees with the checks in the direction of leniency. |

---

## 10. The three parts in detail

### 10.1 A: the prebaked study

| Setting | Value |
|---|---|
| Models | All configured (8) |
| Tasks | All 4 |
| One-shot | 6 variants × 5 runs |
| Harness | 4 variants × 3 runs |
| Size | About 960 one-shot runs and 384 harness sessions, plus judge calls |
| Judge | Primary on every run; cross-check on a 20% sample |

- Run by an instructor with `prompt-lab study run --profile study`. It can be resumed: completed runs are skipped.
- Writes `prompt-lab/results/study-<date>.json` (section 12), which is committed. The site reads the newest committed file.
- The commit includes the date, the gateway's model identifiers, and the configuration used.

### 10.2 B: the class kit

| Setting | Value |
|---|---|
| Models | 2, chosen for contrast (default: Llama 3.1 8B and the newest available) |
| Tasks | refactor and data-question, whose checks are fast and unambiguous |
| One-shot prompts | `terse`, `full`, and the student's own prompt |
| Runs | 3 each |
| Size | About 36 calls per student |
| Harness round | Optional: data-question, `h-terse` against `h-full`, the newest model, 1 run each, with the request counter shown live |
| Judge | Off by default; checks score everything |
| Time | Under 10 minutes on a responsive gateway |

**Room logistics:**

- **Concurrency:** each student's client runs at most 2 requests at once, with backoff on rate-limit errors. The instructor checks the gateway's limits for the expected room size before class.
- **Replay mode:** if the gateway is slow or down, `--replay` serves recorded responses from the study for the reference prompts and labels every result "recorded". The student's own prompt then cannot run, and the page says so.
- **Results:** each run writes a results file. The instructor either drops the files into the report (simple), or students submit to the collector service (section 11.4) for one live chart on the projector.

### 10.3 C: bring your own test

The student brings any task. The flow, in order:

1. **Task:** a prompt; optionally an input file; optionally a check: an expected value, a command whose exit code decides pass or fail, or a list of phrases that must appear.
2. **AI assessment of the prompt.** The primary judge model returns, as structured output:
   - a **tier**: `terse`, `goal`, `context`, or `spec`. Tiers describe how much a prompt states; they correspond to the information axis of section 5.1, with `terse` at the bottom and `spec` matching `informed`;
   - a **technique** score and an **information** score, each from 1 to 3, placing the prompt on the section 5.1 grid;
   - **missing information**, each item classed as discoverable (in the provided files) or only-you-know;
   - **rewrites** at the tiers above the student's, in which every requirement the AI made up is marked as invented, with its text in a separate field, not blended into the prompt.
3. **Student verdict:** for the tier, and for each invented assumption, the student chooses agree or disagree, with an optional one-line reason. A student may delete an invented assumption from a rewrite before it runs.
4. **Rubric:** the AI drafts 3 to 5 criteria from the prompt's intent. The student approves or edits them **before any result exists**. The approved rubric is stored with the run.
5. **Run:** the student's prompt and the rewrites they kept, on 2 or 3 models they choose, 3 runs each.
6. **Score:** checks first, if given; then the judge against the approved rubric, with quoted evidence; tokens for everything. Labels as in section 7.3.
7. **Close the loop:** the results page states whether the AI's recommended tier actually scored higher than the student's prompt, so the AI's own assessment is tested by the results.

**Safeguards:**

- Where possible, the judge is a different model from those being tested. If not, the page says so.
- The AI's assessment and the student's verdict are both stored. Disagreements are kept as data and summarized for instructors across sessions: where the tier model fits students' real work and where it does not.
- Students may use real work material, so section 13 applies in full.

---

## 11. Architecture

### 11.1 Layout

```text
prompt-lab/
├── README.md                     how to run each part; for instructors
├── pyproject.toml                pinned dependencies (from the internal mirror)
├── config/
│   ├── models.yaml               models, identifiers, API style, prices
│   ├── study.yaml                profile for part A
│   ├── harness-policy.json       the mini-harness policy for unattended sessions
│   └── class.yaml                profile for part B
├── tasks/
│   └── <task>/
│       ├── task.yaml             inputs, facts (discoverable / only-you-know), limits
│       ├── input/                files given to the model
│       ├── checks.py             checks with known answers
│       ├── rubric.yaml           judge rubric
│       └── prompts/              one file per variant, including generated ones;
│                                 prompts/harness/ holds the four harness variants
├── promptlab/                    the engine (Python package)
│   ├── backends/                 openai_compat, anthropic, mock (local servers use openai_compat)
│   ├── runner.py                 one-shot runs, retries, at most N requests at once
│   ├── harness_adapter.py        drives course/mini-harness
│   ├── checks.py                 shared check helpers (tests, SQL, mutants, facts)
│   ├── judge.py                  blind judging, rubric, schema, cross-check
│   ├── assess.py                 prompt tier assessment and rubric drafting for part C
│   ├── byot.py                   part C: the flow, scoring, retention, exports
│   ├── custom_checks.py          part C: expected value, phrases, command
│   ├── classkit.py               part B: the class run and its results file
│   ├── replay.py                 replay mode: recorded runs instead of a gateway
│   ├── tokens.py                 accounting and normalization
│   ├── store.py                  SQLAlchemy models and storage
│   ├── study.py                  part A: the study pipeline and the results file (section 12)
│   ├── app/                      FastAPI app for parts B and C (section 11.4)
│   └── cli.py                    `prompt-lab` command
├── results/                      committed study results
└── tests/                        engine tests, run against the mock backend
```

### 11.2 Backends

All backends share one interface: send a request (messages, optional tools, settings) and return the text, any tool calls, and normalized usage (section 8.1).

| Backend | For |
|---|---|
| `openai_compat` | The internal gateway and any OpenAI-compatible endpoint, which is the common shape for gateways serving Llama and GPT models |
| `anthropic` | Anthropic's API, directly or through the gateway |
| `local` | A model served on the student's own machine through an OpenAI-compatible local server |
| `mock` | Deterministic scripted responses, for engine tests and development without a model |
| `replay` | Recorded responses from a results file, for class replay mode |

Backends reuse the token-usage normalization already in `course/mini-harness/backends.py`, and extend it with reasoning tokens.

### 11.3 Storage

- SQLAlchemy models: runs, requests, checks, judgements, assessments, verdicts, rubrics.
- SQLite by default, so an instructor can run everything on one machine; Postgres by setting a connection URL, for a shared, persistent store.
- The committed results file (section 12) is the hand-off format. The site never reads the database.

### 11.4 The app (parts B and C)

A small FastAPI app with a plain server-rendered page, no front-end build step.

- **Class kit:** start a run, see results arrive, see one's own points over the study's.
- **Bring your own test:** the section 10.3 flow, one step per screen.
- **Collector (optional):** accepts class results files and serves one live chart for the projector.
- Runs on the instructor's machine or an internal host; the gateway URL and credentials come from environment configuration, never from the repository.

As built in phase L4:

- **Location.** The app is the package `promptlab/app/`, not a top-level `app/`, so it installs and imports with the engine. Start it with `prompt-lab serve`. Settings come from `PROMPTLAB_*` environment variables (README).
- **One process.** Jobs run in threads of the app's process, so it runs as a single worker. Runs are stored as they finish, so a restart loses only the progress counter.
- **Replay mode** serves whole recorded runs from a results file, harness sessions included, labelled "recorded". It never calls a model, which also means a student's own prompt or test cannot run, and the pages say so.
- **Part C.** Rewrites keep invented requirements in a separate list. Each is kept by default; the student unticks it to delete it, and must give an agree or disagree verdict on every one. The judge sees the student's own prompt (what they wanted) and the approved rubric, never the model or which prompt produced the answer. Shell-command checks run on the server, so they are off unless the instructor turns them on.
- **Retention.** Expired part C tests are deleted, with their runs, when the app starts and by `prompt-lab byot purge`.
- **Access.** There are no accounts. Students' pages live at random addresses, so the app belongs on an internal host.

### 11.5 Dependencies

- The engine: Python 3.11+ (the Anthropic SDK's HTTP dependencies need it), `httpx`, `pydantic`, `PyYAML`, `SQLAlchemy`.
- The app adds `fastapi`, `uvicorn`, and `jinja2`.
- All pinned in `pyproject.toml` and installed from the internal mirror.
- The site (`harness-site/`) remains dependency-free and offline. It only reads the committed results file.

---

## 12. Results file format

`prompt-lab/results/study-<date>.json`, also produced by class runs and exports from part C.

```json
{
  "format": 1,
  "created": "2026-12-01",
  "profile": "study",
  "note": "Classroom demonstration on four tasks; not a benchmark.",
  "models": [{"id": "llama-3.1-8b", "gateway_id": "...", "family": "llama", "generation": 1}],
  "judges": {"primary": "opus-5", "cross_check": "gpt-5.6-luna"},
  "runs": [
    {
      "id": "...",
      "mode": "one-shot",
      "task": "refactor",
      "variant": "terse",
      "model": "llama-3.1-8b",
      "repeat": 1,
      "status": "ok",
      "checks": {"score": 0.75, "details": {"hidden_tests": "6/8"}},
      "judge": {"score": 3.4, "criteria": [{"name": "...", "score": 3, "quote": "...", "reason": "..."}],
                "cross_check": null, "self_preference": false},
      "label": "checked",
      "tokens": {"input": 812, "output": 455, "reasoning": "not reported", "cache_read": 0, "cache_write": 0},
      "chars": {"sent": 3290, "received": 1802},
      "requests": 1,
      "stop": "finished",
      "output_ref": "outputs/....txt"
    }
  ],
  "judge_validation": {"sample": 40, "agreement_with_humans": 0.0, "agreement_with_checks": 0.0},
  "predictions": [{"id": "P1", "outcome": "supported | contradicted | mixed", "note": "..."}]
}
```

Model outputs are stored beside the file (`results/outputs/`), so any score can be traced to the text it judged.

Harness runs add a `session` object: the stop reason, the limits and which one was hit, tool calls made and failed, which tools were used, where the answer was read from, and each request's usage and estimated split. The full conversation is stored beside the outputs (`<run>.session.json`) and linked by `transcript_ref`.

---

## 13. Data handling

- Students' own prompts and files may contain real work. Everything stays on the internal gateway and the instructor's machine or internal host.
- Storage location and retention are set in configuration. The default deletes part C records after 30 days.
- Exports from part C include prompts and outputs only if the student chooses so; the default exports scores, tiers, verdicts, and token counts.
- Nothing from part C is committed to the repository unless the course owner chooses to publish an anonymized summary.
- Logging follows the environment's policy; the app logs no prompt or output text by default.

---

## 14. Site integration

A new section in the site, placed with the evolution material, built from the newest committed results file only. It follows `BUILD_SPEC.md`: static, offline, no dependencies, and accessible.

**Charts:**

1. **Prompt sensitivity by model:** one line per model across the one-shot variants, every run shown as a dot so spread is visible. Grouped by family ladder.
2. **Technique against information:** the 2 × 2 grid from section 5.1, per model, shaded by score.
3. **Harness:** quality and tokens for the four harness variants per model; how far `h-discoverable-gap` closes the gap, and at what cost.
4. **Where harness tokens go:** fixed overhead, conversation, tool results, output, and reasoning, reusing the site's block visuals.
5. **Tokens per correct result:** one-shot against harness, per model.
6. **Judge against checks:** a scatter, with disagreements highlighted and one click to the quoted evidence.
7. **Predictions:** the section 9 table with each outcome.

Every chart states the study date, the four-task scope, and "not a benchmark". Cross-family token charts use characters or cost, as section 8.3 requires.

As built in phase L5:

- **Section 8 of 9,** "Prompts across model generations", placed before the final review. All seven charts are built, with a task filter over those that have per-task data.
- **How the site gets the data.** A static site cannot list a folder to find the newest file, so `harness-site/tools/import_prompt_lab.py` reads one results file and writes the aggregates the page needs to `content/prompt-lab-results.json`. Publishing a study is: export, import, commit.
- **Synthetic sample.** Until a real study is committed, the content file is a sample from the mock models and the page says so in a banner. This is a provisional answer to open question 5.
- **Not color alone.** Model generations differ by marker shape, harness prompts by a letter under each bar, and judge disagreements by shape. Each chart has a text alternative, and the main ones a table of the numbers.
- **Judge against checks.** Runs with the same pair of scores are drawn as one point with a count. A disagreement uses prediction P10's rule (judge at least 0.75 while checks are under 0.5, or the reverse) and opens the judge's quoted evidence, by mouse or keyboard.
- **Cost per correct result** is shown in characters for every model, with tokens in the table for comparisons within a family. Cost is not shown: no prices are configured yet (open question 3).

---

## 15. Open questions for the course owner

1. **Model order and identifiers:** confirm the release order of GPT-5.4, GPT-5.6 Luna, and Opus 5, and the gateway's identifiers for all eight models.
2. **Local models:** do any students need to run a model on their own machine (section 2)?
3. **Pricing:** does the gateway price usage? If so, cost replaces characters on cross-family charts.
4. **Judges:** confirm Opus 5 as primary and GPT-5.6 Luna as cross-check.
5. **Before the real study exists:** should the site section ship with a clearly labelled synthetic sample generated by the mock backend, or stay hidden until the first real study is committed?
6. **Retention:** is 30 days right for part C records, and may an anonymized summary of verdicts be published?

---

## 16. Build phases

Each phase ends with a pull request and a stop for review, as in `AGENT_PLAYBOOK.md`.

| Phase | Deliverable | Done when |
|---|---|---|
| L1 | Engine core: backends (mock, openai_compat, anthropic), one-shot runner, token accounting, storage, CLI; the four tasks with inputs and checks | Engine tests pass against the mock backend; every check passes on a known-good answer and fails on a known-bad one |
| L2 | Prompt variants, including the generated `ai-expanded` and `ai-interviewed` prompts; the judge with rubric, schema, blind ordering, cross-check, and self-preference flags; results export | A full study runs end to end on the mock backend and produces a valid results file |
| L3 | Harness mode through `mini-harness`: the working directories, `run_sql`, limits, per-request accounting | Harness sessions run end to end on the mock backend; limits end sessions as specified |
| L4 | The app: class kit, replay mode, part C flow (assessment, verdicts, rubric approval, scoring), optional collector | Part C runs end to end on the mock backend; replay mode works with no gateway |
| L5 | Site section built from the results file | Section 14 charts render from a sample file; the site's quality checks pass |
| Study | The real study, run by the course owner on the secure system | `study-<date>.json` committed; predictions table filled in |

Real model runs cannot happen in the development environment unless the course owner provides access to an endpoint. Everything up to L5 is built and tested against the mock backend, and optionally one real model.
