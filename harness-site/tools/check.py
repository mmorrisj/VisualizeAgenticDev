#!/usr/bin/env python3
"""Offline quality checks for the site (spec section 8).

Standard library only. Exits non-zero if any check fails.

    python3 tools/check.py

Checks:
  1. Every content/*.json parses and has its required keys.
  2. Every relative link and asset reference in HTML points to a file.
  3. No absolute http(s) URLs in HTML, CSS, JS, or JSON, except the XML
     namespace URIs needed to build SVG from JavaScript.
  4. No emoji or pictographic characters, and no use of the word
     "beginner", in any site file.
  5. Every <img> has alt; every inline <svg> is labelled or decorative;
     every <button> has a text label.
  6. Every relative JS import points to a file.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlsplit

SITE_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".html", ".css", ".js", ".json", ".md"}
SKIP_DIRS = {"tools", ".git", "node_modules"}

# Identifiers, not network addresses: needed for document.createElementNS.
ALLOWED_URLS = {
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/1999/xhtml",
}
URL_RE = re.compile(r"https?://[^\s\"'`)<>]+")

# unicodedata has no emoji property, so list the ranges explicitly.
PICTOGRAPHIC_RANGES = [
    (0x2190, 0x21FF),    # arrows
    (0x2300, 0x23FF),    # miscellaneous technical (watch, hourglass, ...)
    (0x2460, 0x24FF),    # enclosed alphanumerics
    (0x25A0, 0x25FF),    # geometric shapes
    (0x2600, 0x27BF),    # miscellaneous symbols, dingbats
    (0x2900, 0x297F),    # supplemental arrows-B
    (0x2B00, 0x2BFF),    # miscellaneous symbols and arrows
    (0x3030, 0x3030),    # wavy dash
    (0x303D, 0x303D),    # part alternation mark
    (0x3297, 0x3299),    # circled ideographs
    (0xFE0F, 0xFE0F),    # variation selector 16 (emoji presentation)
    (0x200D, 0x200D),    # zero-width joiner (emoji sequences)
    (0x1F000, 0x1FAFF),  # mahjong through symbols and pictographs extended-A
    (0xE0020, 0xE007F),  # tag characters (flag sequences)
]
BANNED_WORD_RE = re.compile(r"beginner", re.IGNORECASE)

# Required keys per content file. Extend as phases add content.
SECTION_KEYS = {"id": str, "concept": str, "module_link": str, "steps": list}
LOOP_KEYS = {**SECTION_KEYS, "tokens_per_block": int, "fixed": list, "session": list, "predict": dict}
ANATOMY_KEYS = {**SECTION_KEYS, "components": list, "model": dict, "model_only": str, "intro": str, "bubble": dict,
                "phases": list, "tour_intro": str}
# Must match COMPONENTS in assets/js/scene.js, which draws them.
HARNESS_COMPONENTS = {"instructions", "tools", "context", "permissions", "memory", "interface"}
COMPONENT_KEYS = {"id": str, "label": str, "example": str, "what": str, "why": str, "module_title": str, "module_link": str}
CONTENT_SCHEMAS = {
    "site.json": {"title": str, "description": str, "written_course_link": str, "sections": list},
    "anatomy.json": ANATOMY_KEYS,
    "loop.json": LOOP_KEYS,
    "context.json": SECTION_KEYS,
    "tokens.json": SECTION_KEYS,
    "extensions.json": SECTION_KEYS,
    "quizzes.json": {"review": dict, "questions": list},
}
SITE_SECTION_KEYS = {"id": str, "page": str, "title": str, "summary": str}
STEP_KEYS = {"text": str, "state": dict}
LOOP_ITEM_KEYS = {"id": str, "role": str, "label": str, "tokens": int}
LOOP_STAGES = {"ask", "decide", "run", "return", "answer"}
CONTENT_ROLES = {"system", "tools", "instructions", "user", "model", "result", "summary"}
QUESTION_KEYS = {"id": str, "section": str, "prompt": str, "choices": list, "answer": int, "explanation": str}

IMPORT_RE = re.compile(r"""(?:import|export)\s[^'"`;]*?from\s*["']([^"']+)["']|import\s*\(\s*["']([^"']+)["']\s*\)""")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: pathlib.Path | str, message: str) -> None:
        self.errors.append(f"{rel(where)}: {message}")

    def warn(self, where: pathlib.Path | str, message: str) -> None:
        self.warnings.append(f"{rel(where)}: {message}")


def rel(path: pathlib.Path | str) -> str:
    if isinstance(path, pathlib.Path):
        try:
            return str(path.relative_to(SITE_ROOT))
        except ValueError:
            return str(path)
    return path


def site_files(suffixes: set[str]) -> list[pathlib.Path]:
    files = []
    for path in sorted(SITE_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(SITE_ROOT).parts):
            continue
        files.append(path)
    return files


def is_relative_reference(ref: str) -> bool:
    """True for paths we should resolve on disk (not anchors, data:, mailto:, ...)."""
    if not ref or ref.startswith(("#", "data:", "mailto:", "javascript:")):
        return False
    parts = urlsplit(ref)
    return not parts.scheme and not parts.netloc


def resolve(base: pathlib.Path, ref: str) -> pathlib.Path:
    path = urlsplit(ref).path
    return (base.parent / path).resolve()


# 1. Content ---------------------------------------------------------------


def check_keys(report: Report, path: pathlib.Path, obj: object, schema: dict, where: str) -> None:
    if not isinstance(obj, dict):
        report.error(path, f"{where} must be an object")
        return
    for key, kind in schema.items():
        if key not in obj:
            report.error(path, f"{where} is missing required key '{key}'")
        elif not isinstance(obj[key], kind) or (kind is int and isinstance(obj[key], bool)):
            report.error(path, f"{where}.{key} must be {kind.__name__}")


def check_content(report: Report) -> None:
    content_dir = SITE_ROOT / "content"
    for name in CONTENT_SCHEMAS:
        if not (content_dir / name).exists():
            report.error(content_dir / name, "required content file is missing")

    for path in sorted(content_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.error(path, f"invalid JSON: {exc}")
            continue

        schema = CONTENT_SCHEMAS.get(path.name)
        if schema is None:
            report.warn(path, "no schema defined in check.py; keys not validated")
            continue
        check_keys(report, path, data, schema, "root")

        if path.name == "site.json":
            for i, section in enumerate(data.get("sections", [])):
                check_keys(report, path, section, SITE_SECTION_KEYS, f"sections[{i}]")
                page = section.get("page", "")
                if isinstance(page, str) and not (SITE_ROOT / page).is_file():
                    report.error(path, f"sections[{i}].page '{page}' does not exist")
        for i, step in enumerate(data.get("steps", []) if isinstance(data, dict) else []):
            check_keys(report, path, step, STEP_KEYS, f"steps[{i}]")
        if path.name == "anatomy.json" and isinstance(data, dict):
            check_anatomy(report, path, data)
        if path.name == "loop.json" and isinstance(data, dict):
            check_loop(report, path, data)
        if path.name == "quizzes.json":
            check_keys(report, path, data.get("review"), {"concept": str, "module_link": str}, "review")
            for i, q in enumerate(data.get("questions", [])):
                check_keys(report, path, q, QUESTION_KEYS, f"questions[{i}]")
                if isinstance(q, dict) and isinstance(q.get("choices"), list) and isinstance(q.get("answer"), int):
                    if not 0 <= q["answer"] < len(q["choices"]):
                        report.error(path, f"questions[{i}].answer is out of range")

        # Content links are relative to the site root. The written course may
        # live outside the site, so a missing target is a warning, not an error.
        for link in find_links(data):
            if is_relative_reference(link) and not (SITE_ROOT / urlsplit(link).path).resolve().exists():
                report.warn(path, f"link target not found (is course/ copied in?): {link}")


def check_anatomy(report: Report, path: pathlib.Path, data: dict) -> None:
    """Exactly the six components the scene draws, and steps that name them."""
    ids = []
    for i, comp in enumerate(data.get("components", [])):
        check_keys(report, path, comp, COMPONENT_KEYS, f"components[{i}]")
        if isinstance(comp, dict):
            ids.append(comp.get("id"))
    if sorted(ids) != sorted(HARNESS_COMPONENTS):
        report.error(path, f"components must be exactly {sorted(HARNESS_COMPONENTS)}, found {ids}")
    check_keys(report, path, data.get("model"), {"label": str, "what": str, "why": str}, "model")
    check_keys(report, path, data.get("bubble"), {"text": str, "caption": str}, "bubble")
    # Tour stops: each names where the line goes, and optionally where it
    # passes on the way.
    places = HARNESS_COMPONENTS | {"you", "model", "world"}
    phases = {ph.get("id") for ph in data.get("phases", []) if isinstance(ph, dict)}
    if not phases:
        report.error(path, "phases must list at least one {id, label}")
    last_request = 0
    for i, step in enumerate(data.get("steps", [])):
        state = step.get("state", {}) if isinstance(step, dict) else {}
        if state.get("phase") not in phases:
            report.error(path, f"steps[{i}].state.phase must be one of {sorted(phases)}")
        if "wire" in state and not isinstance(state["wire"], str):
            report.error(path, f"steps[{i}].state.wire must be text")
        if "request" in state:
            check_keys(report, path, state["request"], {"number": int, "tokens": int}, f"steps[{i}].state.request")
            number = state["request"].get("number") if isinstance(state["request"], dict) else None
            if isinstance(number, int):
                if number != last_request + 1:
                    report.error(path, f"steps[{i}].state.request.number should be {last_request + 1}")
                last_request = number
        if state.get("target") not in places:
            report.error(path, f"steps[{i}].state.target must be one of {sorted(places)}")
        if not isinstance(state.get("title"), str):
            report.error(path, f"steps[{i}].state.title is required")
        unknown = set(state.get("via", [])) - places
        if unknown:
            report.error(path, f"steps[{i}].state.via names unknown places {sorted(unknown)}")


def check_loop(report: Report, path: pathlib.Path, data: dict) -> None:
    """Loop session: valid stages and items, and steps that point at real events."""
    items = list(data.get("fixed", []))
    for i, event in enumerate(data.get("session", [])):
        if not isinstance(event, dict) or event.get("stage") not in LOOP_STAGES:
            report.error(path, f"session[{i}].stage must be one of {sorted(LOOP_STAGES)}")
            continue
        if not isinstance(event.get("explain"), str):
            report.error(path, f"session[{i}] is missing 'explain' text")
        if "item" in event:
            items.append(event["item"])
    ids = set()
    for i, item in enumerate(items):
        check_keys(report, path, item, LOOP_ITEM_KEYS, f"item {i}")
        if isinstance(item, dict):
            if item.get("role") not in CONTENT_ROLES:
                report.error(path, f"item {i} has unknown role '{item.get('role')}'")
            ids.add(item.get("id"))
    for i, event in enumerate(data.get("session", [])):
        if isinstance(event, dict) and "stale" in event and event["stale"] not in ids:
            report.error(path, f"session[{i}].stale points to unknown item '{event['stale']}'")
    count = len(data.get("session", []))
    for i, step in enumerate(data.get("steps", [])):
        target = step.get("state", {}).get("session_step") if isinstance(step, dict) else None
        if not isinstance(target, int) or not 0 <= target < count:
            report.error(path, f"steps[{i}].state.session_step must index the session (0 to {count - 1})")
    check_keys(report, path, data.get("predict"), {"question": str, "choices": list, "reveal": str}, "predict")


def find_links(obj: object) -> list[str]:
    """Values of keys ending in 'link' or named 'page', anywhere in the JSON."""
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and (key.endswith("link") or key == "page"):
                found.append(value)
            else:
                found.extend(find_links(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(find_links(item))
    return found


# 2 and 5. HTML references and accessibility ---------------------------------


class PageParser(HTMLParser):
    """Collects references, and checks img/svg/button labelling."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[int, str]] = []
        self.problems: list[tuple[int, str]] = []
        self.ids: set[str] = set()
        self.labelledby: list[tuple[int, str]] = []
        self._button: dict | None = None
        self._svg_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        line = self.getpos()[0]
        if "id" in a:
            self.ids.add(a["id"])

        for key in ("href", "src"):
            if key in a and tag not in {"svg"} and self._svg_depth == 0:
                self.refs.append((line, a[key]))

        if tag == "img" and "alt" not in a:
            self.problems.append((line, "<img> has no alt attribute"))

        if tag == "svg":
            if self._svg_depth == 0:
                decorative = a.get("aria-hidden") == "true"
                labelled = a.get("role") == "img" and (a.get("aria-label") or a.get("aria-labelledby"))
                if not (decorative or labelled):
                    self.problems.append((line, '<svg> needs role="img" with an accessible name, or aria-hidden="true"'))
                if a.get("aria-labelledby"):
                    self.labelledby.append((line, a["aria-labelledby"]))
            self._svg_depth += 1

        if tag == "button":
            self._button = {"line": line, "label": a.get("aria-label", "").strip(), "text": ""}

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg" and self._svg_depth:
            self._svg_depth -= 1
        if tag == "button" and self._button is not None:
            if not (self._button["label"] or self._button["text"].strip()):
                self.problems.append((self._button["line"], "<button> has no text label"))
            self._button = None

    def handle_data(self, data: str) -> None:
        if self._button is not None and self._svg_depth == 0:
            self._button["text"] += data


def check_html(report: Report) -> None:
    for path in site_files({".html"}):
        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8"))
        for line, ref in parser.refs:
            if is_relative_reference(ref) and not resolve(path, ref).exists():
                report.error(path, f"line {line}: broken reference '{ref}'")
            if ref.startswith("/") and not ref.startswith("//"):
                report.error(path, f"line {line}: root-absolute path '{ref}' breaks subpath hosting")
        for line, problem in parser.problems:
            report.error(path, f"line {line}: {problem}")
        for line, ids in parser.labelledby:
            for ref_id in ids.split():
                if ref_id not in parser.ids:
                    report.error(path, f"line {line}: aria-labelledby points to missing id '{ref_id}'")


# 3. Absolute URLs ------------------------------------------------------------


def check_urls(report: Report) -> None:
    for path in site_files({".html", ".css", ".js", ".json"}):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for url in URL_RE.findall(line):
                if url.rstrip(".,;") not in ALLOWED_URLS:
                    report.error(path, f"line {number}: absolute URL not allowed offline: {url}")


# 4. Emoji and banned words ---------------------------------------------------


def is_pictographic(char: str) -> bool:
    code = ord(char)
    return any(lo <= code <= hi for lo, hi in PICTOGRAPHIC_RANGES)


def check_characters(report: Report) -> None:
    for path in site_files(TEXT_SUFFIXES):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            bad = sorted({f"U+{ord(c):04X}" for c in line if is_pictographic(c)})
            if bad:
                report.error(path, f"line {number}: pictographic characters {', '.join(bad)}")
            if BANNED_WORD_RE.search(line):
                report.error(path, f"line {number}: uses the word 'beginner'")


# 6. JS imports ----------------------------------------------------------------


def check_imports(report: Report) -> None:
    sources: list[tuple[pathlib.Path, str]] = []
    for path in site_files({".js"}):
        sources.append((path, path.read_text(encoding="utf-8")))
    # Inline module scripts in HTML import relative to the page.
    for path in site_files({".html"}):
        sources.append((path, path.read_text(encoding="utf-8")))

    for path, source in sources:
        for match in IMPORT_RE.finditer(source):
            spec = match.group(1) or match.group(2)
            if spec.startswith((".", "/")) and not resolve(path, spec).is_file():
                line = source.count("\n", 0, match.start()) + 1
                report.error(path, f"line {line}: import target not found '{spec}'")


# Main --------------------------------------------------------------------------


def main() -> int:
    report = Report()
    checks = [
        ("content JSON", check_content),
        ("HTML references and accessibility", check_html),
        ("absolute URLs", check_urls),
        ("characters and wording", check_characters),
        ("JS imports", check_imports),
    ]
    for name, check in checks:
        before = len(report.errors)
        check(report)
        status = "ok" if len(report.errors) == before else f"{len(report.errors) - before} problem(s)"
        print(f"  {name:<36} {status}")

    for warning in report.warnings:
        print(f"WARN  {warning}")
    for error in report.errors:
        print(f"FAIL  {error}")

    if report.errors:
        print(f"\ncheck.py: {len(report.errors)} problem(s) found.")
        return 1
    print(f"\ncheck.py: all checks passed ({len(report.warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
