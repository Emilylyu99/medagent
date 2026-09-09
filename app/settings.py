from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _path_from_env(name: str, default: str) -> Path:
    configured = Path(os.getenv(name, default))
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


@dataclass(frozen=True)
class Settings:
    app_env: str
    knowledge_base_path: Path
    evaluation_cases_path: Path
    reasoner_mode: str
    openai_model: str | None
    openai_api_key: str | None
    pipeline_mode: str = "baseline"


settings = Settings(
    app_env=os.getenv("APP_ENV", "development"),
    knowledge_base_path=_path_from_env("KNOWLEDGE_BASE_PATH", "data/guidelines.json"),
    evaluation_cases_path=_path_from_env(
        "EVALUATION_CASES_PATH", "data/evaluation_cases.json"
    ),
    reasoner_mode=os.getenv("REASONER_MODE", "extractive"),
    openai_model=os.getenv("OPENAI_MODEL") or None,
    openai_api_key=os.getenv("OPENAI_API_KEY") or None,
    pipeline_mode=os.getenv("PIPELINE_MODE", "baseline").strip().lower(),
)
