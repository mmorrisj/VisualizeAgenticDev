"""App settings, from the environment only (spec section 11.4): nothing secret in the repository.

| Variable | Default | Meaning |
|---|---|---|
| PROMPTLAB_DB_URL | data/lab.db | Database URL (SQLite file or Postgres) |
| PROMPTLAB_MODELS | config/models.yaml | Models file |
| PROMPTLAB_CLASS_PROFILE | class | Profile for the class kit (class-mock: mock models) |
| PROMPTLAB_JUDGE | the study profile's primary judge | Judge for bring-your-own tests |
| PROMPTLAB_BYOT_MODELS | the study profile's models | Models a student may choose for their own test |
| PROMPTLAB_REPLAY | off | 1 for the newest results/study-*.json, or a results file path |
| PROMPTLAB_STUDY_RESULTS | newest results/study-*.json | The study drawn under students' points |
| PROMPTLAB_RETENTION_DAYS | 30 | Days before part C tests and their runs are deleted |
| PROMPTLAB_ALLOW_COMMAND_CHECKS | 0 | 1 lets students attach shell-command checks; they run on this server |
| PROMPTLAB_COLLECTOR | 0 | 1 turns on /collect and the projector chart |
| PROMPTLAB_COLLECTOR_URL | none | Where "submit" sends a class results file, if not this app |
| PROMPTLAB_CONCURRENCY | 2 | Requests at once per student |

Model endpoints and keys come from the variables named in models.yaml, as for the command line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..profiles import load_profile
from ..study import RESULTS_DIR, newest_results


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    db_url: str | None = None
    models_path: Path | None = None
    class_profile: str = "class"
    judge: str | None = None
    byot_models: list[str] = field(default_factory=list)
    replay: Path | None = None
    study_results: Path | None = None
    retention_days: int = 30
    allow_command_checks: bool = False
    collector: bool = False
    collector_url: str | None = None
    concurrency: int = 2
    inline_jobs: bool = False  # tests: run jobs before the response returns

    @classmethod
    def from_env(cls) -> Settings:
        study = load_profile("study")
        replay_value = os.environ.get("PROMPTLAB_REPLAY", "").strip()
        replay = None
        if replay_value.lower() in {"1", "true", "yes", "on"}:
            replay = newest_results("study", RESULTS_DIR)
            if replay is None:
                raise SystemExit("PROMPTLAB_REPLAY is on, but there is no results/study-*.json to replay")
        elif replay_value and replay_value.lower() not in {"0", "false", "no", "off"}:
            replay = Path(replay_value)
        results = os.environ.get("PROMPTLAB_STUDY_RESULTS")
        return cls(
            db_url=os.environ.get("PROMPTLAB_DB_URL") or None,
            models_path=Path(os.environ["PROMPTLAB_MODELS"]) if os.environ.get("PROMPTLAB_MODELS") else None,
            class_profile=os.environ.get("PROMPTLAB_CLASS_PROFILE", "class"),
            judge=os.environ.get("PROMPTLAB_JUDGE") or (study.judge.primary if study.judge else None),
            byot_models=[m.strip() for m in os.environ.get("PROMPTLAB_BYOT_MODELS", "").split(",") if m.strip()]
            or list(study.models),
            replay=replay,
            study_results=Path(results) if results else (replay or newest_results("study", RESULTS_DIR)),
            retention_days=int(os.environ.get("PROMPTLAB_RETENTION_DAYS", "30")),
            allow_command_checks=_flag("PROMPTLAB_ALLOW_COMMAND_CHECKS"),
            collector=_flag("PROMPTLAB_COLLECTOR"),
            collector_url=os.environ.get("PROMPTLAB_COLLECTOR_URL") or None,
            concurrency=int(os.environ.get("PROMPTLAB_CONCURRENCY", "2")),
        )
