"""Configuration loader. Reads ~/.pr-agent/config.toml and applies environment variable overrides."""

import os
import tomllib
from pathlib import Path

from pr_review_agent.models.config import Settings

_CONFIG_DIR = Path.home() / ".pr-agent"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"

_ENV_MAP = {
    "PR_AGENT_GITHUB_TOKEN": "github_token",
    "PR_AGENT_AZURE_OPENAI_API_KEY": "azure_openai_api_key",
    "PR_AGENT_AZURE_OPENAI_ENDPOINT": "azure_openai_endpoint",
    "PR_AGENT_AZURE_OPENAI_MODEL": "azure_openai_model",
    "PR_AGENT_AZURE_OPENAI_API_VERSION": "azure_openai_api_version",
    "PR_AGENT_OPENAI_API_KEY": "openai_api_key",
    "PR_AGENT_OPENAI_BASE_URL": "openai_base_url",
    "PR_AGENT_CRITIC_CONFIDENCE_THRESHOLD": "critic_confidence_threshold",
    "PR_AGENT_READER_CONCURRENCY": "reader_concurrency",
    "PR_AGENT_BLAST_RADIUS_MAX_DEPTH": "blast_radius_max_depth",
    "PR_AGENT_BLAST_RADIUS_MAX_FILES": "blast_radius_max_files",
    "PR_AGENT_POST_GITHUB_REVIEW": "post_github_review",
    "PR_AGENT_DEFAULT_REPO": "default_repo",
}


def load_settings() -> Settings:
    config_data: dict = {}

    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE, "rb") as f:
            config_data = tomllib.load(f)

    for env_var, field in _ENV_MAP.items():
        val = os.environ.get(env_var)
        if val is not None:
            config_data[field] = val

    return Settings(**config_data)


def save_settings(new_values: dict) -> None:
    """Merge new_values into the existing config file and write it back."""
    import tomli_w

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE, "rb") as f:
            existing = tomllib.load(f)

    existing.update({k: v for k, v in new_values.items() if v})

    with open(_CONFIG_FILE, "wb") as f:
        tomli_w.dump(existing, f)


settings = load_settings()
