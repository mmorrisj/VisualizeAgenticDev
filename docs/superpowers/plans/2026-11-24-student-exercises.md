# Student Exercises Implementation Plan

> **For agentic workers:** Work through this plan task by task, in order. If you have the superpowers skills, use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 1 and 7 end with a **stop**: report to the course owner and wait for their answer before continuing.

**Goal:** Turn the reference data challenge into something a class can do: three labs and one optional lab, a kit each student works in, graders that say whether a lab is done, an instructor's guide, and a written course module.

**Architecture:** The reference system already has the two places a student's work plugs in, once this plan makes them explicit: the list of tools a data server offers, and the set of checks the verifier runs. Each lab gives the student a deliberately weak starting file for one of those, a grader made of tests, and a command that measures their version against recorded reference runs. The verifier lab runs entirely on the synthetic trap tables in SQLite with no model and no network. The discovery lab and the measured half of the tool lab run on the real data. The written module uses only the synthetic tables, so it can be published; everything specific to the real data stays in a local supplement on this system.

**Tech Stack:** Python 3.11 or later; SQLAlchemy 2.0; standard library; `pytest`; POSIX shell for one setup script. Nothing new to install.

**Spec:** There is no separate spec. The next section is the spec. This plan follows the three plans dated 2026-11-23 in this directory (catalogue, MCP servers and orchestrator, verifier) and uses what they built.

---

## Background and decisions

**Why this exists.** The course owner teaches a course on agentic development, "What Is a Harness?", with seven modules and a small practice application. This is its advanced challenge, for data scientists. The owner's reasoning: most courses have to fake the data; this one has real data, so the data is the centrepiece. The owner's pick of exercises was dataset discovery and the confidently wrong analysis, with building the MCP server as the exercise that supports both. The three earlier plans built and measured the instructor's reference implementation. This plan builds what students touch.

**This plan was drafted before any of the earlier plans had been run.** Its author had no access to the system, the data or any results. Which questions make good lab material, how long anything takes and what it costs are unknown. Task 1 finds out and stops for the owner. Where this plan and the measured results disagree, the results win; say so in your report.

**The existing course's conventions,** which this module follows:
- Each module is one `README.md`: prerequisites, numbered learning objectives, numbered sections, labs with exact commands and expected output, "Check your understanding" with answers in block quotes, and a one-sentence key takeaway.
- An exercise is a file with gaps and a reference solution beside it, both shipped (Module 1: `exercise/loop.py`, `solutions/loop_solution.py`).
- Instructor material lives in a file named `INSTRUCTOR-NOTES.md` and is never shown prominently to students.
- No points, levels or leaderboards. Checks are self-checks.
- Every number a student sees comes from running the course's own code, or is labelled illustrative.
- No emoji, and never the word "beginner".
- Tokens are a shared resource on a closed network. Labs state what they cost.

**Decided by the course owner:**

- The labs: dataset discovery; the confidently wrong analysis; building the MCP tools as support for both.
- Earlier ideas kept as supporting material: writing questions with hand-checked answers before running an agent, and orchestrating under a token budget.

**Decided by the plan's author (the owner can overrule any of these):**

- **Three labs and one optional lab,** preceded by a short warm-up. In the order taught: warm-up (a question with a checked answer), Lab A (find the dataset), Lab B (design the tool), Lab C (the confidently wrong analysis), Lab D, optional (orchestrate under a budget).
- **Students may build with their own coding agent.** The course is about agentic development, so each lab is defined by a grader and a measurement, not by typing. The module tells them to hand the agent the grader and not let it edit the grader.
- **Lab C works with no model, no network and no database server.** It is the lab most likely to be reused elsewhere and the one that must not depend on the gateway being free.
- **Lab A is scored by search, not by model calls.** Showing a model the whole catalogue for every question would cost each student on the order of a million tokens. Keyword search over the student's own descriptions is free, instant and repeatable.
- **Lab A uses two sets of questions:** one students tune against, one the instructor reveals at the end. Without the second, students learn to write descriptions that fit the questions.
- **The written module contains nothing from the real data.** Not a table name, not a number. A command checks this.
- **Reference solutions are shipped in the kit,** in their own folder, as Module 1 does.
- **No page on the course website in this plan.** That needs its own entry in the site's build spec.

## Global Constraints

Everything in the three earlier plans' Global Constraints still applies. In addition:

- **Nothing from the real data goes into a file meant for publication.** The module `README.md`, the exercise files, the graders and the solutions use only the trap tables. Real dataset names, questions, results and timings live under `class/` and stay on this system.
- **Students get the read-only database role and nothing more.** The kit never asks for, stores or prints a database URL or key; it reads the same environment variables as before.
- **A student's work is never overwritten.** Setup refuses to write into a folder that already has a kit in it.
- **Every command that needs the gateway says so before it starts,** names the missing variable if there is one, and points to the recorded results the student can use instead.
- **Every live step is sized.** A lab's instructions name the questions to run with `--only`. No lab tells a student to run the full question set.
- **Graders are not to be edited to pass.** The kit's instructions say so, and point to Module 2's `no_test_weakening` hook for students using a harness that supports hooks.
- **No scores, ranks or comparisons between students.** A student's results are shown beside the reference runs only.
- **Do not write the lab questions' expected answers.** Questions on real data and their checked answers come from the owner.

## Review Focus

Conditions the tasks' main tests would otherwise miss. Each has a test in the task named.

1. **A student has no gateway access during the session.** Expect: Lab C, every grader and Lab A's scoring all work; commands that need a model stop with a message naming the variable and the recorded results to use (Tasks 3, 4 and 5).
2. **A student's tools file fails to import, defines no tools, or repeats a tool name.** Expect: the data server exits at once with a message naming the file and the problem, not a hang or a traceback from the client (Task 2).
3. **A student's check raises an exception.** Expect: the grader shows which trap case it happened on and the message; the other cases still run (Task 3).
4. **A student's notes file is not valid TOML or names a dataset that does not exist.** Expect: a message with the line or the id, and no output file written (Task 2).
5. **Setup is run twice into the same folder.** Expect: it refuses and changes nothing (Task 3).
6. **A real table name slips into the module text.** Expect: the publication check fails and names it (Task 6).

## File structure

```
dataset-challenge/
  datacat/
    cli.py                    modified: renote
  datachallenge/
    data_tools.py             new: the reference tools, moved out of data_server.py
    data_server.py            modified: --tools-module
    checks.py                 new: CHECKS, the reference checks by name
    verify.py                 modified: explicit registry, load_checks
    orchestrator.py           modified: tools_module, checks_module
    classkit.py               new: show-case, sql, verify-traps, compare, strip-notes, check-publishable
    cli.py                    modified: the `class` commands; --checks-module on verify-runs
  exercise/
    __init__.py
    checks.py                 Lab C starting file
    tools.py                  Lab B starting file
    tools_naive.py            a copy of the starting tools, kept for comparison
    notes.toml                Lab A starting file (written by setup)
    tests/
      test_lab_b.py  test_lab_c.py
  solutions/
    __init__.py
    checks.py  tools.py
  configs/
    lab-b-mine.toml  lab-b-naive.toml  lab-c-mine.toml  budget-50k.toml  budget-100k.toml
  class/
    setup.sh                  make a student's working copy
    INSTRUCTOR-NOTES.md
    LOCAL.md                  real-data specifics for this system; not for publication
    recorded/traps/runs.jsonl recorded analyst results for the trap cases; generated, no model
    prebaked/                 reference results on real data, copied from the earlier plans' runs
    questions-warmup.json  questions-lab-a-dev.json  questions-lab-a-heldout.json
    questions-lab-b.json
    lab-a-datasets.txt        the datasets whose descriptions Lab A removes
    catalogue-lab-a.jsonl     the catalogue with those descriptions removed
    publishable-allow.txt     words the publication check may ignore, each approved by the owner
  tests/
    test_seams.py  test_classkit.py  test_solutions.py  test_setup.py
course/modules/08-agents-on-real-data/
  README.md                   the written module; synthetic data only
```

If the VisualizeAgenticDev repository is on this system, the module goes at `course/modules/08-agents-on-real-data/README.md` in it and `course/README.md` gets a new row. If it is not, write the module to `dataset-challenge/module/README.md` and tell the owner it needs carrying across.

---

### Task 1: Check the ground, then stop

**Files:**
- Create: `dataset-challenge/class/lab-readiness.md`

- [ ] **Step 1: Run all three earlier test suites.** Expected: pass. If not, stop and report.

- [ ] **Step 2: Read the three reports** (the recommendation test's `report.md`, the orchestrator run's `report.md`, and `verification.md`). In `lab-readiness.md`, answer for each lab whether the real data gives it something to show:
  - **Lab A:** which datasets have look-alikes that the recommendation test or `search-eval` confused, and whether descriptions made a measurable difference between the `schema` and `full` views. If names alone were enough, say so: the lab needs harder questions.
  - **Lab B:** which questions the naive configuration failed or overspent on, and by how much.
  - **Lab C:** how many confidently wrong answers there were on real data, what caused them, and whether the reference checks caught them. If there were none, the lab runs on the trap tables alone; say so.
  - **Lab D:** what orchestration cost and bought against the single agent.

- [ ] **Step 3: Measure what a student will wait for.** Time, on this system: the trap grader; one orchestrated question; `search-eval`; `verify-runs` on ten recorded results. Record tokens for one orchestrated question under `guarded` and one under `naive` with a 50,000 budget.

- [ ] **Step 4: Stop and report to the owner.** Send `lab-readiness.md` and ask, in one message:
  1. how long the session is, how many students, and whether they work alone or in pairs;
  2. whether each student will have the read-only database role and gateway access, and the token allowance per student;
  3. whether students build with their own coding agent, by hand, or either;
  4. to write the Lab A questions with their expected datasets: about eight to tune against and about eight held back, favouring look-alike and blend questions. Suggest candidates from step 2; leave `expected` and `confirmed_by` to them;
  5. to choose, from your shortlist, three questions for Lab B and one or two for the warm-up;
  6. which labs to build, if step 2 shows one has nothing to show on this data.

Do not start Task 2 until they answer.

---

### Task 2: The two places a student's work plugs in

**Files:**
- Create: `datachallenge/data_tools.py`, `datachallenge/checks.py`
- Modify: `datachallenge/data_server.py`, `datachallenge/verify.py`, `datachallenge/orchestrator.py`, `datachallenge/cli.py`, `datacat/cli.py`
- Test: `tests/test_seams.py`

**Interfaces:**
- Produces:

```python
# data_tools.py
@dataclass
class ToolContext:
    entries: dict[str, Entry]                    # the datasets in scope, by id
    max_rows: int                                # the configured cap
    run: Callable[[str, int], QueryResult]       # (sql, max_rows): scope-checked, read-only; raises SqlRejected
    describe: Callable[[str], str]               # dataset id -> its full catalogue text; raises ToolError if unknown

def build_tools(ctx: ToolContext) -> list[Tool]  # the three reference tools, unchanged in behaviour

# checks.py
CHECKS: dict[str, Callable[[VerifyContext], list[Finding]]]   # the six reference checks, by name

# verify.py, changed
def load_checks(module: str) -> dict[str, Callable]
def verify(ctx: VerifyContext, checks: list[str],
           registry: dict[str, Callable] | None = None) -> list[Finding]

# orchestrator.py, changed
@dataclass
class RunConfig:
    ...                                          # existing fields unchanged
    tools_module: str = "datachallenge.data_tools"
    checks_module: str = "datachallenge.checks"
```

- The data server gains `--tools-module NAME`. It imports the module, calls `build_tools`, and exits with status 2 and one line on stderr naming the module and the problem when: the import fails; there is no `build_tools`; it returns no tools; two tools share a name; a tool has no description. The scope check, the read-only connection and the statement timeout stay below `ToolContext.run`, where a tools file cannot reach them.
- `run_analyst` passes `cfg.tools_module` to the server it starts, and runs it with the kit folder as working directory so that `exercise.tools` can be imported.
- `load_checks` imports the module and returns its `CHECKS`; a module without a `CHECKS` dict raises `ValueError` naming it. `verify` with `registry=None` uses `datachallenge.checks.CHECKS`. The module-level `register` function from the verifier plan is removed; the one test that used it passes `registry=` instead. `verify_analyst` and `replay` use `load_checks(cfg.checks_module)`, and `verify-runs` gains `--checks-module`.
- `python -m datacat renote --catalogue IN --notes NOTES --out OUT` applies a notes file to an existing catalogue without connecting to any database. Invalid TOML, or a note for an id not in the catalogue, exits with status 2, a message giving the line or the id, and writes nothing.

- [ ] **Step 1: Write the failing tests**

```python
def test_reference_tools_behave_as_before(data_server): ...        # the existing data server tests pass with --tools-module datachallenge.data_tools
def test_custom_tools_module_is_used(tmp_path, shop):
    # a module whose build_tools returns one tool "hello" returning "hi"
    with McpClient(server(tools_module="mytools")) as c:
        assert [t["name"] for t in c.list_tools()] == ["hello"]

@pytest.mark.parametrize("problem", ["import error", "no build_tools", "no tools", "duplicate name", "no description"])
def test_bad_tools_module_stops_the_server_with_a_message(tmp_path, shop, problem):
    proc = start(server(tools_module=broken(problem)))
    assert proc.wait(timeout=10) == 2 and "mytools" in proc.stderr.read()

def test_tools_cannot_bypass_the_scope(tmp_path, shop): ...        # a tool calling ctx.run on an out-of-scope table gets SqlRejected

def test_load_checks(tmp_path):
    assert set(load_checks("datachallenge.checks")) == set(CHECK_ORDER)
    with pytest.raises(ValueError, match="nochecks"):
        load_checks("nochecks")
def test_verify_with_a_custom_registry(traps): ...                 # registry={"reproduce": ..., "mine": lambda ctx: [finding]}
def test_config_selects_the_modules(tmp_path): ...                 # a config with both keys loads; one without gets the defaults

def test_renote_applies_notes_without_a_database(tmp_path, monkeypatch):
    monkeypatch.setattr("datacat.db.connect", fail_if_called)
    assert main(["renote", "--catalogue", cat, "--notes", notes, "--out", out]) == 0
    assert read_catalogue(out)[0].description_source == "human"
def test_renote_rejects_bad_toml_and_unknown_ids(tmp_path, capsys): ...   # exit 2, message, no output file
```

- [ ] **Step 2: Run** `pytest tests/test_seams.py -v`. Expected: fails on import.
- [ ] **Step 3: Make the changes.** Move the three reference tools into `data_tools.py` without changing what they return.
- [ ] **Step 4: Run every suite.** Expected: all earlier tests pass with no changes other than the one `register` test.
- [ ] **Step 5: Commit** with message `Make tools and checks pluggable for the labs`.

---

### Task 3: The kit, and Lab C on the trap tables

**Files:**
- Create: `datachallenge/classkit.py`, `exercise/__init__.py`, `exercise/checks.py`, `exercise/tests/test_lab_c.py`, `solutions/__init__.py`, `solutions/checks.py`, `configs/lab-c-mine.toml`, `class/setup.sh`, `class/recorded/traps/runs.jsonl`
- Modify: `datachallenge/cli.py`
- Test: `tests/test_classkit.py`, `tests/test_solutions.py`, `tests/test_setup.py`

**Interfaces:**
- Consumes: `trap_cases`, `build_traps`; `verify`, `verdict`, `load_checks`, `VerifyContext`; `shadow`, `dedup_body`, `one_per_key_body`, `rerun_value`, `run_checked`, `entry_for`, `mentions`, `tables_read`.
- Produces:

```python
# classkit.py
def trap_paths(kit_dir: str) -> Paths                      # the trap database's catalogue and sources file
def show_case(case_id: str, reveal: bool = False) -> str
def verify_traps(checks_module: str, kit_dir: str) -> tuple[str, bool]   # the table as text, and whether every case matched
```

**Setup.** `class/setup.sh TARGET` copies `datacat/`, `datachallenge/`, `exercise/`, `solutions/`, `configs/`, `traps/` and `class/recorded/` into `TARGET`; builds `TARGET/traps.db` (SQLite) with `build_traps`; writes `TARGET/sources.traps.toml` and `TARGET/env.sh`, which exports `DATACAT_DB_TRAPS` as the SQLite URL of that file; builds `TARGET/catalogue-traps.jsonl` with `datacat build`; and prints the three commands to run next. It does not copy `class/questions-lab-a-heldout.json`, `class/INSTRUCTOR-NOTES.md` or `class/prebaked/`. If `TARGET/exercise` exists it prints "A kit already exists in TARGET. Nothing was changed." and exits with status 1.

**The recorded results.** `class/recorded/traps/runs.jsonl` is written by a function in `classkit.py` from `trap_cases`: one line per case in the orchestrator plan's format, with one finished analyst whose `final` has the case's SQL and reported value, an `answer` sentence stating the number plainly, and empty `caveats`. No model is involved. A test regenerates it and compares.

**The starting file.** `exercise/checks.py` contains:
- `check_reproduce`, complete, copied from the reference with comments, as the worked example;
- `check_duplicates` and `check_fanout`, each with a docstring stating what it must return for which trap cases and naming the helpers that will be useful, and a body of `raise NotImplementedError`;
- `CHECKS = {"reproduce": check_reproduce, "duplicates": check_duplicates, "fanout": check_fanout}`.

`solutions/checks.py` re-exports the reference `CHECKS`.

**The grader.** `exercise/tests/test_lab_c.py` takes the module from the environment variable `LAB_C_MODULE`, default `exercise.checks`, and builds its own trap database in `tmp_path`. Its tests are grouped so a student can run one stage at a time with `-k`:

| Stage | Passes when |
|---|---|
| `stage1` | `fabricated` fails on `reproduce`; `clean` passes. Passes on the untouched starting file. |
| `stage2` | `dup-wrong` fails on `duplicates`, and the message contains both 2000 and 2100; `dup-right` passes. |
| `stage3` | `fanout-wrong` fails on `fanout`, and the message contains both 5000 and 6000; `fanout-right`, `join-fine` and `count-many` pass. |
| `final` | every trap case gets its expected verdict, apart from `unit-wrong` and `missing`, which the three student checks are not expected to flag and which must come out `passed`. |

When a check raises, the test's failure message gives the case id and the exception.

**Student commands,** all under `python -m datachallenge class`:
- `show-case ID` prints the question and the recorded analyst's report as a student of the system would see it: the answer sentence, the number, the SQL, "Caveats: none". `--reveal` adds the right value. `show-case --list` lists the case ids without saying which are wrong.
- `sql "SELECT ..."` runs one statement against the trap database through `sqlguard.run_query` and prints the formatted result. `--database NAME` runs it against a real database from `sources.toml` instead, with every catalogued dataset of that database in scope.
- `verify-traps [--checks-module exercise.checks]` runs the module's checks over every trap case and prints, per case, the expected verdict, the verdict given, and each finding's message. Exit status 0 only when every case matches.

`configs/lab-c-mine.toml` is `verified.toml` with `checks_module = "exercise.checks"` and `checks = ["reproduce", "duplicates", "fanout"]`.

- [ ] **Step 1: Write the failing tests**

```python
# test_setup.py
def test_setup_builds_a_working_kit(tmp_path):
    run(["sh", "class/setup.sh", str(tmp_path / "kit")])
    kit = tmp_path / "kit"
    assert (kit / "traps.db").exists() and (kit / "exercise" / "checks.py").exists()
    assert not (kit / "class" / "prebaked").exists()
    assert not list(kit.rglob("*heldout*")) and not list(kit.rglob("INSTRUCTOR-NOTES.md"))
def test_setup_refuses_to_overwrite(tmp_path):
    run_setup(kit); (kit / "exercise" / "checks.py").write_text("# my work")
    assert run_setup(kit).returncode == 1
    assert (kit / "exercise" / "checks.py").read_text() == "# my work"
def test_kit_runs_with_no_gateway_and_no_network(tmp_path): ...    # env without DATACAT_GATEWAY_*: stage1 of the grader passes in the kit

# test_solutions.py
def test_starting_file_passes_stage1_only(kit):
    assert grade(kit, "exercise.checks", "stage1").returncode == 0
    assert grade(kit, "exercise.checks", "stage2").returncode != 0
def test_solutions_pass_every_stage(kit):
    for stage in ("stage1", "stage2", "stage3", "final"):
        assert grade(kit, "solutions.checks", stage).returncode == 0
def test_a_raising_check_is_reported_with_its_case(kit): ...       # the starting file's stage2 output contains "dup-wrong" and "NotImplementedError"

# test_classkit.py
def test_recorded_trap_results_match_the_cases(tmp_path): ...      # regenerated file equals the committed one
def test_show_case_hides_the_right_answer_until_asked():
    assert "6000" in show_case("fanout-wrong") and "5000" not in show_case("fanout-wrong")
    assert "5000" in show_case("fanout-wrong", reveal=True)
def test_show_case_list_does_not_give_the_game_away(): ...         # no "wrong" or "right" in the listing; ids are shown as case-01 ... case-10
def test_sql_command_is_read_only_and_capped(kit, capsys): ...     # a DELETE is rejected; SELECT * FROM revenue shows the truncation notice
def test_verify_traps_reports_each_case(kit):
    text, ok = verify_traps("solutions.checks", str(kit))
    assert ok and "fanout-wrong" in text
    text, ok = verify_traps("exercise.checks", str(kit))
    assert not ok
```

`show-case --list` shows neutral ids (`case-01` to `case-10`, in a fixed shuffled order defined in `classkit.py`); `show-case` and the grader accept either form.

- [ ] **Step 2: Run** `pytest tests/test_setup.py tests/test_solutions.py tests/test_classkit.py -v`. Expected: fails.
- [ ] **Step 3: Implement** the kit, the starting file, the grader, the commands and the setup script.
- [ ] **Step 4: Run every suite.** Expected: pass.
- [ ] **Step 5: Do Lab C yourself as a student would,** in a fresh kit, starting from the untouched file and without opening `solutions/` or `datachallenge/checks_rows.py`: read three cases with `show-case`, find by hand with `sql` which numbers are wrong and why, then write the two checks until `final` passes. Record how long each stage took and where the instructions were not enough; fix the docstrings accordingly.
- [ ] **Step 6: Commit** with message `Add the student kit and Lab C on the trap tables`.

---

### Task 4: Lab B, design the tool

**Files:**
- Create: `exercise/tools.py`, `exercise/tools_naive.py`, `exercise/tests/test_lab_b.py`, `solutions/tools.py`, `configs/lab-b-mine.toml`, `configs/lab-b-naive.toml`, `configs/budget-50k.toml`, `configs/budget-100k.toml`
- Modify: `datachallenge/classkit.py`, `datachallenge/cli.py`
- Test: additions to `tests/test_classkit.py`, `tests/test_solutions.py`

**Interfaces:**
- Consumes: `ToolContext`, `Tool`, `format_result`; `Outcome` transcripts as written by the `run` command.
- Produces:

```python
def summarize(results_dir: str) -> list[dict]
def format_compare(mine: list[dict], reference: list[dict]) -> str
```

`summarize` returns one row per configuration: questions run; answers right (of those with a checked answer); runs stopped by budget, turns or error; mean tokens per question; and the largest single tool result in characters, taken from the transcripts. `class compare RESULTS --against REFERENCE` prints the student's rows above the reference's rows, with the configuration names, and nothing that ranks or scores.

**The starting file.** `exercise/tools.py` and its copy `exercise/tools_naive.py` define one tool:

```python
def build_tools(ctx):
    def run_sql(args):
        result = ctx.run(args["sql"], 100_000)
        return "\n".join(" | ".join(str(v) for v in row) for row in result.rows)
    return [Tool("run_sql", "Run SQL.", {"type": "object", "properties": {"sql": {"type": "string"}},
                                          "required": ["sql"]}, run_sql)]
```

It has no row cap, no column names, no notice and a description that tells the model nothing. `solutions/tools.py` re-exports the reference `build_tools`.

**The grader.** `exercise/tests/test_lab_b.py` takes the module from `LAB_B_MODULE`, default `exercise.tools`, and starts the real data server on a trap database it builds, with every trap table in scope and `--max-rows 50`:

| Test | Passes when |
|---|---|
| `test_run_sql_still_exists` | a tool named `run_sql` taking `sql` is offered |
| `test_large_result_is_bounded` | `SELECT * FROM revenue` (480 rows) returns at most 60 lines |
| `test_truncation_is_announced` | that result contains the word "truncated" |
| `test_small_result_is_complete` | `SELECT count(*) FROM revenue` contains 480 and not "truncated" |
| `test_columns_are_named` | `SELECT day, amount FROM revenue LIMIT 1` contains "day" and "amount" |
| `test_every_tool_is_described` | each description is at least 40 characters and each schema is an object |
| `test_tool_definitions_fit_a_budget` | the JSON of `tools/list` is at most 3,200 characters, about 800 tokens |
| `test_scope_still_holds` | a query on a table left out of scope is an error result naming it |

A student is free to add tools (a row sample, a column summary, a description of a dataset). The budget test is what makes adding them a trade-off.

**Configurations.** `lab-b-mine.toml` is `guarded.toml` with `tools_module = "exercise.tools"`. `lab-b-naive.toml` is `naive.toml` with `tools_module = "exercise.tools_naive"` and `token_budget = 50000`, so the failure is quick and cheap. `budget-50k.toml` and `budget-100k.toml` are `guarded.toml` with those budgets, for Lab D.

**Reference results.** Copy the earlier plans' results directories for `guarded`, `naive`, `single` and `verified` into `class/prebaked/`, restricted to the Lab B questions for a second, smaller set `class/prebaked/lab-b/`. If the earlier `naive` run did not cover the three Lab B questions the owner chose, run those three now.

- [ ] **Step 1: Write the failing tests**

```python
def test_starting_tools_fail_the_grader_in_the_expected_places(kit):
    out = grade_b(kit, "exercise.tools")
    for name in ("test_large_result_is_bounded", "test_truncation_is_announced",
                 "test_columns_are_named", "test_every_tool_is_described"):
        assert f"{name} FAILED" in out
    assert "test_scope_still_holds PASSED" in out and "test_run_sql_still_exists PASSED" in out
def test_solution_tools_pass_the_grader(kit):
    assert grade_b(kit, "solutions.tools", returncode=True) == 0

def test_summarize_reads_a_results_directory(results_dir):
    [row] = summarize(str(results_dir))
    assert row["config"] == "guarded" and row["questions"] == 3
    assert row["largest_tool_result_chars"] == 1840        # fixture transcript's largest tool message
def test_compare_shows_mine_above_reference_without_ranking(results_dir, reference_dir):
    text = format_compare(summarize(mine), summarize(ref))
    assert text.index("lab-b-mine") < text.index("guarded")
    assert not re.search(r"(?i)rank|score|better|worse|winner", text)
def test_run_without_gateway_names_the_variable_and_the_recorded_results(kit, capsys):
    assert main(["run", "--config", "configs/lab-b-mine.toml", ...]) == 2
    out = capsys.readouterr().err
    assert "DATACAT_GATEWAY_URL" in out and "class compare" in out
```

- [ ] **Step 2: Run** the new tests. Expected: fail.
- [ ] **Step 3: Implement** the starting files, the grader, the configurations, `summarize`, `format_compare`, the `compare` command, and the gateway check at the start of `run` and `ask`.
- [ ] **Step 4: Run every suite.** Expected: pass.
- [ ] **Step 5: Do Lab B yourself** in a fresh kit: run one Lab B question with `lab-b-naive.toml` and read what happened to the context; rewrite `exercise/tools.py` until the grader passes, without opening `solutions/`; run the three questions with `lab-b-mine.toml`; run `class compare`. Record time, tokens, and whether the naive run failed in a way a student will recognise.
- [ ] **Step 6: Commit** with message `Add Lab B: design the data tool`.

---

### Task 5: Lab A, find the dataset

**Files:**
- Create: `class/lab-a-datasets.txt`, `class/catalogue-lab-a.jsonl`
- Modify: `datachallenge/classkit.py`, `datachallenge/cli.py`, `class/setup.sh`
- Test: additions to `tests/test_classkit.py`, `tests/test_setup.py`

**Interfaces:**
- Produces:

```python
def strip_notes(entries: list[Entry], ids: set[str]) -> list[Entry]
def notes_template(entries: list[Entry], ids: list[str]) -> str     # TOML text
```

`strip_notes` returns the catalogue with, for each listed dataset, `description`, `grain`, `caveats`, `units`, the table comment and every column comment emptied and `description_source` set to `"none"`. Other entries are untouched. An id not in the catalogue raises `ValueError` naming it. `class strip-notes --catalogue ... --datasets class/lab-a-datasets.txt --out class/catalogue-lab-a.jsonl` writes the result.

**What the lab is.** `class/lab-a-datasets.txt` lists about twelve datasets: the expected datasets of the Lab A questions and the look-alikes they are confused with, chosen from Task 1's findings. Students receive the catalogue with those descriptions removed, the questions to tune against, and `exercise/notes.toml`, a template with one empty table per listed dataset and `reviewed = true`. They look at the data with `class sql --database NAME`, write what one row represents, the units and the caveats, then:

```
python -m datacat renote --catalogue class/catalogue-lab-a.jsonl --notes exercise/notes.toml --out exercise/catalogue.jsonl
python -m datachallenge search-eval --catalogue exercise/catalogue.jsonl --questions class/questions-lab-a-dev.json
```

At the end the instructor hands out `questions-lab-a-heldout.json` and they run `search-eval` once more on it. The two numbers, side by side, are the lesson.

`class/setup.sh` is extended, when a real catalogue is present, to copy `class/catalogue-lab-a.jsonl`, `class/questions-lab-a-dev.json`, `class/questions-warmup.json`, `class/questions-lab-b.json`, `class/prebaked/lab-b/`, `sources.toml` and `class/LOCAL.md` into the kit, and to write `exercise/notes.toml` from `notes_template`. Without a real catalogue it prints that Labs A and the measured half of Lab B are unavailable and builds the rest.

- [ ] **Step 1: Write the failing tests** on the `shop` fixture catalogue with notes on two datasets.

```python
def test_strip_notes_empties_only_the_listed_datasets():
    out = strip_notes(entries, {"shop.main.orders"})
    orders, customers = by_id(out, "shop.main.orders"), by_id(out, "shop.main.customers")
    assert (orders.description, orders.grain, orders.caveats, orders.units, orders.comment) == ("", "", "", {}, "")
    assert all(c.comment == "" for c in orders.columns) and orders.description_source == "none"
    assert customers.description != ""
def test_strip_notes_rejects_unknown_ids(): ...
def test_notes_template_round_trips(tmp_path): ...            # template -> renote succeeds; every listed id present
def test_writing_a_note_raises_recall(tmp_path, capsys):
    # question "Which customers were refunded?" expects shop.main.events; stripped catalogue misses it
    before = recall_at_5(stripped); write_note("shop.main.events", description="refund and return events per customer")
    assert recall_at_5(renoted) > before
def test_setup_copies_lab_a_but_not_the_heldout_questions(tmp_path): ...
def test_setup_without_a_real_catalogue_still_builds_lab_c(tmp_path, capsys): ...
```

- [ ] **Step 2: Run** the new tests. Expected: fail.
- [ ] **Step 3: Implement** `strip_notes`, `notes_template`, the command and the setup changes.
- [ ] **Step 4: Run every suite.** Expected: pass.
- [ ] **Step 5: Build the lab's files** from the owner's questions: `lab-a-datasets.txt`, then `catalogue-lab-a.jsonl`. Run `search-eval` three times on the questions to tune against (stripped catalogue, the catalogue with the owner's reviewed notes, and after step 6) and keep the output.
- [ ] **Step 6: Do Lab A yourself** in a fresh kit: write the twelve notes from the data alone, without reading the owner's notes. Record the time taken and both recall figures. If the stripped catalogue already scores within a few points of the reviewed one, the lab has nothing to teach on these questions: report that in Task 7 with the figures.
- [ ] **Step 7: Commit** code and tests with message `Add Lab A: find the dataset`. Ask before committing anything under `class/`.

---

### Task 6: The written module and the instructor's guide

**Files:**
- Create: `course/modules/08-agents-on-real-data/README.md`, `class/INSTRUCTOR-NOTES.md`, `class/LOCAL.md`, `class/publishable-allow.txt`
- Modify: `course/README.md`, `datachallenge/classkit.py`, `datachallenge/cli.py`
- Test: additions to `tests/test_classkit.py`

**Interfaces:**
- Produces:

```python
def unpublishable_words(text: str, entries: list[Entry], allow: set[str]) -> list[str]
```

It returns, sorted, every real database name and every real table or view name of five or more characters that appears in the text as a whole word in any case, leaving out the trap tables' names and the words in `allow`. `class check-publishable FILE... --catalogue catalogue/datasets.jsonl` prints them per file and exits with status 1 if there are any. A word goes into `class/publishable-allow.txt` only when it is an ordinary word used in its ordinary sense and the owner has agreed.

**The module.** `README.md` follows the existing modules' shape. Every example, number and table name in it comes from the trap tables, produced by running the kit. Title: "Module 8: Agents on Real Data". Prerequisites: Modules 4, 5 and 7. Sections, in order:

| Section | Must contain |
|---|---|
| Learning objectives | Five, numbered: write a question whose answer you have checked before an agent sees it; describe a dataset so that an agent can find it; design a tool that returns enough and no more; explain why a wrong number looks like a right one, and build a check that tells them apart; say what splitting work between agents costs and buys. |
| 1. Why data is different | A failing test announces itself; a wrong total does not. The `fanout-wrong` case in full: question, the analyst's report, 6000, and that nothing about it looks wrong. |
| 2. The system | Who can call what, as a diagram: the orchestrator reaches the catalogue server and analysts; each analyst reaches one data server limited to its datasets; the verifier is code run after each analyst. That the database enforces read-only, with a pointer to Module 5's note on this. |
| 3. Set up | `class/setup.sh`, `source env.sh`, and the one command that proves the kit works. What to do with no gateway access. |
| 4. Warm-up: a question you can check | Write one question about the trap tables and work out its answer by hand with `class sql`, before any agent runs. Why the order matters. |
| 5. Lab A: Find the dataset | The stripped catalogue, writing notes from the data, `renote`, `search-eval`, and the held-back questions. What only a person knows: what one row represents, the units, the caveats. States plainly that this lab needs the real data and that its specifics are in the local notes. |
| 6. Lab B: Design the tool | Run the naive tool and watch one result fill the context. The grader. The trade-off between more tools and the size of their definitions on every request (Module 5). Measure with three questions; compare with the recorded runs. |
| 7. Lab C: The confidently wrong analysis | `show-case`; find what is wrong by hand; the worked `reproduce` check; then the idea that carries the lab: re-run the analyst's own query with the suspect table corrected and see whether the number moves. Stages 2 and 3. Then why `dup-right` and `join-fine` must pass: a verifier that fails everything catches everything. Replay on recorded runs. |
| 8. Lab D (optional): Orchestrate under a budget | Tokens by role from the recorded runs; one question under `budget-50k.toml` and `budget-100k.toml`; what the orchestrator never saw. |
| 9. Working with your coding agent | Give it the grader and the starting file. Do not let it edit the grader; Module 2's `no_test_weakening` hook does this for you. Review its diff as Module 4 teaches. Ask it what it did not check. |
| 10. In a production harness | These servers speak standard MCP over stdio and can be listed in a harness's MCP configuration; production servers normally use the `mcp` package; real scoping belongs in database roles; a row cap is a tool design choice, not a security control. |
| Check your understanding | Five questions with answers in block quotes, one per objective. One must be: a check fails 9 of 10 wrong answers and 4 of 10 right ones; is it a good check? |
| Key takeaway | One sentence. |

Add a row for Module 8 to the course map table in `course/README.md` and an arrow into it from Modules 4, 5 and 7 in the diagram.

**The local notes.** `class/LOCAL.md`, for students on this system: the number of datasets; which databases; the Lab A datasets and where to look; the Lab B question ids and the exact `--only` argument; the token cost of each live step as measured; the recorded results' figures the labs compare against. Every number cites the results directory it came from.

**The instructor's guide.** `class/INSTRUCTOR-NOTES.md`, in the style of `course/practice-app/INSTRUCTOR-NOTES.md`: a timed running order for the session length the owner gave; what to prepare beforehand (role, gateway allowance, `setup.sh` for each student); each trap case with its cause and right answer; for each lab, what students get stuck on (from your own run-throughs) and what to say; when to hand out the held-back questions; expected results for each grader; how to reset a kit; and what to do when the gateway is busy.

- [ ] **Step 1: Write the failing tests**

```python
def test_real_names_are_caught():
    assert unpublishable_words("Join ledger_entries to orders.", entries_with("finance.public.ledger_entries"), set()) == ["ledger_entries"]
def test_trap_names_and_allowed_words_are_ignored(): ...     # "orders", "revenue" pass; an allowed word passes
def test_database_names_are_caught(): ...
def test_short_names_are_ignored(): ...                      # a table called "fx" does not flag "fx"
def test_check_publishable_exit_status(tmp_path): ...        # 1 with a hit, 0 without

def test_module_readme_is_publishable_and_complete():
    text = MODULE_README.read_text()
    for heading in ("Learning objectives", "Lab A", "Lab B", "Lab C", "Check your understanding", "Key takeaway"):
        assert heading in text
    assert "beginner" not in text.lower() and not has_emoji(text)
def test_every_command_in_the_readme_exists(): ...            # each `python -m ...` line in a code block parses with the real argument parsers
```

- [ ] **Step 2: Run** the new tests. Expected: fail.
- [ ] **Step 3: Implement** the check and its command, then write the three documents. Produce every number in the module by running the kit on the trap tables, and paste real output for each "expected output" block.
- [ ] **Step 4: Run `class check-publishable`** on the module, every file under `exercise/` and `solutions/`, and the graders, against the real catalogue. Expected: nothing found. Reword rather than add to the allow list.
- [ ] **Step 5: Run every suite.** Expected: pass.
- [ ] **Step 6: Commit** code, tests and the module with message `Add Module 8: Agents on Real Data`. Ask before committing `class/LOCAL.md` and `class/INSTRUCTOR-NOTES.md`.

---

### Task 7: Rehearse it, then stop

**Files:**
- Modify: `class/INSTRUCTOR-NOTES.md`, `class/LOCAL.md`

- [ ] **Step 1: Run the whole session once as a student,** in a fresh kit from `class/setup.sh`, following only the module and `LOCAL.md`, in the order taught, against the session length the owner gave. Do not open `solutions/` or the reference modules. Use the token allowance one student would have.

- [ ] **Step 2: Record, per lab:** time taken against time planned; tokens spent against the allowance; every place the instructions were wrong, unclear or missing a step; every command whose output differed from the module's "expected output".

- [ ] **Step 3: Run it once with the gateway variables unset.** Confirm the warm-up, Lab A's scoring, both graders and all of Lab C complete, and that each command needing a model stops with a useful message.

- [ ] **Step 4: Fix what steps 1 to 3 found** in the documents and the kit. Re-run the affected tests and `check-publishable`. Commit.

- [ ] **Step 5: Put the measured timings and token costs** into `INSTRUCTOR-NOTES.md` and `LOCAL.md`, replacing any estimate.

- [ ] **Step 6: Stop and report to the owner.** Lead with: whether the session fits the time and the token allowance, and by how much. Then, per lab: what it showed on this data, with the figures; what you would cut if time is short; what a student is most likely to get stuck on. Say plainly if a lab does not work here (for example, Lab A when names alone find the datasets), and what would have to change. List what you did not test: more than one student at once on the gateway, a harness other than your own, and anything skipped for lack of a scratch database.

---

## Out of scope

Do not build these. They come after the owner has run the session once.

- A section on the course website. It needs an entry in the site's build spec and its own measured, synthetic data.
- Scores, ranks or any comparison between students.
- A larger synthetic warehouse so that Lab A can run without the real data.
- Automatic grading of Lab A's descriptions beyond the search measurement.
- A lab in which students add their own trap case and check. The grader and trap table are built so that this could follow.
- Running the labs inside a commercial harness's own subagent and MCP features in place of the kit's orchestrator.
- Tooling for many students sharing the gateway at once (queues, per-student quotas).
