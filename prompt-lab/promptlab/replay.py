"""Replay mode for the class kit (spec section 10.2): recorded runs instead of a gateway.

If the gateway is slow or down, the class kit serves the study's recorded runs
for the reference prompts, labelled "recorded". Nothing is sent to any model,
and a student's own prompt cannot run: the page says so.

Replay works at the level of whole runs, so harness sessions replay too.
"""

from __future__ import annotations

import json
from pathlib import Path

from .store import Run


class Recorded:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.document = json.loads(self.path.read_text(encoding="utf-8"))
        self._by_key: dict[tuple, dict] = {}
        self._by_cell: dict[tuple, list[dict]] = {}
        for record in self.document.get("runs", []):
            if record.get("status") == "error":
                continue
            cell = (record["mode"], record["task"], record["variant"], record["model"])
            self._by_key[cell + (record["repeat"],)] = record
            self._by_cell.setdefault(cell, []).append(record)

    @property
    def synthetic(self) -> bool:
        return bool(self.document.get("synthetic"))

    def has(self, mode: str, task: str, variant: str, model: str) -> bool:
        return (mode, task, variant, model) in self._by_cell

    def record(self, mode: str, task: str, variant: str, model: str, repeat: int) -> dict | None:
        """The recorded run with that repeat number, else one of the same cell in turn."""
        exact = self._by_key.get((mode, task, variant, model, repeat))
        if exact:
            return exact
        cell = self._by_cell.get((mode, task, variant, model))
        return cell[(repeat - 1) % len(cell)] if cell else None

    def run(self, mode: str, task: str, variant: str, model: str, repeat: int, profile: str) -> Run | None:
        record = self.record(mode, task, variant, model, repeat)
        if record is None:
            return None
        output = ""
        if record.get("output_ref"):
            path = self.path.parent / record["output_ref"]
            output = path.read_text(encoding="utf-8") if path.is_file() else ""
        chars = record.get("chars") or {}
        return Run(profile=profile, mode=mode, task=task, variant=variant, model=model, repeat=repeat,
                   status=record["status"], score=record["checks"]["score"], label="recorded",
                   check_details={"details": record["checks"].get("details", {}),
                                  "recorded_from": f"{self.path.name}#{record['id']}"},
                   tokens=record.get("tokens") or {}, chars_sent=chars.get("sent", 0),
                   chars_received=chars.get("received", 0), requests=record.get("requests", 1),
                   stop=record.get("stop", ""), latency_s=0.0, output=output, session=record.get("session") or {})
