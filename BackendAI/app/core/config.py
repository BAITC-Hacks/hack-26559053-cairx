from typing import List, Union
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "HackAlem AI API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Production-ready FastAPI backend for AI model inference and Graph analytics."
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True

    # Server config
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS configuration
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    # AI Configuration (Google Gemini / LLM)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Dataset & Storage
    DATA_DIR: str = "./Files"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @property
    def data_path(self) -> Path:
        return Path(self.DATA_DIR).resolve()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
