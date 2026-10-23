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
ANATOMY_KEYS = {"id": str, "concept": str, "module_link": str, "tours": list,
                "components": list, "model": dict, "model_only": str, "intro": str, "bubble": dict}
TOUR_KEYS = {"id": str, "label": str, "intro": str, "phases": list, "steps": list}
# Must match COMPONENTS in assets/js/scene.js, which draws them.
HARNESS_COMPONENTS = {"instructions", "tools", "context", "permissions", "memory", "interface"}
COMPONENT_KEYS = {"id": str, "label": str, "example": str, "what": str, "why": str, "module_title": str, "module_link": str}
CONTENT_SCHEMAS = {
    "site.json": {"title": str, "description": str, "written_course_link": str, "sections": list},
    "anatomy.json": ANATOMY_KEYS,
    "loop.json": LOOP_KEYS,
    "context.json": {**SECTION_KEYS, "source_note": str, "replay": dict, "lab_a": dict, "simulator": dict},
    "tokens.json": {**SECTION_KEYS, "source_note": str, "compare": dict, "caching": dict},
    "extensions.json": {**SECTION_KEYS, "mechanisms": list, "attributes": list, "flow": dict, "scenarios": list,
                        "rules_of_thumb": list, "takeaway": str, "source_note": str},
    "quizzes.json": {"review": dict, "questions": list},
    "flows.json": {"id": str, "concept": str, "module_link": str, "source_note": str, "flows": list, "ui": dict},
    "inside-extensions.json": {"id": str, "concept": str, "module_link": str, "source_note": str, "task": str,
                               "lenses": list, "measured": dict, "session": dict, "ledger": dict},
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
            modules = data.get("curriculum", [])
            if len(modules) != 7:
                report.error(path, "curriculum must cover all seven written modules")
            if {module.get("id") for module in modules} != {f"module-{i}" for i in range(1, 8)}:
                report.error(path, "curriculum must identify modules 1 through 7 exactly once")
            ids = set()
            sections = {section["id"]: section for section in data.get("sections", [])}
            for i, module in enumerate(modules):
                check_keys(report, path, module, {key: str for key in (
                    "id", "title", "concept", "prompt", "lab", "coverage", "section",
                    "visual_link", "module_link", "visual_label", "lab_label"
                )}, f"curriculum[{i}]")
                if module.get("id") in ids:
                    report.error(path, "duplicate curriculum module id")
                ids.add(module.get("id"))
                section = sections.get(module.get("section"))
                if not section or urlsplit(module.get("visual_link", "")).path != section["page"]:
                    report.error(path, f"curriculum[{i}] must link to its declared visual section")
                for key in ("visual_link", "module_link"):
                    if not (SITE_ROOT / urlsplit(module.get(key, "")).path).is_file():
                        report.error(path, f"curriculum[{i}].{key} target is missing")
        for i, step in enumerate(data.get("steps", []) if isinstance(data, dict) else []):
            check_keys(report, path, step, STEP_KEYS, f"steps[{i}]")
        if path.name == "extensions.json" and isinstance(data, dict):
            check_extensions(report, path, data)
        if path.name == "tokens.json" and isinstance(data, dict):
            check_tokens(report, path, data)
        if path.name == "context.json" and isinstance(data, dict):
            check_context(report, path, data)
        if path.name == "anatomy.json" and isinstance(data, dict):
            check_anatomy(report, path, data)
        if path.name == "loop.json" and isinstance(data, dict):
            check_loop(report, path, data)
        if path.name == "inside-extensions.json" and isinstance(data, dict):
            check_inside_extensions(report, path, data)
        if path.name == "flows.json" and isinstance(data, dict):
            check_flows(report, path, data)
        if path.name == "quizzes.json" and isinstance(data, dict):
            check_quizzes(report, path, data)

        # Content links are relative to the site root. The written course may
        # live outside the site, so a missing target is a warning, not an error.
        for link in find_links(data):
            if is_relative_reference(link) and not (SITE_ROOT / urlsplit(link).path).resolve().exists():
                report.warn(path, f"link target not found (is course/ copied in?): {link}")


def check_flows(report: Report, path: pathlib.Path, data: dict) -> None:
    """The renderer and pure trace model require these lenses and controls."""
    controls = {
        "permissions": {"request", "hook", "deny", "ask", "allow", "approve", "sandbox"},
        "verification": {"change", "diff", "mutation"},
        "network": {"internal", "nonessential", "egress", "gateway", "endpoint", "transcript", "telemetry"},
    }
    nodes = {
        "permissions": {"request", "hook", "deny", "ask", "allow", "approval", "execution", "result", "return"},
        "verification": {"baseline", "red", "edit", "green", "diff", "mutation", "verdict", "return"},
        "network": {"files", "context", "gateway", "endpoint", "transcript", "telemetry", "public", "usage"},
    }
    flows = data.get("flows", [])
    if [flow.get("id") for flow in flows] != list(controls):
        report.error(path, "flows must list permissions, verification, and network exactly once in order")
    for flow in flows:
        fid = flow.get("id")
        check_keys(report, path, flow, {"id": str, "label": str, "concept": str, "intro": str,
                   "predict": str, "module_link": str, "source_note": str,
                   "defaults": list, "nodes": list, "messages": dict}, f"flow {fid}")
        defaults = flow.get("defaults", [])
        if {c.get("id") for c in defaults} != controls.get(fid) or len(defaults) != len(controls.get(fid, [])):
            report.error(path, f"flow {fid}: missing or duplicate controls")
        for control in defaults:
            check_keys(report, path, control, {"id": str, "label": str}, f"flow {fid} control")
            if "options" in control:
                values = [option.get("value") for option in control["options"]]
                if control.get("default") not in values or len(values) != len(set(values)):
                    report.error(path, f"flow {fid}: invalid select default or duplicate option")
            elif not isinstance(control.get("default"), bool):
                report.error(path, f"flow {fid}: toggle default must be boolean")
        scene_nodes = flow.get("nodes", [])
        if {n.get("id") for n in scene_nodes} != nodes.get(fid) or len(scene_nodes) != len(nodes.get(fid, [])):
            report.error(path, f"flow {fid}: missing or duplicate diagram nodes")
        for node in scene_nodes:
            check_keys(report, path, node, {"id": str, "label": str, "x": int, "y": int, "kind": str}, f"flow {fid} node")
            if not 82 <= node.get("x", 0) <= 938 or not 40 <= node.get("y", 0) <= 365:
                report.error(path, f"flow {fid}: node outside scene bounds")
        for key, message in flow.get("messages", {}).items():
            check_keys(report, path, message, {"title": str, "text": str, "evidence": str}, f"flow {fid} message {key}")


def check_quizzes(report: Report, path: pathlib.Path, data: dict) -> None:
    """Spec 6.6: 3 to 4 questions per section page, plus a review set drawn by id."""
    review = data.get("review")
    check_keys(report, path, review, {"concept": str, "module_link": str, "question_ids": list}, "review")
    questions = [q for q in data.get("questions", []) if isinstance(q, dict)]
    for i, q in enumerate(data.get("questions", [])):
        check_keys(report, path, q, QUESTION_KEYS, f"questions[{i}]")
        if not isinstance(q, dict) or not isinstance(q.get("choices"), list):
            continue
        choices = q["choices"]
        if len(choices) < 2 or not all(isinstance(c, str) and c.strip() for c in choices):
            report.error(path, f"questions[{i}].choices needs at least two non-empty strings")
        if len(set(choices)) != len(choices):
            report.error(path, f"questions[{i}].choices has duplicates")
        if isinstance(q.get("answer"), int) and not 0 <= q["answer"] < len(choices):
            report.error(path, f"questions[{i}].answer is out of range")

    # Test-wise students pick the longest answer. Keep that from being a reliable cue.
    sized = [q for q in questions if isinstance(q.get("choices"), list) and isinstance(q.get("answer"), int)
             and 0 <= q["answer"] < len(q["choices"]) and all(isinstance(c, str) for c in q["choices"])]
    longest = [q.get("id") for q in sized
               if len(q["choices"][q["answer"]]) > max(len(c) for i, c in enumerate(q["choices"]) if i != q["answer"])]
    if sized and len(longest) * 2 > len(sized):
        report.error(path, f"the correct choice is the longest in {len(longest)} of {len(sized)} questions; "
                     "make wrong choices as specific as the right one")

    ids = [q.get("id") for q in questions]
    for dup in sorted({i for i in ids if ids.count(i) > 1}, key=str):
        report.error(path, f"question id '{dup}' is used more than once")

    try:
        site = json.loads((path.parent / "site.json").read_text(encoding="utf-8"))
        sections = [s["id"] for s in site["sections"]]
    except (OSError, ValueError, KeyError, TypeError):
        return  # site.json problems are reported when site.json is checked
    for q in questions:
        if q.get("section") not in sections:
            report.error(path, f"question '{q.get('id')}' names unknown section '{q.get('section')}'")
    for section in sections:
        if section == "review":
            continue
        count = sum(q.get("section") == section for q in questions)
        if not 3 <= count <= 4:
            report.error(path, f"section '{section}' has {count} questions; the spec asks for 3 to 4")

    if isinstance(review, dict) and isinstance(review.get("question_ids"), list):
        known = set(ids)
        for qid in review["question_ids"]:
            if qid not in known:
                report.error(path, f"review.question_ids names unknown question '{qid}'")
        drawn = {q.get("section") for q in questions if q.get("id") in review["question_ids"]}
        missing = [s for s in sections if s != "review" and s not in drawn]
        if missing:
            report.error(path, f"review set has no question from: {', '.join(missing)}")


# Section 6.7. The ledger composition is shared with the measurement script,
# so the checker, the script, and the page agree on every total.
INSIDE_LENSES = ["mcp", "skill", "subagent", "plugin"]
INSIDE_MECHANISMS = ["mcp", "skill", "subagent"]
INSIDE_ROLES = CONTENT_ROLES | {"skill", "subagent"}
INSIDE_EFFECTS = {"none", "launch", "packet", "drop-in", "refuse", "unfold", "condense",
                  "split", "sub-grow", "collapse", "unpack", "fly", "hook-fire", "toggle-off"}
INSIDE_FOCUS = set(INSIDE_LENSES) | {"hook"}
PLACEHOLDER_RE = re.compile(r"\{([a-z_.]+)\}")


def check_inside_extensions(report: Report, path: pathlib.Path, data: dict) -> None:
    from itertools import combinations
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from measure_inside_extensions import compose

    session, measured = data.get("session", {}), data.get("measured", {})
    events = session.get("events", [])
    always = session.get("always", {})
    ids = [e.get("id") for e in events]
    for dup in sorted({i for i in ids if ids.count(i) > 1}, key=str):
        report.error(path, f"session event id '{dup}' is used more than once")
    whens = {None} | set(INSIDE_MECHANISMS) | {f"!{m}" for m in INSIDE_MECHANISMS}
    for where, item in [(f"event '{e.get('id')}'", e) for e in events] + \
                       [(f"always block '{k}'", b) for k, b in always.items()]:
        if item.get("role") not in INSIDE_ROLES:
            report.error(path, f"{where} has unknown role '{item.get('role')}'")
        if item.get("when") not in whens:
            report.error(path, f"{where} has unknown condition '{item.get('when')}'")
        if not isinstance(item.get("tokens"), int) or item["tokens"] < 0:
            report.error(path, f"{where} needs a non-negative integer token count")
    for e in events:
        if e.get("ctx") not in ("main", "sub"):
            report.error(path, f"event '{e.get('id')}' has ctx '{e.get('ctx')}', not main or sub")

    expected = data.get("ledger", {}).get("expected", {})
    for n in range(len(INSIDE_MECHANISMS) + 1):
        for combo in combinations(INSIDE_MECHANISMS, n):
            key = ",".join(combo) or "none"
            if key not in expected:
                report.error(path, f"ledger.expected is missing combination '{key}'")
            elif compose(session, set(combo)) != expected[key]:
                report.error(path, f"ledger.expected['{key}'] does not match the session's events; "
                             "re-run tools/measure_inside_extensions.py")

    triage = measured.get("triage", {})
    for kind in ("full", "condensed"):
        if len(triage.get(f"{kind}_text", "")) != triage.get(f"{kind}_chars"):
            report.error(path, f"measured.triage.{kind}_chars does not match its text")
    plugin_always = sum(always.get(k, {}).get("tokens", 0) for k in ("mcp-tools", "skill-listing", "agent-listing"))
    if measured.get("plugin", {}).get("always_tokens") != plugin_always:
        report.error(path, "measured.plugin.always_tokens is not the sum of the plugin's always-on blocks")

    lenses = data.get("lenses", [])
    if [lens.get("id") for lens in lenses] != INSIDE_LENSES:
        report.error(path, f"lenses must be, in order: {', '.join(INSIDE_LENSES)}")
    known_at = {"start"} | set(ids)
    focus_ok = INSIDE_FOCUS | set(ids) | set(always)
    wire_len = len(measured.get("wire", []))
    for lens in lenses:
        for i, step in enumerate(lens.get("steps", [])):
            where = f"lens '{lens.get('id')}' step {i + 1}"
            check_keys(report, path, step, {"text": str, "state": dict}, where)
            state = step.get("state", {})
            if state.get("at") not in known_at:
                report.error(path, f"{where}: state.at '{state.get('at')}' is not an event id")
            if state.get("focus") not in focus_ok:
                report.error(path, f"{where}: unknown focus '{state.get('focus')}'")
            if state.get("effect") not in INSIDE_EFFECTS:
                report.error(path, f"{where}: unknown effect '{state.get('effect')}'")
            if not set(state.get("combo", [])) <= set(INSIDE_MECHANISMS):
                report.error(path, f"{where}: combo names an unknown mechanism")
            for w in step.get("wire", []):
                if not isinstance(w, int) or not 0 <= w < wire_len:
                    report.error(path, f"{where}: wire index {w} is out of range")
            for ref in PLACEHOLDER_RE.findall(step.get("text", "")):
                value = data
                for part in ref.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if not isinstance(value, (int, float)):
                    report.error(path, f"{where}: placeholder {{{ref}}} does not resolve to a number")


def check_extensions(report: Report, path: pathlib.Path, data: dict) -> None:
    """The decision flow must be a tree whose every path ends at a result,
    and every result and scenario must name a known mechanism."""
    mechanisms = {m.get("id") for m in data.get("mechanisms", []) if isinstance(m, dict)}
    attributes = [a.get("id") for a in data.get("attributes", []) if isinstance(a, dict)]
    for i, m in enumerate(data.get("mechanisms", [])):
        check_keys(report, path, m, {"id": str, "label": str, "short": str, **{a: str for a in attributes}}, f"mechanisms[{i}]")
    flow = data.get("flow", {})
    nodes = {n.get("id"): n for n in flow.get("nodes", []) if isinstance(n, dict)}
    for nid, n in nodes.items():
        check_keys(report, path, n, {"type": str, "label": str, "x": int, "y": int}, f"flow node {nid}")
        if n.get("type") == "question":
            for answer in ("yes", "no"):
                if n.get(answer) not in nodes:
                    report.error(path, f"flow node {nid}: '{answer}' points to unknown node {n.get(answer)!r}")
        elif n.get("mechanism") not in mechanisms:
            report.error(path, f"flow node {nid}: unknown mechanism {n.get('mechanism')!r}")

    # Walk every path from the start; each must end at a result without looping.
    def walk(nid, seen):
        if nid not in nodes:
            return
        if nid in seen:
            report.error(path, f"flow loops back to {nid}")
            return
        n = nodes[nid]
        if n.get("type") == "question":
            for answer in ("yes", "no"):
                walk(n.get(answer), seen | {nid})
        elif n.get("type") != "result":
            report.error(path, f"flow node {nid} is neither a question nor a result")
    walk(flow.get("start"), frozenset())
    if flow.get("share_yes", {}).get("mechanism") not in mechanisms:
        report.error(path, "flow.share_yes must name a known mechanism")
    for i, sc in enumerate(data.get("scenarios", [])):
        check_keys(report, path, sc, {"id": str, "text": str, "answer": list, "explanation": str}, f"scenarios[{i}]")
        unknown = set(sc.get("answer", [])) - mechanisms if isinstance(sc, dict) else set()
        if unknown:
            report.error(path, f"scenarios[{i}].answer names unknown mechanisms {sorted(unknown)}")


def check_tokens(report: Report, path: pathlib.Path, data: dict) -> None:
    """Sessions need numbered requests with positive sizes; cached tokens can
    never exceed a request's size."""
    sessions = data.get("compare", {}).get("sessions", [])
    if len(sessions) != 2:
        report.error(path, "compare.sessions must hold exactly two sessions (focused and broad)")
    for s, session in enumerate(sessions):
        check_keys(report, path, session, {"id": str, "label": str, "prompt": str, "requests": list}, f"compare.sessions[{s}]")
        for i, req in enumerate(session.get("requests", []) if isinstance(session, dict) else []):
            check_keys(report, path, req, {"n": int, "tokens": int, "call": str}, f"compare.sessions[{s}].requests[{i}]")
            if isinstance(req, dict) and (req.get("n") != i + 1 or not req.get("tokens", 0) > 0):
                report.error(path, f"compare.sessions[{s}].requests[{i}] must be numbered {i + 1} with a positive size")
    caching = data.get("caching", {})
    check_keys(report, path, caching, {"title": str, "intro": str, "requests": list, "miss_note": str}, "caching")
    for i, req in enumerate(caching.get("requests", [])):
        check_keys(report, path, req, {"n": int, "tokens": int, "cached": int}, f"caching.requests[{i}]")
        if isinstance(req, dict) and not 0 <= req.get("cached", 0) <= req.get("tokens", 0):
            report.error(path, f"caching.requests[{i}].cached must be between 0 and the request's size")


def check_context(report: Report, path: pathlib.Path, data: dict) -> None:
    """Replay parts must add up to each request's measured size; simulator
    defaults and presets must sit inside their slider ranges."""
    replay = data.get("replay", {})
    check_keys(report, path, replay, {"title": str, "intro": str, "limit": int, "threshold": float, "requests": list}, "replay")
    for i, req in enumerate(replay.get("requests", [])):
        check_keys(report, path, req, {"n": int, "reported": int, "parts": dict, "results": list, "caption": str}, f"replay.requests[{i}]")
        if not isinstance(req, dict) or not isinstance(req.get("parts"), dict):
            continue
        parts = sum(v for v in req["parts"].values() if isinstance(v, int))
        results = sum(r.get("tokens", 0) for r in req.get("results", []) if isinstance(r, dict))
        if parts + results != req.get("reported"):
            report.error(path, f"replay.requests[{i}]: parts and results sum to {parts + results}, not {req.get('reported')}")
    sim = data.get("simulator", {})
    check_keys(report, path, sim, {"title": str, "intro": str, "ranges": dict, "defaults": dict, "presets": list, "limits": list,
                                   "system_tokens": int, "tokens_per_tool": int, "user_message_tokens": int,
                                   "model_message_tokens": int, "stub_tokens": int, "keep_recent_results": int,
                                   "result_pattern": list}, "simulator")
    ranges = sim.get("ranges", {}) if isinstance(sim.get("ranges"), dict) else {}
    named = [("defaults", sim.get("defaults", {}))] + [(f"presets[{i}]", p.get("values", {})) for i, p in enumerate(sim.get("presets", [])) if isinstance(p, dict)]
    for where, values in named:
        for key, value in values.items():
            lo_hi = ranges.get(key)
            if lo_hi and not lo_hi[0] <= value <= lo_hi[1]:
                report.error(path, f"simulator.{where}.{key} = {value} is outside its range {lo_hi[:2]}")
    if sim.get("defaults", {}).get("limit") not in sim.get("limits", []):
        report.error(path, "simulator.defaults.limit must be one of simulator.limits")
    pattern = sim.get("result_pattern", [])
    if pattern and abs(sum(pattern) / len(pattern) - 1) > 0.01:
        report.error(path, "simulator.result_pattern must average 1.0, so the average-result control is accurate")


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
    tour_ids = set()
    for t, tour in enumerate(data.get("tours", [])):
        check_keys(report, path, tour, TOUR_KEYS, f"tours[{t}]")
        if not isinstance(tour, dict):
            continue
        if tour.get("id") in tour_ids:
            report.error(path, f"tours[{t}].id '{tour.get('id')}' is used twice")
        tour_ids.add(tour.get("id"))
        check_tour(report, path, tour, f"tours[{t}]")
    if not tour_ids:
        report.error(path, "tours must list at least one tour")


def check_tour(report: Report, path: pathlib.Path, tour: dict, where: str) -> None:
    """Tour stops: each names where the line goes, and optionally where it
    passes on the way, which phase it belongs to, and any request it sends."""
    places = HARNESS_COMPONENTS | {"you", "model", "world"}
    phases = {ph.get("id") for ph in tour.get("phases", []) if isinstance(ph, dict)}
    if not phases:
        report.error(path, f"{where}.phases must list at least one {{id, label}}")
    last_request = 0
    for i, step in enumerate(tour.get("steps", [])):
        check_keys(report, path, step, STEP_KEYS, f"{where}.steps[{i}]")
        state = step.get("state", {}) if isinstance(step, dict) else {}
        if state.get("phase") not in phases:
            report.error(path, f"{where}.steps[{i}].state.phase must be one of {sorted(phases)}")
        if "wire" in state and not isinstance(state["wire"], str):
            report.error(path, f"{where}.steps[{i}].state.wire must be text")
        if "request" in state:
            check_keys(report, path, state["request"], {"number": int, "tokens": int}, f"{where}.steps[{i}].state.request")
            number = state["request"].get("number") if isinstance(state["request"], dict) else None
            if isinstance(number, int):
                if number != last_request + 1:
                    report.error(path, f"{where}.steps[{i}].state.request.number should be {last_request + 1}")
                last_request = number
        if state.get("target") not in places:
            report.error(path, f"{where}.steps[{i}].state.target must be one of {sorted(places)}")
        if not isinstance(state.get("title"), str):
            report.error(path, f"{where}.steps[{i}].state.title is required")
        unknown = set(state.get("via", [])) - places
        if unknown:
            report.error(path, f"{where}.steps[{i}].state.via names unknown places {sorted(unknown)}")


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
