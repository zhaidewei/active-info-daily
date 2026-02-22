from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Field(default=Path("data"))
    db_path: Path = Field(default=Path("data/active_info.db"))
    report_dir: Path = Field(default=Path("data/reports"))
    snapshot_dir: Path = Field(default=Path("data/snapshots"))
    source_config_path: Path = Field(default=Path("config/sources.yaml"))

    analysis_provider: str = Field(default="heuristic")
    openai_api_key: Optional[str] = None
    openai_model: str = Field(default="gpt-4o-mini")
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = Field(default="deepseek-reasoner")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deepseek_strict_model: bool = Field(default=True)
    translation_enabled: bool = Field(default=True)
    translation_max_chars: int = Field(default=9000)
    llm_scoring_enabled: bool = Field(default=True)
    llm_scoring_max_items: int = Field(default=80)
    novelty_lookback_reports: int = Field(default=2)
    novelty_repeat_penalty: float = Field(default=1.2)
    novelty_max_reused_items_in_front: int = Field(default=3)

    report_max_items: int = Field(default=80)
    llm_input_items: int = Field(default=25)
    jina_reader_enabled: bool = Field(default=True)
    request_timeout_sec: int = Field(default=15)


def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
