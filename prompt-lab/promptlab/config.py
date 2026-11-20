"""Model configuration (spec section 3), loaded from config/models.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from . import CONFIG_DIR


class ModelConfig(BaseModel):
    """One model under test (or a judge). Credentials are never stored here."""

    id: str                                    # short id used in results, e.g. "opus-5"
    display: str
    gateway_id: str                            # the exact identifier the endpoint expects
    confirmed: bool = False                    # has the course owner confirmed gateway_id?
    family: str
    generation: int                            # rank within the family, oldest = 1
    api: Literal["openai_compat", "anthropic", "mock"]
    base_url_env: str | None = None            # env var holding the endpoint URL
    api_key_env: str | None = None             # env var holding the key; never the key itself
    max_tokens: int = 16000
    max_tokens_param: str = "max_tokens"       # some OpenAI-style models want max_completion_tokens
    context_window: int | None = None
    reports_reasoning: bool | None = None
    effort: str | None = None                  # Anthropic effort setting, if the study fixes one
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    mock_quality: Literal["low", "high"] | None = None  # mock backend only
    notes: str = ""


class ModelsFile(BaseModel):
    models: list[ModelConfig] = Field(default_factory=list)


def load_models(path: Path | None = None) -> dict[str, ModelConfig]:
    path = path or CONFIG_DIR / "models.yaml"
    data = ModelsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    ids = [m.id for m in data.models]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate model ids in {path}: {sorted(dupes)}")
    return {m.id: m for m in data.models}
