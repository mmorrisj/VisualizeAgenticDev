"""Checks for summarize: key facts present, length limit, customer impact first.

Fact matching here is by pattern, a first pass. Phase L2 adds the judge, which
verifies each fact with a quote and counts claims the report does not support.
"""

import re

import yaml

from promptlab.checks import CheckResult, combine

WORD_LIMIT = 200
LEAD_WORDS = 40
IMPACT = re.compile(r"4,?300|12\s*%|12\s*per\s*cent", re.I)


def check(answer: str, task) -> CheckResult:
    text = answer.strip()
    facts = yaml.safe_load(task.read("hidden", "key-facts.yaml"))["facts"]
    found = [f["id"] for f in facts if any(re.search(p, text, re.I) for p in f["patterns"])]
    words = re.findall(r"\b[\w'%,.-]+\b", text)
    lead = " ".join(words[:LEAD_WORDS])
    parts = {
        "facts": len(found) / len(facts),
        "length": 1.0 if 0 < len(words) <= WORD_LIMIT else 0.0,
        "impact_first": 1.0 if IMPACT.search(lead) else 0.0,
    }
    details = {
        "parts": parts,
        "facts_found": found,
        "facts_missing": [f["id"] for f in facts if f["id"] not in found],
        "words": len(words),
        "word_limit": WORD_LIMIT,
        "unsupported_claims": "not checked until phase L2 (judge)",
    }
    return CheckResult(combine(parts, task.spec.weights), details, text)
