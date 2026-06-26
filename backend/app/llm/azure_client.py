"""Provider-agnostic LLM client using litellm.

Supports Azure OpenAI (existing .env works unchanged) and any other
litellm-compatible provider via OPENAI_API_KEY / OPENAI_BASE_URL.
The complete_structured() signature is identical to the old Azure-only
client so no other file needs to change.
"""

import warnings

import litellm
from pydantic import BaseModel

from app.config import settings

# litellm's background async logger emits a benign GC warning when the
# event loop resets between pipeline phases — suppress it.
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message="coroutine.*was never awaited",
    module="litellm",
)
litellm.suppress_debug_info = True


def _model_name() -> str:
    if settings.azure_openai_endpoint and settings.azure_openai_api_key:
        return f"azure/{settings.azure_openai_model}"
    return settings.azure_openai_model


def _call_kwargs() -> dict:
    kwargs: dict = {}
    if settings.azure_openai_endpoint and settings.azure_openai_api_key:
        kwargs["api_key"] = settings.azure_openai_api_key
        kwargs["api_base"] = settings.azure_openai_endpoint
        kwargs["api_version"] = settings.azure_openai_api_version
    elif settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    if settings.openai_base_url:
        kwargs["api_base"] = settings.openai_base_url
    return kwargs


async def complete_structured(
    schema: type[BaseModel], system_prompt: str, user_prompt: str, *, temperature: float = 0.2
) -> BaseModel:
    response = await litellm.acompletion(
        model=_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=schema,
        temperature=temperature,
        **_call_kwargs(),
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError(f"LLM returned empty response for {schema.__name__}")
    return schema.model_validate_json(content)
