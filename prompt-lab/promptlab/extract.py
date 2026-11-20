"""Pull the artifact (code, SQL, tests) out of a model's answer.

Models wrap code in Markdown fences, add prose, or sometimes return bare code.
The rules, in order:
1. Fenced blocks tagged with the wanted language; if several, the longest.
2. Otherwise any fenced block; the longest.
3. Otherwise the whole answer, stripped.
"""

from __future__ import annotations

import re

FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", re.S)

ALIASES = {"python": {"python", "py", "python3"}, "sql": {"sql", "sqlite"}}


def fenced_blocks(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).lower(), m.group(2)) for m in FENCE.finditer(text)]


def extract(text: str, language: str) -> str:
    blocks = fenced_blocks(text)
    wanted = [body for lang, body in blocks if lang in ALIASES.get(language, {language})]
    pool = wanted or [body for _, body in blocks]
    if pool:
        return max(pool, key=len).strip() + "\n"
    return text.strip() + "\n"
