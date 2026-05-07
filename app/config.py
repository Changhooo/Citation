from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_path: str = "data/citationclaw.sqlite3"
    data_dir: str = "data"
    default_scholar_mirror: str = "https://sc.panda985.com/"
    page_wait_min_seconds: int = 5
    page_wait_max_seconds: int = 12
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    @property
    def db_path(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else ROOT / path

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        return path if path.is_absolute() else ROOT / path


@lru_cache
def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    settings = Settings(
        database_path=os.getenv("DATABASE_PATH", "data/citationclaw.sqlite3"),
        data_dir=os.getenv("DATA_DIR", "data"),
        default_scholar_mirror=os.getenv("DEFAULT_SCHOLAR_MIRROR", "https://sc.panda985.com/"),
        page_wait_min_seconds=int(os.getenv("PAGE_WAIT_MIN_SECONDS", "5")),
        page_wait_max_seconds=int(os.getenv("PAGE_WAIT_MAX_SECONDS", "12")),
        llm_provider=os.getenv("LLM_PROVIDER", "deepseek"),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    )
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
