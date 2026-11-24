# Dataset Discovery Challenge: build spec (v1)

An advanced, in-person exercise for the agentic development course. Teams get questions but are not told which of about 200 datasets answers them. They design the tools that let an agent find the right data and answer correctly, within a fixed budget.

Read with [`PROMPT_LAB_SPEC.md`](PROMPT_LAB_SPEC.md), whose engine this reuses, and [`AGENT_PLAYBOOK.md`](AGENT_PLAYBOOK.md) for working conventions. Section 14 lists the questions still open; three of them change the design and are marked.

---

## 1. Purpose

Most people who use agents never design the tools an agent works with. This exercise makes them do it, on data large enough that bad designs fail visibly.

**What it teaches:**

1. **An agent cannot read everything.** Listing 200 datasets with their schemas fills the context before any work starts.
2. **Tool design decides the outcome.** What a catalogue search returns matters more than how the prompt is worded.
3. **The dangerous failure is a confident answer from the wrong dataset.** Names mislead, and two datasets often look equally right.
4. **Sometimes the right answer is "this data cannot tell you".**

It extends the Prompt Lab's finding that a harness turns information in the files into a token cost. Here the "files" are too large to explore naively, so the cost is the design problem.

**Not a benchmark.** Eight questions on one organization's data, for teaching.

---

## 2. Assumptions

These come from the course owner's description, not from seeing the data. Each is an open question in section 14.

| Assumption | If it is wrong |
|---|---|
| The datasets are tabular and can be queried with SQL through one read-only connection | See section 13: documents need a retrieval tool and judged answers |
| A raw catalogue can be exported: dataset names, column names and types, and whatever descriptions exist | Instructors build a minimal one from the database's own metadata |
| Aggregate query results may be sent to the model gateway; raw rows may not, by default | Section 9's defaults already assume the stricter case |
| Teams of 2 to 4, on machines that reach the gateway and the data | The kit also runs fully offline on the synthetic catalogue (section 10) |

---

## 3. What teams build

Teams do not write the agent. Everyone uses the same `mini-harness` loop, system prompt and model, so the only difference between teams is their design.

### 3.1 Four tools

| Tool | Purpose | What the team decides |
|---|---|---|
| `search_catalog(query)` | Find candidate datasets | What text it searches, how many results it returns, which fields each result shows |
| `describe_dataset(name)` | Inspect one dataset | Which columns to show and how, and which notes (owner, date range, row count, known issues) |
| `sample_rows(name)` | Look at example rows | Whether to offer it at all, how many rows, which columns. Off by default (section 9) |
| `run_query(sql)` | Compute an answer | The row cap, and whether results return whole or summarised |

The agent has no other tools. It cannot list every dataset, read files, or run commands.

### 3.2 Catalogue notes

Teams also write the descriptions the search runs over. The raw catalogue is their starting point, and it will be thin or inconsistent. They decide what to add: plain-language descriptions, date coverage, which dataset supersedes which, common names for the same thing.

This is the main design work. A team that spends its time on tool settings and none on the notes should lose to one that does the opposite, and the debrief should show that.

### 3.3 How a design is expressed

A team's design is one folder:

```text
teams/<team>/
├── tools.yaml        settings for the four tools
├── notes.yaml        the team's catalogue notes, by dataset name
└── tools.py          optional: Python overrides for teams that want more than settings
```

- **`tools.yaml` first.** Settings cover result counts, shown fields, row caps and summarising. Most teams should finish with settings and notes alone, so the exercise fits the time and designs stay comparable.
- **`tools.py` is an escape hatch.** A team may replace a tool's result formatting or search ranking with a Python function. It runs on the team's own machine, inside the hard limits of section 9, which the team cannot change.

---

## 4. The questions

Eight questions, each with an answer an instructor has verified by hand.

| Kind | Count | What makes it hard |
|---|---|---|
| Straightforward | 2 | Nothing: one dataset with an honest name. Shows the pipeline works |
| Misleading | 3 | Two plausible datasets. One is stale, partial, or defines the measure differently. Only the description, the date range or the row counts tell them apart |
| Needs two datasets | 2 | The answer needs a join across datasets that do not reference each other by name |
| Unanswerable | 1 | No dataset covers it. The correct answer says so |

**Practice and held-back sets.** Three questions are for practice: one straightforward, one misleading, one needing two datasets. Five are held back for the scored run and are not distributed until then. Without a held-back set, teams tune their notes to the practice questions and the score rewards it.

**Each question records:**

- the text given to the agent;
- the expected value and a tolerance;
- every acceptable set of datasets;
- for misleading questions, the wrong dataset and the wrong value it produces, so the scorer can name the trap a team fell into;
- the instructor's verification query, kept out of the team's reach.

**Writing misleading questions.** Good candidates in a real estate of 200 datasets: a table and its archived predecessor; a raw table and a deduplicated one; two systems that both record "customers" or "orders"; a daily table and a monthly rollup that disagree at the edges. An instructor who knows the data should find three in an hour. Section 10's synthetic catalogue plants the same kinds.

---

## 5. Answer format

The agent's final message must end with two lines. This instruction is part of the fixed prompt, the same for every team.

```text
DATASETS: orders_2026, customers_current
ANSWER: 1284
```

For an unanswerable question:

```text
DATASETS: none
ANSWER: cannot be answered
```

A final message without these lines scores zero for that session.

---

## 6. Scoring

### 6.1 One session

| Check | Rule |
|---|---|
| Value | `ANSWER` equals the expected value within the tolerance. For the unanswerable question, `ANSWER` is "cannot be answered" |
| Datasets | The `DATASETS` line matches an acceptable set, and each named dataset was actually queried in the session, read from the session log |
| Finished | The session ended on its own, not by hitting a limit |

A session is **correct** only if all three hold. A right number from the wrong dataset is wrong: it was luck, and next quarter it will not be.

Saying "cannot be answered" to an answerable question is wrong. This stops a design that refuses everything from scoring on the unanswerable question.

### 6.2 A team

Each held-back question runs twice, because models vary between runs.

1. **Correct sessions**, out of 10. This ranks first.
2. **Tokens per correct session:** all tokens the 10 sessions used, divided by the number correct. This breaks ties and is the number the debrief is about.
3. **Reported beside them, not ranked:** requests per session, failed tool calls, sessions that hit a limit, and for each misleading question whether the team fell into the trap.

### 6.3 Limits

Each session stops at 25 requests or 60,000 input tokens, the limits the Prompt Lab's harness mode already enforces. Hitting either is a failure.

---

## 7. Running the session

About two hours.

| Time | What happens |
|---|---|
| 10 min | **Baseline.** The instructor runs the agent with naive tools that return everything. It hits the token limit on screen |
| 50 min | **Design.** Teams write notes and settings, testing on the three practice questions |
| 20 min | **Scored run.** The five held-back questions, twice each. No changes allowed once it starts |
| 20 min | **Swap.** Each team runs another team's design and reads its session logs |
| 20 min | **Debrief** around the leaderboard |

**Debrief questions:**

- Which design choice separated the top teams from the rest: notes or settings?
- Who fell into which trap, and what in the catalogue would have prevented it?
- Which team was cheapest per correct answer, and what did their search return that others' did not?
- Did any design overfit the practice questions?

**A shorter version (75 minutes)** drops the swap and uses three held-back questions.

---

## 8. What the course owner prepares

On the secure system, before the course:

1. **Export the raw catalogue** (section 11.2's format): names, columns, types, row counts, and existing descriptions.
2. **Choose about 12 datasets** the questions depend on. The other 188 are distractors and need no preparation.
3. **Write the eight questions** and verify each answer by hand. Record the trap for each misleading one.
4. **Create a read-only database role** for the exercise, with a statement timeout.
5. **Mark any dataset that must never be queried** (section 9).
6. **Run the baseline and one reference design** end to end, so the session's timings are known.

Budget about a day. Step 3 is most of it.

---

## 9. Data handling

Students see real organizational data, and tool results go to the model gateway. These limits are enforced by the engine and cannot be changed from a team's folder.

| Limit | Default | Why |
|---|---|---|
| Queries are read-only | Always | Enforced by the database role. The engine also allows one statement per call, but that is a convenience, not the protection |
| Rows returned by `run_query` | At most 50 | A query that returns raw rows instead of an aggregate is capped and says so in its result |
| `sample_rows` | Off | An instructor turns it on per course, with a row cap. Off suits data that should not reach the gateway |
| Blocked datasets | None | Listed datasets stay in the catalogue as distractors; any query touching one is refused |
| Statement timeout | 30 seconds | A runaway query costs one tool call, not the session |
| Tool result size | 8,000 characters | Larger results are cut, with a note saying how much was removed |

Session logs contain query results. They stay on the machine that ran them and follow the Prompt Lab's retention setting. Only scores and counts go to the leaderboard.

---

## 10. The synthetic catalogue

The kit must work with no access to real data: for building and testing it, and for trying the exercise elsewhere.

A generator writes about 200 small tables to one SQLite file, from a fixed seed, with:

- realistic, inconsistent names across several invented business areas;
- thin descriptions, some missing, some out of date;
- the planted traps of section 4: an archived predecessor, a raw table and a deduplicated one, two "customers" tables from different systems, a rollup that disagrees with its source;
- eight questions with known answers, in the section 4 mix.

The mock model plays two scripted agents against it: one that lists everything and hits the limit, and one that searches, inspects and answers. As in the Prompt Lab, mock results prove the pipeline and nothing else.

---

## 11. Architecture

### 11.1 Where it lives

Inside the Prompt Lab, not a separate project. It needs the lab's backends, harness sessions, limits, per-request accounting and storage, all of which exist.

```text
prompt-lab/
├── promptlab/discovery/
│   ├── catalog.py        load the raw catalogue; merge a team's notes
│   ├── tools.py          the four tools, their settings, and the hard limits
│   ├── search.py         catalogue search
│   ├── questions.py      questions, expected answers, acceptable datasets, traps
│   ├── session.py        one agent session through mini-harness with these tools
│   ├── score.py          section 6
│   └── synthetic.py      section 10's generator
├── discovery/
│   ├── catalog.yaml      the raw catalogue (the synthetic one is committed)
│   ├── questions/        practice.yaml is committed; heldback.yaml is not
│   ├── baseline/         the naive design used in the opening demonstration
│   ├── reference/        one good design, for instructors
│   └── teams/            one folder per team (section 3.3)
└── tests/test_discovery.py
```

The harness adapter needs one change: a session may be given its tool set, where today it adds `run_sql` to the standard tools.

### 11.2 Raw catalogue format

```yaml
datasets:
  - name: orders_2026
    description: ""              # may be empty; teams add notes separately
    rows: 1840221
    columns:
      - {name: order_id, type: bigint}
      - {name: placed_at, type: timestamp}
    blocked: false               # section 9
```

### 11.3 Data access

- **SQLAlchemy** over one read-only connection, so Postgres works by URL and the synthetic catalogue works on SQLite. The URL comes from an environment variable, never the repository.
- **Dialect.** Questions and the reference design are written for the real database's dialect. The agent is told which dialect it is using.

### 11.4 Search

- **Default: keyword search** over names, columns, descriptions and the team's notes, with a simple ranking. Standard library only, so every team has the same baseline.
- **Optional: embedding search with pgvector,** if the gateway serves an embedding model. It would make a good extension, comparing keyword and semantic search on the same questions, but it is not needed for the exercise and is not in the first build.

### 11.5 Commands

```text
prompt-lab discovery run --team T --questions practice     run a team's design on a question set
prompt-lab discovery score --team T                        section 6, with the trap named for each miss
prompt-lab discovery log --team T --question Q             read one session: every tool call and result size
prompt-lab discovery baseline                              the opening demonstration
prompt-lab discovery synth                                 regenerate the synthetic catalogue
```

### 11.6 Leaderboard

The Prompt Lab app gains one page: teams submit their score file, and the page ranks them as section 6.2 describes. It reuses the class kit's collector.

---

## 12. What we expect to see

Written before any team has tried it, in the Prompt Lab's manner. The first real session should be compared against these.

| # | Expectation | What would contradict it |
|---|---|---|
| E1 | The naive baseline hits the token limit on most questions | It answers within budget |
| E2 | Teams' scores track the quality of their notes more than their tool settings | Settings alone separate the top teams |
| E3 | On misleading questions, most wrong answers are confident and well explained | Wrong answers usually come with stated doubt |
| E4 | Most teams answer the unanswerable question with a number at first | Most refuse it without being designed to |
| E5 | The cheapest design per correct answer returns fewer, richer search results, not more | Returning more results is cheaper overall |

---

## 13. If the data is not tabular

If the "datasets" are document collections, the exercise still works but two parts change:

- `run_query` becomes a retrieval tool over one collection, and `describe_dataset` describes a collection's contents and coverage.
- Answers cannot be checked against exact values. They are graded by the Prompt Lab's judge against a rubric, with quoted evidence, and labelled AI-judged. Instructor hand-scoring of a sample becomes necessary.

That is a larger build, and the scoring is weaker. If the estate is mixed, use the tabular datasets for this exercise.

---

## 14. Open questions for the course owner

The first three change the design.

1. **Form of the data (changes the design):** tabular and SQL-queryable, documents, or mixed? Which database engine?
2. **Existing catalogue (changes the design):** is there one with descriptions, or only names and columns? A good existing catalogue shrinks the notes work, and the weight should move to the misleading and two-dataset questions.
3. **Sensitivity (changes the design):** may aggregate results reach the gateway? May sample rows? Are any datasets off limits entirely?
4. **Model:** which gateway model runs the agent? One capable model for every team is assumed. A weak model mostly teaches that the model is weak.
5. **Time and team size:** two hours and teams of 2 to 4 are assumed.
6. **Embeddings:** does the gateway serve an embedding model, for the optional pgvector extension?
7. **Who writes the questions:** section 8 assumes an instructor who knows the data.

---

## 15. Build phases

Each phase ends with a pull request and a stop for review.

| Phase | Deliverable | Done when |
|---|---|---|
| D1 | The synthetic catalogue and its eight questions; the four tools with settings and hard limits; keyword search; a session through `mini-harness` with these tools | On the mock model, the naive design hits the limit and the reference design answers; every hard limit in section 9 has a test |
| D2 | Scoring, the team folder with `tools.yaml`, `notes.yaml` and optional `tools.py`, the commands, the session log reader, the baseline and reference designs | A team folder can be run, scored and inspected end to end on the synthetic catalogue; a right value from the wrong dataset scores zero |
| D3 | The leaderboard page, an instructor guide with the section 7 run sheet and section 8 checklist, and the adapter notes for a real Postgres catalogue | A full mock session runs from baseline to leaderboard; the guide has been followed from a clean checkout |
| Real data | Done by the course owner on the secure system: export the catalogue, write and verify the questions, run the baseline and reference | The session's timings are known and the held-back answers are verified |

Nothing in D1 to D3 needs the real data. As with the Prompt Lab, it is built and tested against the mock model and the synthetic catalogue.
