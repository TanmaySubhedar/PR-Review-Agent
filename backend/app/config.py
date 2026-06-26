from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_model: str = "gpt-4o"
    azure_openai_api_version: str = "2025-01-01-preview"

    # Non-Azure providers (leave blank if using Azure above)
    openai_api_key: str = ""
    openai_base_url: str = ""

    github_token: str = ""
    github_webhook_secret: str = ""

    database_url: str = "sqlite:///./pr_analyzer.db"

    critic_confidence_threshold: float = 0.7
    reader_concurrency: int = 5
    blast_radius_max_depth: int = 3
    blast_radius_max_files: int = 20

    def __repr__(self) -> str:
        return "Settings(***redacted***)"


settings = Settings()
