from pydantic import BaseModel


class Settings(BaseModel):
    github_token: str = ""

    # Azure OpenAI (preferred when endpoint is set)
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_model: str = "gpt-4o"
    azure_openai_api_version: str = "2025-01-01-preview"

    # Plain OpenAI fallback
    openai_api_key: str = ""
    openai_base_url: str = ""

    default_repo: str = ""

    critic_confidence_threshold: float = 0.7
    reader_concurrency: int = 5
    blast_radius_max_depth: int = 3
    blast_radius_max_files: int = 20
    post_github_review: bool = True
