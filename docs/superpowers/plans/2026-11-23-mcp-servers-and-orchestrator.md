# MCP Servers and Orchestrator Implementation Plan

> **For agentic workers:** Work through this plan task by task, in order. If you have the superpowers skills, use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 1 and 7 end with a **stop**: report to the course owner and wait for their answer before continuing.

**Goal:** Build the reference system for the advanced data challenge: a student asks a question, an orchestrating agent finds the relevant datasets through a catalogue MCP server, hands them to analyst subagents that each reach only their datasets through a data MCP server, and returns an answer; then measure how often the answer is right and what it costs.

**Architecture:** Two small MCP servers over stdio and a client for them. The catalogue server searches and describes datasets and never returns rows. The data server runs read-only SQL against one PostgreSQL database, restricted to a list of datasets given when it starts. An agent loop drives a model with tool calling under a shared token budget. The orchestrator is one such agent whose tools are the catalogue and `ask_analyst`; each analyst is a fresh agent whose only tools come from a data server started for it. A run command puts the owner's questions through the system under several configurations and writes a report.

**Tech Stack:** Python 3.11 or later; SQLAlchemy 2.0 with the PostgreSQL driver already used by `datacat`; standard library for everything else, including the MCP protocol layer. `pytest` for tests.

**Spec:** There is no separate spec. The next section is the spec. This plan follows `2026-11-23-dataset-catalogue-and-recommendation-test.md` (the "catalogue plan") and uses what it built.

---

## Background and decisions

**Why this exists.** The course owner is building an advanced challenge for data scientists on a course about agentic development. Real data is the centrepiece. The catalogue plan answered whether a model can choose datasets from a catalogue. This plan builds the working system around that: the tools an agent uses to reach the data, and the orchestration that splits the work. It is the instructor's reference implementation and the thing measurements are taken from. Turning it into student exercises is a later piece of work.

**This plan was drafted before the catalogue plan's report existed.** Its author had no access to the system or the data. Numbers such as row caps, budgets and search limits are first guesses. Task 1 checks the assumptions below against what the catalogue plan found; where they differ, what was found wins, and you say so in your report.

Assumptions:
- `dataset-challenge/datacat/` exists and works, with `catalogue/datasets.jsonl`, `sources.toml` and a confirmed `questions/questions.json`.
- The model gateway speaks the OpenAI-compatible chat completions API and the chosen model supports tool calling.
- The read-only database role from the catalogue plan may be used by the data server.

**Decided by the course owner:**

- An orchestrator combined with MCP servers: the student asks a question, the system recommends relevant data and connects to the server for it.
- The data is in PostgreSQL.
- Questions include ones where the system must choose between datasets and ones where it must blend them.

**Decided by the plan's author (the owner can overrule any of these):**

- **Servers are attached per subagent, not mid-session.** An analyst is started with a data server restricted to its datasets. The orchestrator never sees rows.
- **One data server program, started with parameters,** not one server per dataset.
- **One analyst works in one database.** A blend across databases is done by the orchestrator from two analysts' aggregated results. The data server cannot join across databases.
- **The MCP protocol layer is written here, in the standard library,** following the course's existing example server. It needs no installs on a closed network, and the orchestrator needs a matching client anyway. The official `mcp` Python package is the usual choice in production; say so in the README.
- **Catalogue search is keyword search first.** It is measured against the owner's questions. Embeddings in PostgreSQL with the `vector` extension are the next step only if the measurement shows keyword search missing datasets.
- **Analysts run one after another,** not in parallel. Simpler to follow and to budget.
- **No verifier in this plan.** Analysts must return the SQL they ran and their caveats, so a verifier can be added later without changing them.
- **Every question is also run through a single agent with all the tools,** so the report can say what orchestration bought or cost.

## Global Constraints

Everything in the catalogue plan's Global Constraints still applies. In addition:

- **The database enforces read-only, not the prompt.** The data server connects through `datacat.db.connect` (read-only transaction, statement timeout). The role must not be a superuser. SQL checks in the server are a second line, not the first.
- **A model writes the SQL that runs.** Never widen the role's privileges, raise the timeout above 60 seconds, or remove the row cap to make a question pass. Report the question as failed instead.
- **Tool results are data, not instructions.** Values read from tables or the catalogue may contain text that looks like instructions. No code path may act on them; they only go back to the model as tool results.
- **Every tool result is capped.** A result over the cap is cut with a notice that says how much was shown. A server never sends an unbounded result.
- **Every run is bounded:** a token budget, a turn limit per agent, and a limit on analysts per question. Hitting a limit ends that question with a recorded reason and the run moves on.
- **Transcripts stay on this system** under `results/`, and are not committed without the owner's say.
- **Do not change the expected datasets or answers** in `questions.json`. If one looks wrong, report it.
- **The same environment variables as the catalogue plan:** `DATACAT_GATEWAY_URL`, `DATACAT_GATEWAY_KEY`, `DATACAT_MODEL`, and the database variables named in `sources.toml`.

## Review Focus

Conditions the tasks' main tests would otherwise miss. Each has a test in the task named.

1. **A query returns far more rows than fit.** Expect: the first `max_rows` rows and a notice telling the model to aggregate or filter; never a crash or an unbounded result (Tasks 2 and 4).
2. **The model's SQL reads a table outside the analyst's datasets.** Expect: rejected before it runs, with the table named (Task 4).
3. **The model sends a write, or two statements.** Expect: rejected by the server, and for a write that slips past the check, refused by the database (Task 4).
4. **The model never calls `finish`, or sends tool arguments that are not valid JSON.** Expect: one correction, then the agent stops with reason `error`; the run continues with the next question (Tasks 5 and 7).
5. **The budget runs out while an analyst is working.** Expect: the analyst stops with reason `budget`, the orchestrator is told, the question is recorded as stopped by budget (Tasks 5 and 6).
6. **A server process dies or stops answering.** Expect: the client raises `McpError` within its timeout, and the agent receives a tool error it can read (Task 2).

## File structure

```
dataset-challenge/
  datacat/                    from the catalogue plan
    questions.py              modified in Task 1: optional `answer`
  datachallenge/
    __init__.py
    __main__.py
    cli.py                    argparse: search-eval, ask, run
    stdio_server.py           MCP server side: tools/list, tools/call over stdio
    stdio_client.py           MCP client side: start a server process and call it
    search.py                 keyword search over catalogue entries
    catalogue_server.py       MCP server: search_datasets, describe_dataset
    sqlguard.py               single-statement check, tables a query reads, capped execution
    data_server.py            MCP server: list_datasets, describe_dataset, run_sql
    chat.py                   one function that calls the model with tools
    agent.py                  the agent loop, the budget, the finish tool
    orchestrator.py           analyst, orchestrator and single-agent modes
    evalrun.py                run questions, score, write the report
  configs/
    guarded.toml  naive.toml  single.toml
  tests/
    test_stdio.py  test_search.py  test_catalogue_server.py  test_sqlguard.py
    test_data_server.py  test_agent.py  test_orchestrator.py  test_evalrun.py
```

Tests reuse the catalogue plan's `shop` SQLite fixture and its `postgres` marker. Server tests start the real server as a subprocess and talk to it through the real client. Agent and orchestrator tests use a scripted model: a function that returns a prepared list of replies in order and fails the test if asked for more.

---

### Task 1: Check the ground, then stop

**Files:**
- Modify: `datacat/questions.py`, `tests/test_recommend.py`
- Create: `dataset-challenge/preflight.md`

- [ ] **Step 1: Read the catalogue plan's `inventory.md` and its latest `report.md`.** In `preflight.md`, write down for each assumption in this plan whether it holds, and what the report says about which catalogue view the model needed and where it went wrong.

- [ ] **Step 2: Check tool calling.** Send the chosen model one request with a single tool (`add(a, b)`) and the message "What is 2 + 3? Use the tool." Record whether it returns a tool call with valid JSON arguments. If it does not, stop here and tell the owner: nothing in this plan works without it.

- [ ] **Step 3: Let questions carry a checked answer.** Extend `Question` with `answer: dict | None`:

```json
{"id": "q01", "...": "...",
 "answer": {"value": 48210.5, "tolerance": 0.005, "sql": "the query the owner ran to get it"}}
```

`value` is a number, `tolerance` is relative and defaults to `0.005`, `sql` is free text for the record. `load_questions` raises `ValueError` when `answer` is present on a `none` question, or `value` is not a number.

```python
def test_question_answer_is_loaded(tmp_path):
    assert load_questions(path, ids)[0].answer == {"value": 48210.5, "tolerance": 0.005, "sql": "..."}
def test_answer_tolerance_defaults(tmp_path): ...      # omitted tolerance becomes 0.005
def test_none_question_with_answer_is_refused(tmp_path): ...
def test_question_without_answer_still_loads(tmp_path): ...   # answer is None
```

Run `pytest tests/test_recommend.py -v` (fails, then passes after the change). Commit with message `Let questions carry a checked answer`.

- [ ] **Step 4: Stop and report to the owner.** Send `preflight.md` and ask, in one message:
  1. to add an `answer` to each question that has one checkable number, worked out by them with their own SQL, not by you and not by a model. Questions without one are scored on datasets only;
  2. to confirm the database role the data server may use;
  3. a token budget per question they are content to spend (this plan assumes 200,000) and how many questions to run;
  4. any assumption that did not hold, and what you propose instead.

Do not start Task 2 until they answer.

---

### Task 2: MCP over stdio, both ends

**Files:**
- Create: `datachallenge/__init__.py`, `datachallenge/stdio_server.py`, `datachallenge/stdio_client.py`
- Test: `tests/test_stdio.py`

**Interfaces:**
- Produces:

```python
# stdio_server.py
class ToolError(Exception): ...          # raised by a handler: becomes a result with isError true

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict                   # JSON Schema object
    handler: Callable[[dict], str]

def serve(name: str, version: str, tools: list[Tool], *, instructions: str = "",
          max_chars: int = 20_000, stdin=sys.stdin, stdout=sys.stdout) -> None

# stdio_client.py
class McpError(RuntimeError): ...

@dataclass
class ToolResult:
    text: str
    is_error: bool

class McpClient:                          # a context manager
    def __init__(self, command: list[str], *, env: dict[str, str] | None = None,
                 timeout: float = 120.0): ...
    def list_tools(self) -> list[dict]    # each: name, description, inputSchema
    def call(self, name: str, arguments: dict) -> ToolResult
```

Protocol: newline-delimited JSON-RPC 2.0. The server answers `initialize` (protocol version `2025-06-18` unless the client asks for another it lists as supported: `2025-11-25`, `2025-03-26`, `2024-11-05`), `ping`, `tools/list` and `tools/call`; ignores notifications; answers an unknown method with error `-32601` and unparseable input with `-32700`. Only protocol messages go to stdout; diagnostics go to stderr. A handler's return value becomes one text content item. A missing required argument, an unknown tool, a `ToolError` and any other exception in a handler all become a result with `isError: true` and a one-line message; the server keeps running. Text longer than `max_chars` is cut and `\n[truncated: first {max_chars} of {n} characters shown]` appended.

The client starts the process, sends `initialize` then `notifications/initialized`, and on exit closes stdin and waits, killing the process after 5 seconds. A reply that does not arrive within `timeout`, a closed pipe, or a JSON-RPC error raises `McpError`.

- [ ] **Step 1: Write the failing tests.** A helper script in the test starts a server with tools `echo(text)`, `fail()` raising `ToolError("nope")`, `big()` returning 50,000 characters, `crash()` calling `os._exit(1)`, and `hang()` sleeping 30 seconds.

```python
def test_round_trip(server):
    with McpClient(server) as c:
        assert [t["name"] for t in c.list_tools()] == ["echo", "fail", "big", "crash", "hang"]
        assert c.call("echo", {"text": "hi"}) == ToolResult("hi", False)

def test_tool_error_is_a_result_not_an_exception(server):
    assert c.call("fail", {}) == ToolResult("nope", True)
def test_unknown_tool_and_missing_argument_are_error_results(server): ...
def test_large_result_is_truncated(server):
    r = c.call("big", {})
    assert len(r.text) < 20_200 and "[truncated: first 20000 of 50000 characters shown]" in r.text
def test_dead_server_raises_mcp_error(server):
    with pytest.raises(McpError):
        c.call("crash", {})
def test_silent_server_times_out(server): ...          # timeout=1.0, "hang": McpError within about a second
def test_stdout_carries_only_protocol_messages(server): ...   # every line the server writes parses as JSON-RPC
def test_version_negotiation(): ...                    # serve() driven through io.StringIO
def test_parse_error_and_unknown_method_codes(): ...
```

- [ ] **Step 2: Run** `pytest tests/test_stdio.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement both modules.** Read replies on a thread or with `selectors` so the timeout is real.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with message `Add a small MCP server and client over stdio`.

---

### Task 3: Catalogue search and the catalogue server

**Files:**
- Create: `datachallenge/search.py`, `datachallenge/catalogue_server.py`, `datachallenge/cli.py`, `datachallenge/__main__.py`
- Test: `tests/test_search.py`, `tests/test_catalogue_server.py`

**Interfaces:**
- Consumes: `datacat.entry.Entry`, `read_catalogue`, `datacat.views.render`, `datacat.questions.load_questions`; `Tool`, `serve`, `ToolError`.
- Produces:

```python
@dataclass
class Hit:
    id: str
    score: float
    line: str        # "id -- description (about N rows)"; the table comment when there is no description

def tokenize(text: str) -> list[str]
def build_index(entries: list[Entry]) -> "Index"
def search(index: "Index", query: str, limit: int = 5) -> list[Hit]
```

`tokenize` lower-cases, splits on anything that is not a letter or digit (so `order_date` gives `order`, `date`), and drops one-character tokens. Scoring is BM25 (`k1 = 1.5`, `b = 0.75`) over one document per dataset, built from its fields with the name's tokens counted three times, description, grain, caveats and table comment twice, and column names and column comments once. Entries with `error` set are not indexed. Hits with score 0 are not returned. Ties are broken by id.

The server, `python -m datachallenge.catalogue_server --catalogue catalogue/datasets.jsonl`, offers two tools with these descriptions, exactly:

- `search_datasets(query: string, limit: integer = 5)`: "Search the catalogue of datasets by keyword. Returns up to `limit` (at most 20) dataset ids with a one-line description each, best match first. Returns no rows of data. Search more than once with different words before deciding nothing fits."
- `describe_dataset(id: string)`: "Show one dataset's columns, types, keys, time span, units, caveats and known joins. Returns no rows of data."

`search_datasets` returns one hit line per line, or `No datasets matched.`. `describe_dataset` returns `render([entry], "full")`; an unknown id is a `ToolError` saying to use `search_datasets`.

Command `python -m datachallenge search-eval --catalogue ... --questions ...` uses each non-`none` question's text as the query and prints, for `k` in 5, 10 and 20, the share of expected datasets found in the top `k`, overall and by question type, then every question with an expected dataset missing from the top 20.

- [ ] **Step 1: Write the failing tests** over the `shop` catalogue with notes on two datasets.

```python
def test_tokenize():
    assert tokenize("Order_Date (UTC)") == ["order", "date", "utc"]
def test_name_match_ranks_first():
    assert search(index, "orders")[0].id == "shop.main.orders"
def test_description_words_are_searchable(): ...     # a word only in a note finds that dataset
def test_column_names_are_searchable(): ...          # "happened" finds shop.main.events
def test_no_match_returns_nothing():
    assert search(index, "zebra") == []
def test_limit_is_honoured(): ...
def test_error_entries_are_not_indexed(): ...        # "broken" never appears

def test_server_search_and_describe(catalogue_server):
    with McpClient(catalogue_server) as c:
        assert c.call("search_datasets", {"query": "orders"}).text.startswith("shop.main.orders -- ")
        assert "primary key: order_id" in c.call("describe_dataset", {"id": "shop.main.orders"}).text
def test_server_limit_is_capped_at_20(catalogue_server): ...
def test_describe_unknown_id_is_an_error_result(catalogue_server): ...
def test_search_eval_prints_recall(tmp_path, capsys): ...    # two questions; output contains "top 5: 1.00"
```

- [ ] **Step 2: Run** `pytest tests/test_search.py tests/test_catalogue_server.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement** the modules and the `search-eval` command.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Run `search-eval` on the real catalogue and questions** and keep the output for the final report. If fewer than 80% of expected datasets are in the top 10, carry on, but say so prominently in Task 7's report: it is the evidence for or against adding embeddings.
- [ ] **Step 6: Commit** with message `Add catalogue search and its MCP server`.

---

### Task 4: The SQL guard and the data server

**Files:**
- Create: `datachallenge/sqlguard.py`, `datachallenge/data_server.py`
- Test: `tests/test_sqlguard.py`, `tests/test_data_server.py`

**Interfaces:**
- Consumes: `datacat.db.load_sources`, `connect`; `read_catalogue`, `render`; `Tool`, `serve`, `ToolError`.
- Produces:

```python
class SqlRejected(Exception): ...

@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool          # the query had more than max_rows rows

def check_single_select(sql: str) -> str
def tables_read(conn: Connection, sql: str) -> set[str]            # "schema.name", lower-cased
def expand_scope(conn: Connection, datasets: list[tuple[str, str]]) -> set[str]   # (schema, name) pairs in
def run_query(engine: Engine, sql: str, allowed: set[str], max_rows: int) -> QueryResult
def format_result(result: QueryResult, max_rows: int) -> str
```

- `check_single_select` strips whitespace and one trailing semicolon and returns the rest. It raises `SqlRejected` when the text is empty, contains another semicolon, or does not start with `SELECT` or `WITH` (any case). A semicolon inside a string literal is rejected too; that is accepted as the price of a simple rule.
- `tables_read` asks the database which relations the statement reads, without running it. PostgreSQL: `EXPLAIN (FORMAT JSON)` and collect every node's `Schema` and `Relation Name`. SQLite: install an authorizer on the driver connection, prepare the statement with `EXPLAIN`, and collect the tables of each read action. A statement the database cannot plan raises `SqlRejected` carrying the database's message.
- `expand_scope` returns, for each dataset, the relations `SELECT * FROM schema.name` reads. For a plain table that is itself; for a view it is the view's underlying tables; for a partitioned table it is its partitions. This is how views and partitions stay usable. The consequence, to state in the README: allowing a view also allows direct queries on the tables under it.
- `run_query` calls `check_single_select`, then `tables_read`; any relation not in `allowed` raises `SqlRejected("This query reads tables outside your datasets: a.b, c.d")`. It then executes and fetches `max_rows + 1` rows. Database errors, including the statement timeout, raise `SqlRejected` with a one-line message.
- `format_result`: a header line of column names joined by ` | `, one line per row, then `[N rows]`, or when truncated: `[truncated: first {max_rows} rows shown; the query returned more. Aggregate in SQL or add a filter instead of reading rows.]`.

The server:

```
python -m datachallenge.data_server --sources sources.toml --database finance
       --catalogue catalogue/datasets.jsonl --datasets id,id,...
       [--max-rows 50] [--max-chars 20000] [--timeout-seconds 30]
```

It refuses to start, naming the problem, when a dataset id is not in the catalogue or belongs to another database. Tools, with these descriptions exactly:

- `list_datasets()`: "List the datasets you can query, with a one-line description each."
- `describe_dataset(id: string)`: "Show one dataset's columns, types, keys, time span, units, caveats and known joins. Read this before writing SQL against it."
- `run_sql(sql: string)`: "Run one read-only SELECT statement against the datasets you were given, written as schema.table. Returns at most {max_rows} rows. Compute totals, counts and averages in SQL; do not fetch rows to add them up yourself."

A `SqlRejected` becomes a `ToolError` with the same message, so the model can correct itself.

- [ ] **Step 1: Write the failing tests**

```python
# test_sqlguard.py
def test_check_single_select():
    assert check_single_select(" select 1 ; ") == "select 1"
    assert check_single_select("WITH t AS (SELECT 1) SELECT * FROM t").startswith("WITH")
    for bad in ["", "DELETE FROM orders", "select 1; select 2", "drop table orders"]:
        with pytest.raises(SqlRejected):
            check_single_select(bad)

def test_tables_read(shop):
    sql = "SELECT c.name, count(*) FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY 1"
    assert tables_read(conn, sql) == {"main.orders", "main.customers"}
def test_tables_read_sees_through_subqueries_and_ctes(shop): ...
def test_expand_scope_of_a_view_is_its_base_tables(shop):
    assert expand_scope(conn, [("main", "recent_orders")]) == {"main.orders"}

def test_out_of_scope_table_is_rejected_and_named(shop):
    with pytest.raises(SqlRejected, match="main.customers"):
        run_query(engine, "SELECT * FROM customers", {"main.orders"}, 50)
def test_rows_are_capped_and_marked(shop):
    r = run_query(engine, "SELECT * FROM orders", {"main.orders"}, 10)
    assert len(r.rows) == 10 and r.truncated is True
    assert "Aggregate in SQL" in format_result(r, 10)
def test_small_result_is_not_marked(shop): ...        # count(*) query: "[1 rows]"
def test_sql_error_is_rejected_with_the_message(shop): ...   # unknown column

@pytest.mark.postgres
def test_tables_read_on_postgres(pg): ...             # the join query above, schema-qualified
@pytest.mark.postgres
def test_write_hidden_in_a_cte_is_refused_by_the_database(pg):
    with pytest.raises(SqlRejected):
        run_query(engine, f"WITH d AS (DELETE FROM {schema}.orders RETURNING 1) SELECT count(*) FROM d", allowed, 50)
@pytest.mark.postgres
def test_slow_query_hits_the_timeout(pg): ...         # select pg_sleep(5) with a 1 second timeout

# test_data_server.py   (real subprocess, SQLite)
def test_run_sql_through_the_server(data_server):     # scoped to orders and customers
    with McpClient(data_server) as c:
        assert "40" in c.call("run_sql", {"sql": "SELECT count(*) FROM orders"}).text
def test_out_of_scope_query_is_an_error_result(data_server):
    r = c.call("run_sql", {"sql": "SELECT * FROM events"})
    assert r.is_error and "main.events" in r.text
def test_write_is_an_error_result(data_server): ...
def test_list_and_describe_cover_only_the_scope(data_server): ...
def test_server_refuses_unknown_dataset_at_start(tmp_path): ...   # process exits non-zero, stderr names the id
```

- [ ] **Step 2: Run** `pytest tests/test_sqlguard.py tests/test_data_server.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement both modules.**
- [ ] **Step 4: Run the tests,** with the scratch PostgreSQL database if there is one. Expected: pass; note how many were skipped.
- [ ] **Step 5: Try the server by hand against one real database** with two datasets in scope: a count, a query on a table outside the scope, and a `SELECT *` on the largest table in scope. Confirm the last returns `max_rows` rows and the notice, quickly.
- [ ] **Step 6: Commit** with message `Add the scoped read-only data server`.

---

### Task 5: The agent loop and the budget

**Files:**
- Create: `datachallenge/chat.py`, `datachallenge/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Produces:

```python
# chat.py
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict | None
    arguments_error: str | None        # set when the model's arguments were not a JSON object

@dataclass
class ChatReply:
    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int

def chat(messages: list[dict], tools: list[dict]) -> ChatReply

# agent.py
class Budget:
    def __init__(self, max_tokens: int): ...
    def spend(self, role: str, input_tokens: int, output_tokens: int) -> None
    @property
    def remaining(self) -> int
    @property
    def exhausted(self) -> bool
    def by_role(self) -> dict[str, dict[str, int]]      # role -> {"input": n, "output": n, "requests": n}

@dataclass
class AgentTool:
    description: str
    input_schema: dict
    run: Callable[[dict], str]          # may raise; the message goes back to the model

@dataclass
class AgentResult:
    final: dict | None                  # the arguments of the finish call
    stop_reason: str                    # "finished", "max_turns", "budget" or "error"
    turns: int
    transcript: list[dict]              # every message, in order

def run_agent(*, role: str, system: str, task: str, tools: dict[str, AgentTool],
              finish_schema: dict, budget: Budget, max_turns: int = 20,
              chat: Callable = chat) -> AgentResult
```

`chat` posts to `{DATACAT_GATEWAY_URL}/chat/completions` with the model, messages, `tools` in the OpenAI function format, and temperature 0; timeout 300 seconds. When the gateway returns no usage, it estimates tokens as characters divided by four.

`run_agent` offers the model the given tools plus `finish`, whose parameters are `finish_schema`. Each turn: if the budget is exhausted, stop with `budget`; call `chat`; spend its tokens under `role`. For each tool call in the reply, in order: `finish` with every required key present ends the run with `finished`; `finish` with a key missing gets a tool message naming it; arguments that failed to parse get a tool message quoting the error; an unknown tool gets a tool message listing the tools; otherwise the tool runs and its text, or its exception's message prefixed `Error: `, is the tool message. A reply with no tool call gets one user message, `Call a tool, or call finish with your answer.`; a second such reply in a row stops with `error`. Reaching `max_turns` stops with `max_turns`.

- [ ] **Step 1: Write the failing tests** with a scripted `chat`.

```python
def test_tool_then_finish():
    result = run_agent(role="a", system="s", task="t", tools={"double": tool(lambda a: str(a["n"] * 2))},
                       finish_schema=ANSWER, budget=Budget(10_000),
                       chat=script(call("double", {"n": 4}), call("finish", {"answer": "8"})))
    assert (result.stop_reason, result.final, result.turns) == ("finished", {"answer": "8"}, 2)
    assert any(m.get("role") == "tool" and m["content"] == "8" for m in result.transcript)

def test_tool_exception_goes_back_to_the_model(): ...   # tool raises ValueError("bad"): tool message "Error: bad", run continues
def test_unparseable_arguments_are_reported_to_the_model(): ...
def test_unknown_tool_is_reported_to_the_model(): ...
def test_finish_missing_a_key_is_sent_back(): ...
def test_text_only_reply_is_nudged_once_then_stops():
    assert run_agent(..., chat=script(text("thinking"), text("still thinking"))).stop_reason == "error"
def test_max_turns(): ...                               # max_turns=3, script of 3 tool calls: "max_turns"
def test_budget_stops_the_run():
    # each scripted reply costs 600 tokens; Budget(1000)
    assert result.stop_reason == "budget" and result.turns == 2
def test_budget_is_shared_and_split_by_role(): ...     # two run_agent calls on one Budget: by_role has both roles
def test_missing_gateway_variable_is_named(monkeypatch): ...
```

- [ ] **Step 2: Run** `pytest tests/test_agent.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement both modules.**
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** with message `Add the agent loop with a shared token budget`.

---

### Task 6: Analyst, orchestrator and the single-agent baseline

**Files:**
- Create: `datachallenge/orchestrator.py`, `configs/guarded.toml`, `configs/naive.toml`, `configs/single.toml`; modify `datachallenge/cli.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `McpClient`; `run_agent`, `Budget`, `AgentTool`, `AgentResult`; the two server programs; `read_catalogue`.
- Produces:

```python
@dataclass
class RunConfig:
    name: str
    mode: str                 # "orchestrated" or "single"
    max_rows: int
    max_chars: int
    token_budget: int
    max_turns: int
    max_analysts: int
    sql_timeout_seconds: int

@dataclass
class Paths:
    catalogue: str
    sources: str

@dataclass
class Outcome:
    final: dict | None        # answer, value, datasets, cannot_answer
    stop_reason: str
    analysts: list[dict]      # per analyst: datasets, task, final, stop_reason, turns
    tokens: dict              # Budget.by_role()
    transcripts: dict[str, list[dict]]   # "orchestrator", "analyst-1", ...

def load_config(path: str) -> RunConfig
def run_analyst(task: str, dataset_ids: list[str], cfg: RunConfig, paths: Paths,
                budget: Budget, chat: Callable) -> AgentResult
def answer_question(question: str, cfg: RunConfig, paths: Paths, chat: Callable = chat) -> Outcome
```

Configurations:

| File | mode | max_rows | max_chars | token_budget | max_turns | max_analysts | sql_timeout_seconds |
|---|---|---|---|---|---|---|---|
| `guarded.toml` | orchestrated | 50 | 20000 | 200000 | 20 | 4 | 30 |
| `naive.toml` | orchestrated | 100000 | 2000000 | 200000 | 20 | 4 | 30 |
| `single.toml` | single | 50 | 20000 | 200000 | 40 | 0 | 30 |

`naive` exists to show what an uncapped tool does to a context window. Expect it to fail; that is its purpose.

**Analyst.** `run_analyst` raises `ValueError` if the datasets are not all in one database. It starts a data server for that database restricted to those datasets, exposes its three tools unchanged, and runs an agent with role `analyst`, this system prompt, and the task as the user message:

```
You are a data analyst. You can query only the datasets you have been given. Read each dataset's description before writing SQL against it, and take its units, caveats and what one row represents seriously.

Work out the answer in SQL. Before trusting a number, check the things that make numbers wrong: duplicate rows, a join that repeats rows, missing values, a unit or definition that changes part-way through the data.

When you have the answer, or are sure the datasets cannot give one, call finish. Report every SQL statement your answer depends on, and say plainly what you did not check.
```

Finish schema, all required: `answer` (string), `value` (number or null), `sql` (array of strings), `datasets_used` (array of strings), `caveats` (string).

**Orchestrator.** In `orchestrated` mode, `answer_question` starts the catalogue server and runs an agent with role `orchestrator` whose tools are `search_datasets`, `describe_dataset`, and:

- `ask_analyst(dataset_ids: array of string, task: string)`: "Hand a self-contained task to an analyst who can query only the datasets you list. All of them must be in the same database (the first part of the id). The analyst knows nothing about the user's question except what you write in the task. Returns the analyst's answer, the SQL it ran and its caveats."

`ask_analyst` returns the analyst's `final` as JSON, cut to 4,000 characters. When the analyst did not finish it returns `The analyst stopped without an answer: {stop_reason}.` Datasets in more than one database, an id not in the catalogue, or more than `max_analysts` calls return an error text explaining which. System prompt:

```
You answer questions about data by finding the right datasets and delegating the analysis. You cannot query data yourself.

First search the catalogue and read the descriptions of likely datasets. Choose the smallest set that can answer the question. Then give an analyst those datasets and a task that states exactly what to compute, including any filter, period or unit the question implies. If the question needs datasets from different databases, use one analyst for each and combine their results yourself.

You have a limited token budget. Do not describe datasets you will not use, and do not ask an analyst for rows.

If nothing in the catalogue can answer the question, say so. Do not answer from a dataset that only looks related. When you are done, call finish.
```

Finish schema, all required: `answer` (string), `value` (number or null), `datasets` (array of dataset ids the answer rests on), `cannot_answer` (boolean).

**Single agent.** In `single` mode there is one agent with role `single`: the catalogue tools plus `run_sql(database: string, sql: string)`, which runs through a data server for that database with every one of its datasets in scope, started on first use. Its system prompt is the analyst's first two paragraphs preceded by "You answer questions about data. Search the catalogue to find the right datasets, then query them.", with the orchestrator's last paragraph and finish schema.

All server processes are closed when `answer_question` returns, whatever happened. An `McpError` from a tool reaches the model as that tool's error text.

Command: `python -m datachallenge ask "question" --config configs/guarded.toml --catalogue ... --sources ...` prints the answer, the datasets, the stop reason and tokens by role.

- [ ] **Step 1: Write the failing tests.** Real servers on the `shop` fixture, scripted model.

```python
def test_orchestrated_question_end_to_end(shop_paths):
    chat = script(
        call("search_datasets", {"query": "orders"}),
        call("ask_analyst", {"dataset_ids": ["shop.main.orders"], "task": "Count the orders."}),
        call("run_sql", {"sql": "SELECT count(*) FROM orders"}),                       # analyst
        call("finish", {"answer": "40", "value": 40, "sql": ["SELECT count(*) FROM orders"],
                        "datasets_used": ["shop.main.orders"], "caveats": ""}),        # analyst
        call("finish", {"answer": "40 orders", "value": 40,
                        "datasets": ["shop.main.orders"], "cannot_answer": False}))
    out = answer_question("How many orders?", GUARDED, shop_paths, chat)
    assert out.stop_reason == "finished" and out.final["value"] == 40
    assert set(out.tokens) == {"orchestrator", "analyst"}
    assert len(out.analysts) == 1 and out.analysts[0]["final"]["sql"]
    assert "40" in tool_message_after(out.transcripts["analyst-1"], "run_sql")

def test_orchestrator_never_receives_rows(shop_paths): ...     # no tool message in the orchestrator transcript contains a row from orders
def test_analyst_cannot_read_outside_its_datasets(shop_paths): ...   # analyst script queries customers: its tool message is the scope error
def test_analyst_limit_is_enforced(shop_paths): ...            # max_analysts=1, second ask_analyst returns the limit message
def test_unknown_dataset_id_is_reported_to_the_orchestrator(shop_paths): ...
def test_datasets_in_two_databases_are_refused(two_db_paths): ...
def test_budget_running_out_in_the_analyst(shop_paths):
    # token_budget small enough to run out on the analyst's second request
    assert out.analysts[0]["stop_reason"] == "budget" and out.stop_reason == "budget"
def test_single_mode_end_to_end(shop_paths): ...               # search, run_sql(database="shop", ...), finish; tokens keyed "single"
def test_servers_are_closed_after_a_failure(shop_paths): ...   # scripted chat raises; no child processes remain
def test_load_config(tmp_path): ...
```

- [ ] **Step 2: Run** `pytest tests/test_orchestrator.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement** `orchestrator.py`, the three config files and the `ask` command.
- [ ] **Step 4: Run the full suite.** Expected: pass.
- [ ] **Step 5: Ask one real question** with `ask` and the guarded configuration: one of the owner's `single` questions. Read both transcripts. Check the orchestrator saw no rows and the analyst's SQL is sensible.
- [ ] **Step 6: Commit** with message `Add the orchestrator, analysts and the single-agent baseline`.

---

### Task 7: Run the questions, report, then stop

**Files:**
- Create: `datachallenge/evalrun.py`; modify `datachallenge/cli.py`, `dataset-challenge/README.md`
- Test: `tests/test_evalrun.py`

**Interfaces:**
- Consumes: `answer_question`, `Outcome`, `RunConfig`; `Question`; `datacat.score.score`.
- Produces:

```python
@dataclass
class RunScore:
    datasets_exact: bool
    datasets_recall: float
    datasets_precision: float
    answer_correct: bool | None        # None when the question has no checked answer
    declined: bool                     # the system said it cannot answer

def score_outcome(outcome: Outcome, q: Question) -> RunScore
def write_report(rows: list[dict], meta: dict, path: str) -> None
```

Dataset scores come from `datacat.score.score` applied to `final["datasets"]`. `answer_correct` is true when `final["value"]` is a number and `abs(value - expected) <= tolerance * abs(expected)` (an expected value of 0 requires an exact 0). For a `none` question the run is right when `cannot_answer` is true. An outcome with no `final` scores false or zero throughout.

Command:

```
python -m datachallenge run --config configs/guarded.toml [--config ...]
       --questions questions/questions.json --catalogue ... --sources ...
       --out results/ [--repeats 1] [--only q01,q02]
```

For each configuration, question and repeat it calls `answer_question`, appends a line to `results/<UTC timestamp>/runs.jsonl` (configuration, question id and type, repeat, final, stop reason, the five scores, tokens by role, `analysts` (the list from `Outcome.analysts`: each analyst's datasets, task, final and stop reason, which the verifier plan replays), turns, seconds taken), and writes the transcripts to `transcripts/<config>-<question>-<repeat>.json`. An exception while answering one question is recorded as stop reason `crashed` with its message, and the run continues. It prints one progress line per question.

`report.md`, in this order:
1. Model, date, number of questions, repeats, configurations, and the name in `confirmed_by`.
2. **Results by configuration:** answers right (of questions with a checked answer), datasets exactly right, `none` questions correctly declined, questions stopped by budget, turns or error, mean tokens per question, mean seconds per question.
3. **Where the tokens went:** mean tokens per question by role, per configuration.
4. **Results by question type,** per configuration.
5. **Confidently wrong:** every run that finished with a number that is not the checked answer and did not decline. For each: question, expected value, value given, datasets used, the analyst's SQL and its stated caveats.
6. **Stopped runs:** every run that did not finish, with its reason.
7. **Reading this:** the fixed text below.

```
This is a small test on questions one person wrote. It shows how this system behaves here; it is not a benchmark.

The "confidently wrong" section matters most. Each entry is an answer that looked finished and was not right. Read the SQL: the cause is usually in the data (duplicate rows, a join that repeats rows, a unit that changes) and not in the arithmetic.

Compare guarded with naive to see what a row cap is worth, and guarded with single to see what splitting the work bought or cost.
```

- [ ] **Step 1: Write the failing tests**

```python
def test_answer_within_tolerance_is_correct():
    assert score_outcome(outcome(value=48300.0), q(answer={"value": 48210.5, "tolerance": 0.005})).answer_correct is True
def test_answer_outside_tolerance_is_wrong(): ...          # 49000.0: False
def test_no_checked_answer_scores_none(): ...              # answer_correct is None
def test_none_question_is_right_when_declined(): ...
def test_none_question_answered_is_wrong(): ...
def test_unfinished_outcome_scores_zero(): ...

def test_run_end_to_end(shop_paths, tmp_path, monkeypatch):
    # monkeypatch answer_question: q01 right, q02 a wrong number, q03 raises RuntimeError
    assert main(["run", "--config", "configs/guarded.toml", ...]) == 0
    rows = [json.loads(l) for l in runs_path.read_text().splitlines()]
    assert [r["stop_reason"] for r in rows] == ["finished", "finished", "crashed"]
    report = report_path.read_text()
    assert "Confidently wrong" in report and "q02" in report.split("Confidently wrong")[1]
    assert "not a benchmark" in report
    assert (out / "transcripts").is_dir()

def test_two_configurations_give_two_rows_in_the_summary(...): ...
def test_only_filters_questions(...): ...
```

- [ ] **Step 2: Run** `pytest tests/test_evalrun.py -v`. Expected: fails on import.
- [ ] **Step 3: Implement** `evalrun.py` and the `run` command.
- [ ] **Step 4: Run the full suite.** Expected: pass.
- [ ] **Step 5: Add to `README.md`:** what the system does in one paragraph, a diagram in text of who can call what, the three commands, the configurations, the view-scope consequence from Task 4, and the note that production servers normally use the `mcp` package.
- [ ] **Step 6: Commit** with message `Run the questions through the system and report`.
- [ ] **Step 7: Run for real.** First `--only` two questions with `guarded` to check cost and time; tell the owner the projected total if it exceeds what they agreed in Task 1. Then all questions with `guarded` and `single`. Then `naive` on three questions only: it is expected to burn its budget.
- [ ] **Step 8: Read the transcripts** of every wrong and every stopped run before writing anything. Work out, for each, where it went wrong: search missed the dataset; the orchestrator chose badly; the task it wrote lost something from the question; the analyst's SQL; the data itself.
- [ ] **Step 9: Stop and report to the owner.** Lead with: how many answers were right, and how many were confidently wrong. Then: the causes from step 8, counted; what orchestration cost and bought against the single agent; what the naive configuration did; the `search-eval` result from Task 3 and whether it argues for embeddings; which failures would make good exercises, and which traps in the data caused them. Say what you did not run or could not check, including skipped PostgreSQL-only tests.

---

## Out of scope

Do not build these. They come after the owner has read the report.

- A verifier that checks an analyst's answer. Its inputs (the SQL, the caveats, the datasets) are already recorded.
- Planting traps in the data.
- Embedding search with the `vector` extension, unless the owner asks for it after seeing `search-eval`.
- Running analysts in parallel.
- Student-facing material: exercise stubs, a course module, a page on the site.
- A web interface or an HTTP transport for the servers.
- Connecting these servers to a commercial harness. They speak standard MCP over stdio, so it should work; it has not been tried.
