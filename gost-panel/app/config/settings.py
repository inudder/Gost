from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GOST_PANEL_",
        env_file=BASE_DIR / ".env",
        extra="ignore",
    )

    app_name: str = "GOST Panel"
    debug: bool = False
    bind_host: str = "127.0.0.1"
    bind_port: int = 17777
    secret_key: str = Field(default="local-dev-key-change-me", min_length=8)
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{(BASE_DIR / 'data' / 'gost_panel.db').as_posix()}"
    )
    template_auto_reload: bool = True


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()
