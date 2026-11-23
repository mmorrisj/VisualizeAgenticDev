# Dataset Catalogue and Recommendation Test Implementation Plan

> **For agentic workers:** Work through this plan task by task, in order. If you have the superpowers skills, use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 1 and 5 end with a **stop**: report to the course owner and wait for their answer before continuing.

**Goal:** Build a catalogue of the datasets that actually exist in the PostgreSQL databases on this system, then measure whether a model can pick the right dataset or datasets for a question from that catalogue alone.

**Architecture:** A small Python package, `datacat`, with two halves. The first half connects read-only to each database, profiles every table and view (declared schema, keys and foreign keys, comments, row count, time span, a sample for value statistics, likely joins) into one catalogue file, and merges in descriptions a person has written. The second half shows a model the catalogue at three levels of detail, asks it to pick datasets for each of a set of questions whose correct answers a person wrote down beforehand, and scores the picks.

**Tech Stack:** Python 3.11 or later. SQLAlchemy 2.0 (Core and the inspector, no ORM) with a PostgreSQL driver (`psycopg` version 3, or `psycopg2` if that is what is installed). Standard library for everything else (`json`, `tomllib`, `urllib`, `argparse`, `dataclasses`). `pytest` for tests. Unit tests run against SQLite through the same SQLAlchemy code; PostgreSQL-only behaviour is tested against a scratch PostgreSQL database.

**Spec:** There is no separate spec. The next section is the spec; it records what the course owner decided.

---

## Background and decisions

You are picking this up without the conversation that led to it. This is what you need from it.

**Why this exists.** The course owner is designing an advanced challenge for a course on agentic development, aimed at data scientists. The planned challenge has a student ask a question; an orchestrating agent finds the relevant datasets out of roughly 200, hands each to a subagent that reaches it through an MCP server, and a verifier checks the combined answer. Before building any of that, the owner wants to know two things: what is actually in the datasets, and whether a model can choose well among them. This plan answers both. It deliberately builds no MCP server, no orchestrator and no subagents.

**What the plan's author did not know.** The author had no access to this system. The owner has said the datasets will ultimately be in PostgreSQL databases, and estimates about 200 of them. How many databases and schemas, how large the tables are, what they are about, and whether everything is in PostgreSQL already are unknown. Task 1 finds out, and the answers may change later tasks. Where this plan and what you find disagree, what you find wins; say so in your report.

**Decided by the course owner:**

- Catalogue first, then the recommendation test.
- The datasets are, or will be, in PostgreSQL.
- The test questions must include ones where the model has to choose between datasets and ones where it has to blend two or more.

**Decided by the plan's author (the owner can overrule any of these):**

- One dataset is one table, view or materialized view. Its id is `database.schema.name`.
- The facts in the catalogue come from the database: declared types, keys, foreign keys, comments, counts, date ranges. The meaning (description, what one row represents, units) is written or reviewed by a person.
- Questions and their correct datasets are written by a person **before** any model run, so nobody ends up judging whether a model's pick merely sounds right.
- The catalogue is a plain file and the tool is one command line. No server, no web page, and nothing is written to any database.
- The package stands alone. It does not import the Prompt Lab (`prompt-lab/` in the VisualizeAgenticDev repository), because that repository may not be on this system. If it is, put this work in a new top-level folder `dataset-challenge/` in that repository on its own branch, and pin SQLAlchemy to the version the Prompt Lab pins; otherwise create `dataset-challenge/` wherever the owner says.

## Global Constraints

- **Read-only on the data.** Connect with a role that has only `CONNECT`, `USAGE` and `SELECT`. Every connection sets `default_transaction_read_only=on`. Never run DDL, `INSERT`, `UPDATE`, `DELETE`, `ANALYZE`, `VACUUM` or `CREATE EXTENSION` against a real database. Tests that create tables run only against SQLite or a scratch database the owner has named.
- **Be a polite client.** Every connection sets `statement_timeout` (default 60 seconds). One connection per database, one query at a time. No `COUNT(*)` or `min`/`max` on a large table without the timeout. If the owner names quiet hours, run the build then.
- **Nothing leaves this system.** Do not copy data, catalogue contents, questions or results to any other network, service or repository unless the owner says so. Commit code and tests; ask before committing `catalogue/`, `questions/` or `results/`.
- **No credentials in files.** Database URLs and the gateway key are read from environment variables. `sources.toml` holds the variables' names, never their values. Never print a URL.
- **Model calls go only to the gateway** named by the environment variables in Task 7.
- **Example values may be sensitive.** The catalogue is sent to a model. Whether column example values may be included is the owner's decision (asked in Task 1). Until they answer, build with `--no-examples`.
- **One unreadable table never stops a run.** Permission denied, a timeout, a broken view: record the error on that entry and continue.
- **Do not write the expected answers to the test questions.** You may suggest candidate questions; only the owner fills in `expected` and `confirmed_by`.
- **No emoji in any file, and plain language in every report.**

## Review Focus

Conditions the tasks' main tests would otherwise miss. Each has a test in the task named.

1. **A table too large to read in full.** Expect: the profiler reads a sample of at most `sample_rows` rows, marks the entry `sampled: true`, and reports an estimated row count marked as an estimate (Task 3).
2. **A table or view that cannot be read** (no `SELECT` privilege, a view over a dropped table, a query that times out). Expect: an entry with `error` set; the build finishes and lists it (Tasks 3 and 5).
3. **The model names a dataset that is not in the catalogue.** Expect: the id is dropped from the pick, counted as `unknown_ids`, and shown in the report (Tasks 7 and 8).
4. **The catalogue text is larger than the model's context window.** Expect: the run for that view is skipped with a clear message and the report says so; this is a finding, not a failure (Task 8).
5. **The questions file has not been confirmed by a person.** Expect: `run` refuses to start (Task 7).

## File structure

```
dataset-challenge/
  README.md                  how to run each command; written in Task 8
  pyproject.toml             package metadata, pinned dependencies, pytest config; Task 2
  sources.toml               which databases and schemas; names of environment variables only
  inventory.md               what Task 1 found
  datacat/
    __init__.py
    __main__.py              `python -m datacat` entry point
    cli.py                   argparse: build, views, run
    entry.py                 catalogue entry dataclasses, read and write
    db.py                    sources.toml, read-only connections, table discovery
    profile.py               profile one table or view into an entry
    joins.py                 likely joins between datasets
    notes.py                 person-written descriptions, merged in
    views.py                 three renderings of the catalogue as text
    model.py                 one function that calls the gateway
    questions.py             load and validate the question file
    recommend.py             ask the model, parse and clean the pick
    score.py                 compare a pick with the expected datasets
    report.py                write the Markdown report
  catalogue/
    datasets.jsonl           generated; one entry per line
    notes.toml               written by a person
  questions/
    questions.json           written by a person
  results/<UTC timestamp>/
    runs.jsonl
    report.md
  tests/
    conftest.py              SQLite fixture database; the `postgres` marker
    test_entry.py  test_db.py  test_profile.py  test_joins.py  test_notes.py
    test_views.py  test_recommend.py  test_score.py  test_cli.py
```

**Testing against two databases.** Most tests build a small SQLite database in `tmp_path` and run the real code against it through SQLAlchemy. Tests of PostgreSQL-only behaviour carry `@pytest.mark.postgres` and run only when `DATACAT_TEST_PG_URL` is set; `conftest.py` skips them otherwise and prints how many were skipped. That variable must point at a scratch database you may create tables in, never at real data. If the owner cannot provide one, say so in your report: the PostgreSQL-only paths are then untested until the first real build, so check its first ten entries by hand with extra care.

---

### Task 1: Inventory, then stop

No package code yet. Find out what is here and report it. Use `psql` or a short throwaway script; read-only queries only.

**Files:**
- Create: `dataset-challenge/inventory.md`

- [ ] **Step 1: Ask the owner** which databases to look at, which role to connect as, and whether all the datasets are in PostgreSQL today. If some are still files or in another system, ask when they will be loaded and whether to wait. Do not go looking across the system uninvited.

- [ ] **Step 2: Survey from the system catalogues, without reading table data.** For each database: PostgreSQL version; schemas; number of tables, views and materialized views per schema; estimated rows and size of each table (`pg_class.reltuples`, `pg_total_relation_size`); the ten largest. Record how many tables have never been analysed (`reltuples = -1`).

- [ ] **Step 3: Record what the database already knows about meaning.** How many tables and columns have comments (`obj_description`, `col_description`); how many tables have a primary key; how many foreign keys are declared; any data dictionary, README or portal that describes the tables. This decides how much of the catalogue can be generated and how much a person must write.

- [ ] **Step 4: Check what your role may do.** Confirm it can `SELECT` from the tables in scope and cannot write. List anything it cannot read.

- [ ] **Step 5: Look at five tables by hand,** chosen to differ in size and subject. For each, note what one row appears to represent, how dates and money are typed (a date held in a `text` column matters), and anything odd (duplicate rows, no primary key, mixed units, columns that look like keys to other tables but have no foreign key).

- [ ] **Step 6: Check the tools.** Record the Python version; installed versions of SQLAlchemy, `psycopg` or `psycopg2`, and `pytest`; whether a scratch PostgreSQL database is available for tests; whether the `vector` extension is installed (not used by this plan; the owner will want to know for later); and whether the model gateway is reachable (ask the owner for the variable values in Task 7; make one small test call).

- [ ] **Step 7: Write `inventory.md`** under the headings Databases and schemas, Sizes, Existing documentation and constraints, Access, Five tables looked at, Tools, and Changes this plan needs. Under the last heading, state plainly anything that makes the plan's approach wrong, including datasets that span several tables (for example a table partitioned by year, which should be one dataset, not twenty).

- [ ] **Step 8: Stop and report to the owner.** Ask them to confirm, in one message:
  1. the scope (which databases and schemas; all tables, or a named subset to start with);
  2. whether example values from columns may be shown to the model;
  3. which model to test with;
  4. a scratch database for tests, or that there is none;
  5. any change you proposed in step 7.

Do not start Task 2 until they answer.

---

### Task 2: Catalogue entries

**Files:**
- Create: `dataset-challenge/pyproject.toml`, `datacat/__init__.py`, `datacat/entry.py`
- Test: `tests/test_entry.py`

**Interfaces:**
- Produces:

```python
TYPES = ("integer", "number", "date", "datetime", "boolean", "text")

@dataclass
class Column:
    name: str
    type: str                  # one of TYPES
    db_type: str               # as the database declares it, e.g. "NUMERIC(12, 2)"
    nullable: bool
    comment: str               # the column's comment in the database, or ""
    null_fraction: float       # 0.0 to 1.0, of rows read
    distinct_count: int        # of rows read
    distinct_capped: bool      # True when counting stopped at the cap
    min: str | None            # for integer, number, date, datetime; of rows read
    max: str | None
    examples: list[str]        # empty when examples are switched off

@dataclass
class JoinCandidate:
    column: str
    other_dataset: str
    other_column: str
    source: str                # "declared" (a foreign key) or "inferred" (values overlap)
    overlap: float | None      # None for declared joins

@dataclass
class Entry:
    id: str                    # database.schema.name
    database: str
    schema: str
    name: str
    kind: str                  # "table", "view" or "materialized view"
    comment: str               # the table's comment in the database, or ""
    row_count: int | None
    row_count_exact: bool      # False when row_count is the planner's estimate
    size_bytes: int | None
    sampled: bool
    columns: list[Column]
    primary_key: list[str]     # declared; may be several columns; [] when none
    candidate_keys: list[str]  # single columns unique and non-null in the rows read
    time_span: dict | None     # {"column": str, "start": str, "end": str, "exact": bool}
    join_candidates: list[JoinCandidate]
    description: str           # "" until notes are merged
    grain: str                 # what one row represents; "" until notes are merged
    units: dict[str, str]      # column name -> unit
    caveats: str
    description_source: str    # "human", "draft" or "none"
    error: str | None
    profiled_at: str           # UTC, ISO 8601

def make_id(database: str, schema: str, name: str) -> str
def write_catalogue(entries: list[Entry], path: str) -> None
def read_catalogue(path: str) -> list[Entry]
```

`make_id` joins the three parts with dots, lower-cased. If Task 1 agreed a different rule (for example for partitioned tables), use that and update the test.

`pyproject.toml` pins SQLAlchemy and the driver to the versions Task 1 found installed, and registers the `postgres` pytest marker.

- [ ] **Step 1: Write the failing tests**

```python
def test_make_id():
    assert make_id("Finance", "public", "Orders") == "finance.public.orders"

def test_catalogue_round_trips(tmp_path):
    entry = sample_entry()          # helper building an Entry with one Column and one JoinCandidate
    path = tmp_path / "datasets.jsonl"
    write_catalogue([entry], str(path))
    assert read_catalogue(str(path)) == [entry]
    assert len(path.read_text().splitlines()) == 1

def test_write_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="duplicate id"):
        write_catalogue([sample_entry(), sample_entry()], str(tmp_path / "d.jsonl"))

def test_write_sorts_by_id(tmp_path): ...   # two entries written out of order are read back in id order
```

- [ ] **Step 2: Run** `pytest tests/test_entry.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement `entry.py`.** One JSON object per line, keys in dataclass order, UTF-8.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with message `Add catalogue entry model`.

---

### Task 3: Connect, discover and profile

**Files:**
- Create: `datacat/db.py`, `datacat/profile.py`, `tests/conftest.py`, `dataset-challenge/sources.toml`
- Test: `tests/test_db.py`, `tests/test_profile.py`

**Interfaces:**
- Consumes: `Entry`, `Column`, `JoinCandidate`, `make_id` from Task 2.
- Produces:

```python
# db.py
@dataclass
class DatabaseConfig:
    name: str                  # the name used in dataset ids
    url_env: str               # environment variable holding the SQLAlchemy URL
    schemas: list[str]         # [] means every schema except the system ones
    exclude: list[str]         # table names or schema.table to leave out

@dataclass
class TableRef:
    id: str
    database: str
    schema: str
    name: str
    kind: str

def load_sources(path: str) -> list[DatabaseConfig]
def connect(cfg: DatabaseConfig, *, statement_timeout_ms: int = 60_000) -> Engine
def discover(engine: Engine, cfg: DatabaseConfig) -> list[TableRef]

# profile.py
def map_type(sa_type: TypeEngine) -> str
def profile_table(engine: Engine, ref: TableRef, *, sample_rows: int = 100_000,
                  examples: int = 3, distinct_cap: int = 10_000
                  ) -> tuple[Entry, dict[str, set[str]]]
```

`sources.toml`:

```toml
[[database]]
name = "finance"
url_env = "DATACAT_DB_FINANCE"
schemas = ["public", "reporting"]
exclude = ["public.schema_migrations"]
```

Rules the tests pin:

- `connect` raises `RuntimeError` naming the variable when it is unset, and never includes the URL in any message. For a PostgreSQL URL it passes `options="-c default_transaction_read_only=on -c statement_timeout=<ms>"` in `connect_args`.
- `discover` uses `sqlalchemy.inspect`. It returns tables, views and materialized views, skips `pg_catalog`, `information_schema` and `pg_toast`, honours `schemas` and `exclude`, and sorts by id. On SQLite the schema is `main`.
- `map_type`: `Integer` family gives `integer`; `Numeric` and `Float` give `number`; `Date` gives `date`; `DateTime` gives `datetime`; `Boolean` gives `boolean`; everything else (text, uuid, json, arrays, enums, unknown) gives `text`. `db_type` always records what the database declared.
- `profile_table` takes column names, types, nullability, comments, the primary key and foreign keys from the inspector. Each foreign key becomes a `JoinCandidate` with `source="declared"` and `overlap=None`, pointing at `make_id(database, referred_schema, referred_table)`.
- **Row count.** On PostgreSQL, read `reltuples` for the table. If it is above `sample_rows`, use it and set `row_count_exact=False`. Otherwise, and on other databases, run `COUNT(*)` and set `row_count_exact=True`. If the estimate is `-1` (never analysed) and `COUNT(*)` times out, `row_count` is `None`.
- **Sample.** When the row count is at most `sample_rows`, or unknown, read rows with `LIMIT sample_rows`. When it is larger: on PostgreSQL, for a table, use `TABLESAMPLE SYSTEM (p)` with `p` chosen to return about `sample_rows` rows, plus `LIMIT sample_rows`; for a view, or on other databases, use `LIMIT sample_rows`. Set `sampled=True` whenever fewer rows were read than the table holds.
- `null_fraction`, `distinct_count`, `min`, `max`, `examples` and `candidate_keys` are computed in Python from the rows read, with every value turned to a string. A column is a candidate key when it has no missing values and as many distinct values as rows read, and `distinct_capped` is false.
- **Time span** uses the first `date` or `datetime` column by column order. It runs `SELECT min(col), max(col)` for an exact answer; if that times out it uses the sample's min and max with `"exact": false`.
- Any database error while profiling (permission denied, timeout on the sample, a broken view) returns an entry with `error` set to a one-line message, whatever was learned from the inspector before the failure, and an empty value dict. It never raises.
- The returned dict maps each column to the distinct values seen, at most `distinct_cap`, for Task 4.

- [ ] **Step 1: Write `conftest.py`.** A fixture `shop` that creates a SQLite file in `tmp_path` and returns `(engine, cfg)`:
  - `customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, joined DATE)`, 30 rows;
  - `orders(order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), order_date DATE, amount NUMERIC)`, 40 rows, order dates 2024-01-05 to 2024-03-09, 10 with a null amount;
  - `events(customer_id INTEGER, happened_at TIMESTAMP, kind TEXT)`, no primary key, 6 rows of which 2 are identical;
  - a view `recent_orders` over `orders`;
  - a view `broken` over a table that is then dropped.

  Also the `postgres` marker and its skip rule, and a `pg` fixture that creates the same tables in a uniquely named schema of the scratch database and drops that schema afterwards.

- [ ] **Step 2: Write the failing tests**

```python
# test_db.py
def test_missing_url_variable_is_named(monkeypatch):
    monkeypatch.delenv("DATACAT_DB_X", raising=False)
    with pytest.raises(RuntimeError, match="DATACAT_DB_X"):
        connect(DatabaseConfig("x", "DATACAT_DB_X", [], []))

def test_load_sources(tmp_path): ...            # the example above parses to one DatabaseConfig

def test_discover_finds_tables_and_views(shop):
    engine, cfg = shop
    refs = discover(engine, cfg)
    assert [r.name for r in refs] == ["broken", "customers", "events", "orders", "recent_orders"]
    assert {r.name: r.kind for r in refs}["recent_orders"] == "view"
    assert refs[1].id == "shop.main.customers"

def test_discover_honours_exclude(shop): ...    # exclude=["events"] leaves four

# test_profile.py
def test_profile_table(shop):
    entry, values = profile_table(engine, ref("orders"))
    assert entry.error is None and entry.sampled is False
    assert (entry.row_count, entry.row_count_exact) == (40, True)
    assert [c.type for c in entry.columns] == ["integer", "integer", "date", "number"]
    assert entry.columns[3].null_fraction == 0.25
    assert entry.primary_key == ["order_id"] and entry.candidate_keys == ["order_id"]
    assert entry.time_span == {"column": "order_date", "start": "2024-01-05", "end": "2024-03-09", "exact": True}
    assert entry.join_candidates == [JoinCandidate("customer_id", "shop.main.customers", "id", "declared", None)]
    assert len(values["customer_id"]) == 30

def test_table_with_duplicate_rows_has_no_keys(shop):
    entry, _ = profile_table(engine, ref("events"))
    assert entry.primary_key == [] and entry.candidate_keys == []

def test_view_is_profiled(shop): ...            # recent_orders: kind "view", columns present, no error
def test_broken_view_gives_error_entry(shop):
    entry, values = profile_table(engine, ref("broken"))
    assert entry.error and values == {}
def test_examples_can_be_switched_off(shop): ...   # examples=0 gives [] for every column
def test_large_table_is_sampled(shop):
    entry, _ = profile_table(engine, ref("orders"), sample_rows=10)
    assert entry.sampled is True and entry.row_count == 40
    assert all(c.distinct_count <= 10 for c in entry.columns)

def test_map_type():
    assert map_type(sa.BigInteger()) == "integer"
    assert map_type(sa.Numeric(12, 2)) == "number"
    assert map_type(sa.DateTime(timezone=True)) == "datetime"
    assert map_type(sa.JSON()) == "text"

@pytest.mark.postgres
def test_connection_is_read_only(pg):
    with pytest.raises(sa.exc.DBAPIError):
        with engine.begin() as conn:
            conn.execute(sa.text(f"INSERT INTO {schema}.customers (id, name) VALUES (999, 'x')"))

@pytest.mark.postgres
def test_comments_are_read(pg): ...             # COMMENT ON TABLE and COLUMN set by the fixture appear on the entry

@pytest.mark.postgres
def test_estimate_is_used_for_large_tables(pg):
    # fixture has run ANALYZE on its own scratch table; sample_rows=10
    assert entry.row_count_exact is False and entry.sampled is True

@pytest.mark.postgres
def test_statement_timeout_gives_error_entry(pg): ...   # connect(statement_timeout_ms=1) against a view calling pg_sleep(1)
```

- [ ] **Step 3: Run** `pytest tests/test_db.py tests/test_profile.py -v`. Expected: fails on import.
- [ ] **Step 4: Implement `db.py` and `profile.py`.** Build queries with SQLAlchemy Core (`sa.table`, `sa.select`, `sa.func`), not string formatting, so identifiers are quoted correctly. Keep the PostgreSQL-only statements (`reltuples`, `TABLESAMPLE`) behind a check of `engine.dialect.name`.
- [ ] **Step 5: Run the tests,** with `DATACAT_TEST_PG_URL` set if a scratch database exists. Expected: pass; note how many were skipped.
- [ ] **Step 6: Commit** with message `Profile database tables into catalogue entries`.

---

### Task 4: Likely joins between datasets

Declared foreign keys are already on the entries from Task 3. This task adds the joins nobody declared, which in most real databases is most of them.

**Files:**
- Create: `datacat/joins.py`
- Test: `tests/test_joins.py`

**Interfaces:**
- Consumes: `Entry`, `JoinCandidate`; the value sets from `profile_table`.
- Produces:

```python
def find_join_candidates(entries: list[Entry],
                         values: dict[str, dict[str, set[str]]],   # dataset id -> column -> values
                         *, min_overlap: float = 0.5, min_distinct: int = 20,
                         top: int = 5) -> None    # adds to entry.join_candidates in place
```

Two columns in different datasets are an inferred candidate when both have the same type, that type is `integer`, `text` or `date`, both have at least `min_distinct` distinct values, and `overlap = len(a & b) / min(len(a), len(b))` is at least `min_overlap`. A pair that is already a declared join is not added again. Declared joins are all kept and listed first; then at most `top` inferred candidates, highest overlap first, ties broken by other dataset id then column name. Every inferred candidate appears on both entries. Datasets in different databases can be candidates; whether such a join can actually be run is a question for later.

These thresholds are a first guess. An inferred join is a hint for the model and for the person writing notes, not a fact. Sequential integer ids overlap between unrelated tables; expect false positives and report how many look wrong.

- [ ] **Step 1: Write the failing tests**

```python
def test_undeclared_shared_key_is_found_on_both_sides():
    # events.customer_id and customers.id share 30 integer values; no foreign key
    find_join_candidates(entries, values)
    assert events.join_candidates == [JoinCandidate("customer_id", "shop.main.customers", "id", "inferred", 1.0)]
    assert JoinCandidate("id", "shop.main.events", "customer_id", "inferred", 1.0) in customers.join_candidates

def test_declared_join_is_kept_first_and_not_duplicated(): ...   # orders.customer_id: one declared candidate, no inferred twin
def test_small_columns_are_ignored(): ...        # two columns sharing 5 values: no candidate
def test_different_types_are_ignored(): ...      # integer column vs text column with the same digits: no candidate
def test_low_overlap_is_ignored(): ...           # 30 values each, 10 shared: no candidate
def test_only_top_inferred_candidates_are_kept(): ...   # 7 matching datasets, top=5: 5 kept, highest overlap first
def test_entries_with_errors_are_skipped(): ...
```

- [ ] **Step 2: Run** `pytest tests/test_joins.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement `joins.py`.**
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with message `Suggest undeclared joins between datasets`.

---

### Task 5: Notes, the build command, then stop

**Files:**
- Create: `datacat/notes.py`, `datacat/cli.py`, `datacat/__main__.py`
- Test: `tests/test_notes.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 2 to 4.
- Produces:

```python
def load_notes(path: str) -> dict[str, dict]             # {} when the file does not exist
def apply_notes(entries: list[Entry], notes: dict[str, dict]) -> list[str]   # ids with no human note
def write_notes_template(entries: list[Entry], path: str) -> None
```

`notes.toml` has one table per dataset id:

```toml
["finance.public.invoice_lines"]
description = "Invoiced sales, one line per invoice line."
grain = "one invoice line"
caveats = "Amounts are in pounds until 2024-06-30 and in euros after."
reviewed = true

["finance.public.invoice_lines".units]
amount = "GBP then EUR"
```

`apply_notes` copies `description`, `grain`, `caveats` and `units` onto the matching entry and sets `description_source` to `"human"` when `reviewed` is true, `"draft"` when it is false or absent, and `"none"` when the dataset has no table in the file. A table whose id matches no entry raises `ValueError` naming the id. `write_notes_template` writes a table for every entry that has none, with `description` pre-filled from the database's table comment (empty when there is none) and `reviewed = false`, and never overwrites an existing file: it writes `notes.template.toml` beside it.

Command line:

```
python -m datacat build --sources sources.toml --out catalogue/
                        [--sample-rows 100000] [--timeout-seconds 60]
                        [--no-examples] [--limit N]
```

`build` connects to each database in turn, discovers and profiles its tables, finds joins across all of them, merges `catalogue/notes.toml` if present, writes `catalogue/datasets.jsonl` and the notes template, and prints one summary: databases, datasets found, profiled, failed (with ids and reasons), sampled, with no primary key, and missing a human note. It prints one progress line per table so a long run can be followed. A database that cannot be connected to is reported and skipped. Exit status 0 even when some datasets failed; 2 when none were found.

- [ ] **Step 1: Write the failing tests**

```python
def test_reviewed_note_marks_entry_human(tmp_path): ...
def test_unreviewed_note_marks_entry_draft(tmp_path): ...
def test_entry_without_note_is_none_and_reported(tmp_path):
    assert apply_notes([entry], {}) == [entry.id] and entry.description_source == "none"
def test_note_for_unknown_dataset_raises(tmp_path): ...
def test_template_does_not_overwrite_notes(tmp_path): ...
def test_template_prefills_from_table_comment(tmp_path): ...

def test_build_end_to_end(shop_sources, tmp_path, capsys):
    # shop_sources: a sources.toml pointing at the shop fixture through an environment variable
    assert main(["build", "--sources", str(shop_sources), "--out", str(out), "--no-examples"]) == 0
    entries = read_catalogue(str(out / "datasets.jsonl"))
    assert len(entries) == 5
    assert [e.name for e in entries if e.error] == ["broken"]
    assert all(c.examples == [] for e in entries for c in e.columns)
    printed = capsys.readouterr().out
    assert "failed: 1" in printed and "no primary key: " in printed
    assert "sqlite" not in printed.lower()        # the URL is never printed

def test_unreachable_database_is_skipped(tmp_path, capsys): ...   # two databases, one bad URL: exit 0, the good one is catalogued
def test_build_with_no_datasets_exits_2(tmp_path): ...
```

- [ ] **Step 2: Run** `pytest tests/test_notes.py tests/test_cli.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement** `notes.py`, `cli.py` (`main(argv) -> int`) and `__main__.py`.
- [ ] **Step 4: Run the full suite.** Expected: pass.
- [ ] **Step 5: Commit** with message `Add notes and the build command`.
- [ ] **Step 6: Build the real catalogue.** Write `sources.toml` for the agreed scope. Try `--limit 10` first and check the ten entries against the database yourself, column by column. Fix what is wrong. Then build the agreed scope, in quiet hours if the owner named any. Record how long it took.
- [ ] **Step 7: Draft notes, marked as drafts.** For each dataset, propose `description`, `grain` and `units` from the profile, the database comments and any documentation Task 1 found, in `notes.toml`, with `reviewed = false`. Where you are guessing, say so in `caveats`.
- [ ] **Step 8: Stop and report to the owner.** Give them: the build summary and run time; the failed datasets and why; how many tables have no primary key; how many joins are declared against how many are inferred, with the ten inferred joins you trust most and the ten you trust least; and anything surprising in the data (duplicate rows, a unit or format that changes part-way through a series, joins that would multiply rows, dates or numbers held as text). Those surprises matter: a later challenge is built from them.

Then ask for two things, and wait:
  1. Review `notes.toml`, correcting drafts and setting `reviewed = true`. A first pass over the datasets most likely to appear in questions is enough.
  2. Write `questions/questions.json` in the format in Task 7. Ten to fifteen questions, with a mix of: answered by one dataset; needing two or more blended; two similar-looking datasets where only one is right; and one or two that nothing here answers. You may offer candidate questions. Leave `expected` and `confirmed_by` for them.

---

### Task 6: Three views of the catalogue

**Files:**
- Create: `datacat/views.py`; modify `datacat/cli.py`
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: `Entry`.
- Produces:

```python
VIEWS = ("titles", "schema", "full")
def render(entries: list[Entry], view: str) -> str
def estimate_tokens(text: str) -> int      # len(text) // 4
```

Entries with `error` set are left out of every view. One block per dataset, blocks separated by a blank line:

- `titles`: the id alone.
- `schema`: the id, then `rows: N` (`rows: about N` when the count is an estimate), then one line per column: `  name (type)`.
- `full`: the schema view, plus `description:`, `grain:`, `primary key: a, b`, `time span: start to end (column)`, `units:`, `caveats:`, and one line per join candidate: `joins: column -> other_dataset.other_column (declared)` or `(likely)`. A line whose value is empty is omitted. When there is no human or draft description, the database's table comment is used for `description:`. Column lines add ` -- comment` when the column has one and ` e.g. a, b, c` when examples exist.

The three views are the experiment: they show how much the catalogue's detail changes the model's picks and what each level costs.

Command: `python -m datacat views --catalogue catalogue/datasets.jsonl` prints each view's character count and estimated tokens.

- [ ] **Step 1: Write the failing tests**

```python
def test_titles_view():
    assert render([orders, customers], "titles") == "shop.main.customers\n\nshop.main.orders"

def test_schema_view_lists_columns_and_rows():
    text = render([orders], "schema")
    assert "rows: 40" in text and "  order_date (date)" in text and "description" not in text

def test_estimated_row_count_says_about(): ...   # row_count_exact False: "rows: about 1200000"

def test_full_view_adds_meaning_and_joins():
    text = render([orders_with_notes], "full")
    assert "grain: one order" in text
    assert "primary key: order_id" in text
    assert "time span: 2024-01-05 to 2024-03-09 (order_date)" in text
    assert "joins: customer_id -> shop.main.customers.id (declared)" in text

def test_inferred_join_is_marked_likely(): ...
def test_table_comment_stands_in_for_missing_description(): ...
def test_full_view_omits_empty_lines(): ...     # no note, no comment: no "description:" or "caveats:" line
def test_error_entries_are_left_out(): ...
def test_unknown_view_raises(): ...             # ValueError
def test_each_view_is_longer_than_the_last(): ...
```

- [ ] **Step 2: Run** `pytest tests/test_views.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement** `views.py` and the `views` command.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with message `Render the catalogue at three levels of detail`.

---

### Task 7: Ask the model for a pick

**Files:**
- Create: `datacat/model.py`, `datacat/questions.py`, `datacat/recommend.py`
- Test: `tests/test_recommend.py`

**Interfaces:**
- Produces:

```python
@dataclass
class ModelReply:
    text: str
    input_tokens: int | None
    output_tokens: int | None

def complete(system: str, user: str) -> ModelReply      # model.py

@dataclass
class Question:
    id: str
    question: str
    type: str                    # "single", "blend", "lookalike" or "none"
    expected: list[str]          # dataset ids; [] for type "none"
    also_accept: list[list[str]] # other sets that are also right
    notes: str

def load_questions(path: str, valid_ids: set[str]) -> list[Question]

@dataclass
class Recommendation:
    datasets: list[str]          # cleaned: known ids only, no repeats, order kept
    join_on: list[str]
    reason: str
    unknown_ids: list[str]       # ids the model gave that are not in the catalogue
    input_tokens: int | None
    output_tokens: int | None
    error: str | None            # set when no usable reply was obtained

def recommend(question: str, catalogue_text: str, valid_ids: set[str],
              complete: Callable[[str, str], ModelReply] = model.complete) -> Recommendation
```

`model.complete` reads `DATACAT_GATEWAY_URL` (base URL of an OpenAI-compatible API), `DATACAT_GATEWAY_KEY` and `DATACAT_MODEL`, and posts to `{base}/chat/completions` with `urllib.request`, temperature 0, timeout 120 seconds. It takes token counts from `usage.prompt_tokens` and `usage.completion_tokens`. A missing variable raises `RuntimeError` naming it. If the gateway here speaks a different API (Task 1 will have shown this), change only this function. If the Prompt Lab is installed here, its `PROMPTLAB_GATEWAY_URL` and `PROMPTLAB_GATEWAY_KEY` hold the same kind of values.

`questions.json`:

```json
{
  "confirmed_by": "name of the person who wrote the expected answers",
  "questions": [
    {"id": "q01", "question": "...", "type": "blend",
     "expected": ["finance.public.orders", "finance.public.customers"],
     "also_accept": [], "notes": ""}
  ]
}
```

`load_questions` raises `ValueError` when: `confirmed_by` is missing or blank; a type is not one of the four; an id in `expected` or `also_accept` is not in `valid_ids`; a `none` question has a non-empty `expected`; any other type has an empty `expected`; two questions share an id.

`recommend` sends this system prompt, exactly:

```
You are choosing datasets to answer a question. You are given a catalogue of the datasets that exist. Each is a database table or view. Choose only from it, by id.

Choose the smallest set of datasets that can answer the question. If the answer needs data from more than one, list each one and say which columns join them. If nothing in the catalogue can answer the question, return an empty list. Do not guess.

Reply with one JSON object and nothing else:
{"datasets": ["id", ...], "join_on": ["dataset.column = dataset.column", ...], "reason": "one or two sentences"}
```

The user message is `Catalogue:\n\n{catalogue_text}\n\nQuestion: {question}`. The reply is parsed as the first JSON object in the text, allowing a Markdown code fence around it. If parsing fails, or `datasets` is not a list of strings, it asks once more, appending the error; a second failure returns a `Recommendation` with `error` set and empty `datasets`. Token counts are summed over both attempts.

- [ ] **Step 1: Write the failing tests,** each passing a fake `complete`.

```python
def test_clean_pick():
    rec = recommend("q", "cat", {"a.b.orders", "a.b.customers"},
                    fake('{"datasets": ["a.b.orders"], "join_on": [], "reason": "r"}'))
    assert rec.datasets == ["a.b.orders"] and rec.unknown_ids == [] and rec.error is None

def test_unknown_ids_are_dropped_and_counted():
    # model returns ["a.b.orders", "a.b.sales_2024", "a.b.orders"]
    assert rec.datasets == ["a.b.orders"] and rec.unknown_ids == ["a.b.sales_2024"]

def test_fenced_json_is_accepted(): ...
def test_empty_list_is_a_valid_pick(): ...       # datasets == [] and error is None
def test_bad_reply_is_retried_once(): ...        # first reply prose, second valid: one result, tokens summed
def test_two_bad_replies_give_error(): ...       # error set, datasets == []

def test_unconfirmed_questions_are_refused(tmp_path):
    with pytest.raises(ValueError, match="confirmed_by"):
        load_questions(path_with_blank_confirmed_by, {"a.b.orders"})

def test_question_naming_unknown_dataset_is_refused(tmp_path): ...
def test_none_question_must_have_empty_expected(tmp_path): ...
def test_missing_gateway_variable_is_named(monkeypatch):
    monkeypatch.delenv("DATACAT_GATEWAY_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATACAT_GATEWAY_URL"):
        model.complete("s", "u")
```

- [ ] **Step 2: Run** `pytest tests/test_recommend.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with message `Ask a model to pick datasets for a question`.

---

### Task 8: Score, report, run

**Files:**
- Create: `datacat/score.py`, `datacat/report.py`, `dataset-challenge/README.md`; modify `datacat/cli.py`
- Test: `tests/test_score.py`, additions to `tests/test_cli.py`

**Interfaces:**
- Consumes: `Question`, `Recommendation`, `render`, `estimate_tokens`, `recommend`.
- Produces:

```python
@dataclass
class Score:
    exact: bool        # pick equals expected, or one of also_accept, as a set
    recall: float      # share of expected ids picked; 1.0 when expected is empty and pick is empty
    precision: float   # share of picked ids that are expected; 1.0 when both empty, 0.0 when only the pick is non-empty
    unknown_ids: int

def score(rec: Recommendation, q: Question) -> Score
def write_report(runs: list[dict], meta: dict, path: str) -> None
```

Recall and precision are measured against whichever of `expected` and `also_accept` the pick overlaps most. A recommendation with `error` set scores `exact=False`, recall 0.0, precision 0.0.

Command:

```
python -m datacat run --catalogue catalogue/datasets.jsonl --questions questions/questions.json
                      --out results/ [--views titles,schema,full] [--repeats 3]
                      [--context-window 128000]
```

This command does not connect to any database. For each view, each question and each repeat it calls `recommend` and appends one line to `results/<UTC timestamp>/runs.jsonl` holding the view, question id, question type, repeat, pick, unknown ids, join_on, reason, error, token counts and the four score fields. A view whose `estimate_tokens` exceeds 80% of `--context-window` is skipped: no calls, and a message naming the view and both numbers.

`report.md` has, in this order:
1. Model, date, number of datasets and questions, repeats, and the name in `confirmed_by`.
2. **Results by view:** a table with a row per view: exact-match rate, mean recall, mean precision, runs with unknown ids, mean input tokens per question, and skipped views marked "too large for the context window".
3. **Results by question type:** exact-match rate for each type under each view.
4. **Consistency:** how many questions got the same pick on every repeat, per view.
5. **Misses:** every question a view got wrong on any repeat: the question, expected, picked, and the model's reason, grouped by question.
6. **Reading this:** the fixed text below.

```
This is a small test on questions one person wrote. It shows whether the idea works here; it is not a benchmark.

If the titles view scores as well as the full view, the questions are too easy: the table names give the answers away. If every view scores poorly on blends, look at whether the catalogue records what joins to what. If "none" questions are answered with a dataset, the model is guessing, which is the behaviour the challenge is meant to expose.
```

- [ ] **Step 1: Write the failing tests**

```python
def test_exact_match_ignores_order():
    assert score(rec(["a.b.customers", "a.b.orders"]), q(expected=["a.b.orders", "a.b.customers"])).exact is True

def test_also_accept_counts_as_exact(): ...
def test_partial_pick():
    s = score(rec(["a.b.orders", "a.b.refunds"]), q(expected=["a.b.orders", "a.b.customers"]))
    assert (s.exact, s.recall, s.precision) == (False, 0.5, 0.5)
def test_none_question_answered_with_nothing_is_exact(): ...     # recall 1.0, precision 1.0
def test_none_question_answered_with_a_dataset_fails(): ...      # exact False, precision 0.0
def test_errored_recommendation_scores_zero(): ...

def test_run_end_to_end(tmp_path, monkeypatch):
    # monkeypatch datacat.model.complete to always pick one dataset; 2 questions, views titles,full, repeats 2
    assert main(["run", ...]) == 0
    runs = [json.loads(l) for l in runs_path.read_text().splitlines()]
    assert len(runs) == 8
    report = report_path.read_text()
    assert "Results by view" in report and "Misses" in report and "not a benchmark" in report

def test_view_too_large_is_skipped_not_fatal(tmp_path, monkeypatch, capsys):
    # --context-window 10
    assert main(["run", ...]) == 0
    assert "too large for the context window" in report_path.read_text()
    assert runs_path.read_text() == ""

def test_run_refuses_unconfirmed_questions(tmp_path): ...        # exit status 2, message names confirmed_by
```

- [ ] **Step 2: Run** `pytest tests/test_score.py tests/test_cli.py -v`. Expected: the new tests fail.
- [ ] **Step 3: Implement** `score.py`, `report.py` and the `run` command.
- [ ] **Step 4: Run the full suite.** Expected: pass.
- [ ] **Step 5: Write `README.md`:** what this is for (three sentences), the three commands with one example each, the environment variables, the read-only role the build needs, and where output goes.
- [ ] **Step 6: Commit** with message `Score picks and write the report`.
- [ ] **Step 7: Run it for real** against the owner's confirmed questions with the agreed model. Read `report.md` and the misses yourself before handing it over.
- [ ] **Step 8: Report to the owner.** Lead with the answer to their question: can the model recommend the right datasets from the catalogue, and how much does the catalogue's detail matter? Then: what it cost in tokens per view; which questions it got wrong and what the wrong picks have in common; whether the questions look too easy or too hard by the report's own reading guide; and what you would change in the catalogue next. Say what you did not do or could not check, including any PostgreSQL-only tests that were skipped.

---

## Out of scope

Do not build these. They come after the owner has read the report.

- An MCP server over the catalogue or the data.
- An orchestrator, subagents or a verifier.
- A search tool over the catalogue. It is needed only if a view does not fit in the context window; if that happens, report it. The likely design then is the catalogue loaded into a PostgreSQL table with an embedding per dataset (the `vector` extension), which is why Task 1 records whether that extension is installed.
- Storing the catalogue in a database. A file is enough to answer this plan's question and keeps the build read-only.
- Answering the questions from the data. This test stops at choosing the datasets.
- Planting traps in the data. Report the ones that are already there.
