"""Every check passes its known-good answers and fails its known-bad ones (spec phase L1)."""

import pytest

from promptlab.extract import extract
from promptlab.tasks import load_task, task_ids

CASES = [(tid, name) for tid in task_ids() for name in load_task(tid).answers()]


@pytest.mark.parametrize("task_id,answer", CASES)
def test_known_answers(task_id, answer):
    task = load_task(task_id)
    result = task.check(task.answer(answer))
    if answer.startswith("good"):
        assert result.passed, result.details
    else:
        assert not result.passed, result.details


def test_every_task_has_good_and_bad_answers_and_the_four_variants():
    for tid in task_ids():
        task = load_task(tid)
        names = task.answers()
        assert any(n.startswith("good") for n in names) and any(n.startswith("bad") for n in names)
        assert {"terse", "technique", "informed", "full"} <= set(task.variants())


def test_every_task_has_both_kinds_of_fact():
    for tid in task_ids():
        kinds = {f.kind for f in load_task(tid).spec.facts}
        assert kinds == {"discoverable", "private"}, tid


def test_refactor_unchanged_module_fails_only_on_changed():
    result = load_task("refactor").check(load_task("refactor").answer("bad-unchanged"))
    assert result.details["parts"] == {"hidden_tests": 1.0, "signatures": 1.0, "stdlib_only": 1.0, "changed": 0.0}


def test_refactor_unparseable_scores_zero():
    result = load_task("refactor").check("```python\ndef broken(:\n```")
    assert result.score == 0 and "parse" in result.error


def test_data_question_rejects_multiple_statements():
    result = load_task("data-question").check("```sql\nSELECT 8; DROP TABLE incidents;\n```")
    assert result.score == 0 and "more than one" in result.error


def test_data_question_query_only():
    result = load_task("data-question").check("```sql\nDELETE FROM incidents\n```")
    assert result.score == 0 and not result.details["sql_runs"]


def test_summarize_word_limit():
    task = load_task("summarize")
    long = task.answer("good") + " extra" * 200
    assert task.check(long).details["parts"]["length"] == 0.0


def test_write_tests_infinite_loop_is_contained():
    loop = "```python\ndef test_forever():\n    while True:\n        pass\n```"
    result = load_task("write-tests").check(loop)
    assert result.score == 0


@pytest.mark.parametrize("text,lang,expected", [
    ("prose\n```python\nx = 1\n```\nmore", "python", "x = 1\n"),
    ("```\nSELECT 1\n```", "sql", "SELECT 1\n"),
    ("```py\na\n```\n```python\nlonger = 2\n```", "python", "longer = 2\n"),
    ("SELECT 2", "sql", "SELECT 2\n"),
    ("```sql\nSELECT 1\n```\n```python\nprint(1)\n```", "sql", "SELECT 1\n"),
])
def test_extract(text, lang, expected):
    assert extract(text, lang) == expected
