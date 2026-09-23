import json
from datetime import date
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    PROJECT_NAME: str = "Career Quest"
    VERSION: str = "2.0.0"
    DESCRIPTION: str = "Employee development recommendations with deterministic scoring."
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Server config
    HOST: str = "0.0.0.0"
    PORT: int = Field(default=8000, ge=1, le=65535)

    # CORS configuration
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["*"]

    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENAI_MODEL: str = "gpt-4o-mini"
    NVIDIA_API_KEY: SecretStr = SecretStr("")
    NVIDIA_MODEL: str = "meta/llama-3.1-70b-instruct"
    LLM_TIMEOUT_SECONDS: float = Field(default=4.0, gt=0, le=30)
    MAX_UPLOAD_BYTES: int = Field(default=10 * 1024 * 1024, gt=0)

    # Dataset & Storage
    DATA_DIR: str = "dataset"
    SNAPSHOT_DATE: date = date(2026, 10, 1)

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_mode(cls, value):
        if isinstance(value, str) and value.lower() in ("release", "production"):
            return False
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return json.loads(value) if value.startswith("[") else [
                part.strip() for part in value.split(",") if part.strip()
            ]
        return value

    @property
    def data_path(self) -> Path:
        path = Path(self.DATA_DIR)
        return path if path.is_absolute() else BACKEND_DIR / path

    model_config = SettingsConfigDict(
        # Secrets come only from the process environment, never from a file.
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
