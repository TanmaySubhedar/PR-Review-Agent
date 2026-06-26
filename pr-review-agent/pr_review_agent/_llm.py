"""LLM wrapper using litellm for provider-agnostic structured completions."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from typing import Callable

import litellm
from pydantic import BaseModel

from pr_review_agent.config import settings

# litellm's GracefulThreadedWorker.__del__ GC-s queued async logging coroutines
# when the event loop closes between pipeline phases.  The warning is harmless —
# pipeline output is unaffected — but it pollutes the CLI output.
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message="coroutine.*was never awaited",
    module="litellm",
)
# Reduce the volume of async background logging that triggers the above.
litellm.suppress_debug_info = True


@dataclass
class AgentStep:
    """One tool call made during an agent loop iteration."""
    tool: str
    args: dict
    result: str


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
    schema: type[BaseModel],
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
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
        raise ValueError(f"LLM did not return a parseable {schema.__name__}")
    return schema.model_validate_json(content)


async def run_agent_loop(
    tools: list[dict],
    tool_handlers: dict[str, Callable],
    system_prompt: str,
    initial_user_message: str,
    max_steps: int = 10,
) -> tuple[str | None, list[AgentStep]]:
    """Drive a tool-using agent loop until the model stops calling tools.

    Returns (final_text, trace). final_text is None if max_steps is exhausted
    before the model emits a stop finish_reason.
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_message},
    ]
    trace: list[AgentStep] = []

    for _ in range(max_steps):
        response = await litellm.acompletion(
            model=_model_name(),
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            **_call_kwargs(),
        )
        choice = response.choices[0]
        tool_calls = choice.message.tool_calls or []

        asst_msg: dict = {"role": "assistant", "content": choice.message.content or ""}
        if tool_calls:
            asst_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        messages.append(asst_msg)

        if choice.finish_reason == "stop" or not tool_calls:
            return choice.message.content, trace

        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except (ValueError, TypeError):
                args = {}
            handler = tool_handlers.get(fn_name)
            result = await handler(args) if handler else f"unknown tool: {fn_name}"
            trace.append(AgentStep(tool=fn_name, args=args, result=str(result)))
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

    return None, trace
