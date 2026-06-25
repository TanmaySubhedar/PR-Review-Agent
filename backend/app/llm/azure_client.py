from functools import lru_cache

from openai import AsyncAzureOpenAI
from pydantic import BaseModel

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> AsyncAzureOpenAI:
    return AsyncAzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )


async def complete_structured(
    schema: type[BaseModel], system_prompt: str, user_prompt: str, *, temperature: float = 0.2
) -> BaseModel:
    """Call Azure OpenAI and parse the response directly into `schema`,
    removing manual JSON parsing as a failure mode for every LLM call in the
    pipeline (readers, review agent, critic)."""
    client = get_client()
    response = await client.chat.completions.parse(
        model=settings.azure_openai_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=schema,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError(f"Azure OpenAI did not return a parseable {schema.__name__}")
    return parsed
