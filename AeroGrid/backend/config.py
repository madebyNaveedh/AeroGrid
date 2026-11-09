"""AeroGrid Configuration Module.

Manages application settings, LLM provider credentials, database paths, and
runtime environment parameters.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Gracefully load python-dotenv if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field

    class Settings(BaseSettings):
        """Production configuration schema using Pydantic Settings."""
        openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
        openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
        openai_base_url: Optional[str] = Field(default=None, alias="OPENAI_BASE_URL")

        gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
        gemini_model: str = Field(default="gemini-1.5-pro", alias="GEMINI_MODEL")

        aerogrid_env: str = Field(default="development", alias="AEROGRID_ENV")
        db_path: str = Field(default="backend/audit/aerogrid_audit.db", alias="AEROGRID_DB_PATH")
        parquet_dir: str = Field(default="backend/audit/exports", alias="AEROGRID_PARQUET_DIR")
        mock_llm_mode: bool = Field(default=False, alias="MOCK_LLM_MODE")
        log_level: str = Field(default="INFO", alias="AEROGRID_LOG_LEVEL")

        class Config:
            env_file = ".env"
            extra = "ignore"

    settings = Settings()

except ImportError:
    # Standard library fallback if pydantic / pydantic-settings not yet installed
    class Settings:  # type: ignore[no-redef]
        """Fallback settings reader based on os.environ."""
        def __init__(self) -> None:
            self.openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
            self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
            self.openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL")

            self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
            self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

            self.aerogrid_env: str = os.getenv("AEROGRID_ENV", "development")
            self.db_path: str = os.getenv("AEROGRID_DB_PATH", "backend/audit/aerogrid_audit.db")
            self.parquet_dir: str = os.getenv("AEROGRID_PARQUET_DIR", "backend/audit/exports")
            self.mock_llm_mode: bool = os.getenv("MOCK_LLM_MODE", "false").lower() in ("true", "1", "yes")
            self.log_level: str = os.getenv("AEROGRID_LOG_LEVEL", "INFO")

    settings = Settings()

# Ensure base audit directories exist
Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
Path(settings.parquet_dir).mkdir(parents=True, exist_ok=True)

