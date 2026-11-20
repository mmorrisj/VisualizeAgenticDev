"""Checks for data-question: the returned SQL runs and its result is the right number."""

import json
import sqlite3

from promptlab.checks import CheckResult
from promptlab.extract import extract

STEP_LIMIT = 2_000_000  # SQLite VM steps; stops runaway queries


def run_query(sql: str, task):
    db = sqlite3.connect(":memory:")
    db.executescript(task.read("input", "schema.sql") + task.read("input", "data.sql"))
    db.execute("PRAGMA query_only = ON")
    steps = {"n": 0}

    def guard():
        steps["n"] += 1
        return 1 if steps["n"] > STEP_LIMIT // 1000 else 0

    db.set_progress_handler(guard, 1000)
    try:
        row = db.execute(sql).fetchone()
    finally:
        db.close()
    return None if row is None else row[0]


def check(answer: str, task) -> CheckResult:
    expected = json.loads(task.read("hidden", "expected.json"))["value"]
    sql = extract(answer, "sql").strip().rstrip(";").strip()
    details = {"expected": expected, "sql_runs": False, "value": None}
    if ";" in sql:
        return CheckResult(0.0, details, sql, "more than one SQL statement")
    try:
        value = run_query(sql, task)
    except sqlite3.Error as err:
        return CheckResult(0.0, details, sql, f"SQL did not run: {err}")
    details.update(sql_runs=True, value=value)
    try:
        correct = value is not None and float(value) == float(expected)
    except (TypeError, ValueError):
        correct = False
    return CheckResult(1.0 if correct else 0.0, details, sql)
