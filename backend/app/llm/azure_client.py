"""Provider-agnostic LLM client using litellm.

Supports Azure OpenAI (existing .env works unchanged) and any other
litellm-compatible provider via OPENAI_API_KEY / OPENAI_BASE_URL.
The complete_structured() signature is identical to the old Azure-only
client so no other file needs to change.
"""

import asyncio
import logging
import warnings

import litellm
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# litellm's background async logger emits a benign GC warning when the
# event loop resets between pipeline phases — suppress it.
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message="coroutine.*was never awaited",
    module="litellm",
)
litellm.suppress_debug_info = True

# Retry config — only for transient failures (rate limits, timeouts, 5xx).
# Auth errors and bad requests propagate immediately.
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.5  # seconds; waits: 1.5s, 3s, 6s

_TRANSIENT_ERRORS = (
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.ServiceUnavailableError,
    litellm.InternalServerError,
    litellm.BadGatewayError,
)


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
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
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
        except _TRANSIENT_ERRORS as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES:
                break
            wait = _BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                "LLM transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, _MAX_RETRIES, wait, exc,
            )
            await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]
