#!/usr/bin/env python3
"""practice-db: a minimal MCP server over stdio. Standard library only.

It exposes a small, read-only SQLite database of practice-app users through
three tools. It implements just enough of the Model Context Protocol to work
with an MCP client (a harness): initialize, tools/list, tools/call, ping.

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout. Anything written to
stdout must be protocol messages; diagnostics go to stderr.

Run it through the probe to watch the protocol:
    python3 mcp_probe.py

Production servers normally use an MCP SDK (for Python, the `mcp` package),
which handles the protocol details, validation, and newer protocol features.
This file exists so you can see that the protocol itself is small.
"""
import json
import sqlite3
import sys

SERVER_INFO = {"name": "practice-db", "version": "0.1.0"}
SUPPORTED_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
MAX_ROWS = 50

TOOLS = [
    {
        "name": "list_tables",
        "description": "List the tables in the practice-app database.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_table",
        "description": "Show the columns of one table.",
        "inputSchema": {"type": "object",
                        "properties": {"table": {"type": "string"}},
                        "required": ["table"]},
    },
    {
        "name": "run_select",
        "description": f"Run one read-only SELECT statement. Returns at most {MAX_ROWS} rows.",
        "inputSchema": {"type": "object",
                        "properties": {"sql": {"type": "string"}},
                        "required": ["sql"]},
    },
]


def make_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE users (name TEXT PRIMARY KEY, password_hash TEXT, created TEXT);
        CREATE TABLE login_events (ts TEXT, user TEXT, success INTEGER);
        INSERT INTO users VALUES
            ('alice', '3f1a…', '2026-01-04'),
            ('bob',   '9c2e…', '2026-02-11'),
            ('carol', '',      '2026-03-02'),
            ('dave',  '77ad…', '2026-03-15');
        INSERT INTO login_events VALUES
            ('2026-10-01T09:12', 'alice', 1),
            ('2026-10-01T09:40', 'carol', 1),
            ('2026-10-02T14:03', 'bob',   0),
            ('2026-10-02T14:04', 'bob',   1),
            ('2026-10-03T08:55', 'carol', 1);
    """)
    # Hard control inside the server: the connection itself refuses writes.
    db.execute("PRAGMA query_only = ON")
    return db


DB = make_db()


def text_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call_tool(name: str, args: dict) -> dict:
    if name == "list_tables":
        rows = DB.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return text_result("\n".join(r[0] for r in rows))
    if name == "describe_table":
        table = args.get("table", "")
        if not table.isidentifier():
            return text_result("Invalid table name.", True)
        rows = DB.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            return text_result(f"No table named {table}.", True)
        return text_result("\n".join(f"{r[1]} {r[2]}" for r in rows))
    if name == "run_select":
        sql = args.get("sql", "").strip().rstrip(";")
        if not sql.lower().startswith("select") or ";" in sql:
            return text_result("Only a single SELECT statement is allowed.", True)
        try:
            cur = DB.execute(sql)
        except sqlite3.Error as err:
            return text_result(f"SQL error: {err}", True)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        lines = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows[:MAX_ROWS]]
        if len(rows) > MAX_ROWS:
            lines.append(f"[truncated at {MAX_ROWS} rows]")
        return text_result("\n".join(lines))
    return text_result(f"Unknown tool: {name}", True)


def handle(msg: dict):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return {"protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
                "instructions": "Read-only access to the practice-app user database."}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return call_tool(params.get("name", ""), params.get("arguments") or {})
    raise LookupError(method)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "Parse error"}}
            print(json.dumps(reply), flush=True)
            continue
        if "id" not in msg:  # a notification, e.g. notifications/initialized
            print(f"[practice-db] notification: {msg.get('method')}", file=sys.stderr)
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except LookupError:
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32601, "message": f"Method not found: {msg.get('method')}"}}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
