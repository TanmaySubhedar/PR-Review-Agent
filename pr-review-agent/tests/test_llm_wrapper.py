"""Unit tests for the LLM wrapper (pr_review_agent._llm)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

import pr_review_agent._llm as llm_module
from pr_review_agent._llm import complete_structured


# ---------------------------------------------------------------------------
# Schema fixtures
# ---------------------------------------------------------------------------

class _SimpleSchema(BaseModel):
    answer: str
    score: float = 0.0


class _EmptySchema(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_acompletion_mock(content: str | None) -> AsyncMock:
    """Return a mock litellm.acompletion whose response carries JSON content."""
    mock_message = MagicMock()
    mock_message.content = content

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    return AsyncMock(return_value=mock_response)


# ---------------------------------------------------------------------------
# complete_structured — happy path
# ---------------------------------------------------------------------------

async def test_complete_structured_returns_schema_instance():
    mock_fn = _make_acompletion_mock('{"answer": "yes", "score": 0.9}')

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        result = await complete_structured(
            _SimpleSchema,
            system_prompt="You are helpful.",
            user_prompt="Is the sky blue?",
        )

    assert isinstance(result, _SimpleSchema)
    assert result.answer == "yes"
    assert result.score == 0.9


async def test_complete_structured_calls_acompletion_with_response_format():
    mock_fn = _make_acompletion_mock('{"answer": "no"}')

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        await complete_structured(
            _SimpleSchema,
            system_prompt="System prompt.",
            user_prompt="User prompt.",
        )

    mock_fn.assert_called_once()
    call_kwargs = mock_fn.call_args
    assert call_kwargs.kwargs.get("response_format") == _SimpleSchema


async def test_complete_structured_passes_system_and_user_messages():
    mock_fn = _make_acompletion_mock('{"answer": "ok"}')
    system_text = "You are a strict reviewer."
    user_text = "Check this diff."

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        await complete_structured(
            _SimpleSchema,
            system_prompt=system_text,
            user_prompt=user_text,
        )

    call_kwargs = mock_fn.call_args
    messages = call_kwargs.kwargs.get("messages", [])
    roles = {m["role"]: m["content"] for m in messages}
    assert roles.get("system") == system_text
    assert roles.get("user") == user_text


async def test_complete_structured_uses_schema_class():
    mock_fn = _make_acompletion_mock("{}")

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        result = await complete_structured(
            _EmptySchema,
            system_prompt="s",
            user_prompt="u",
        )

    assert isinstance(result, _EmptySchema)


# ---------------------------------------------------------------------------
# complete_structured — None / empty content raises ValueError
# ---------------------------------------------------------------------------

async def test_complete_structured_raises_value_error_when_content_is_none():
    mock_fn = _make_acompletion_mock(None)

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        with pytest.raises(ValueError):
            await complete_structured(
                _SimpleSchema,
                system_prompt="s",
                user_prompt="u",
            )


async def test_complete_structured_value_error_mentions_schema_name():
    mock_fn = _make_acompletion_mock(None)

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        with pytest.raises(ValueError, match="_SimpleSchema"):
            await complete_structured(
                _SimpleSchema,
                system_prompt="s",
                user_prompt="u",
            )


async def test_complete_structured_raises_value_error_when_content_is_empty():
    mock_fn = _make_acompletion_mock("")

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        with pytest.raises(ValueError):
            await complete_structured(
                _SimpleSchema,
                system_prompt="s",
                user_prompt="u",
            )


# ---------------------------------------------------------------------------
# complete_structured — temperature forwarding
# ---------------------------------------------------------------------------

async def test_complete_structured_passes_default_temperature():
    mock_fn = _make_acompletion_mock('{"answer": "t"}')

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        await complete_structured(
            _SimpleSchema,
            system_prompt="s",
            user_prompt="u",
        )

    call_kwargs = mock_fn.call_args
    assert call_kwargs.kwargs.get("temperature") == 0.2


async def test_complete_structured_passes_custom_temperature():
    mock_fn = _make_acompletion_mock('{"answer": "t"}')

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        await complete_structured(
            _SimpleSchema,
            system_prompt="s",
            user_prompt="u",
            temperature=0.0,
        )

    call_kwargs = mock_fn.call_args
    assert call_kwargs.kwargs.get("temperature") == 0.0


# ---------------------------------------------------------------------------
# complete_structured — litellm.acompletion is called
# ---------------------------------------------------------------------------

async def test_complete_structured_calls_litellm_acompletion():
    mock_fn = _make_acompletion_mock('{"answer": "x"}')

    with patch.object(llm_module.litellm, "acompletion", mock_fn):
        await complete_structured(
            _SimpleSchema,
            system_prompt="s",
            user_prompt="u",
        )

    mock_fn.assert_called_once()


# ---------------------------------------------------------------------------
# _model_name — provider routing
# ---------------------------------------------------------------------------

async def test_model_name_azure_prefix(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "azure_openai_endpoint", "https://my.openai.azure.com")
    monkeypatch.setattr(llm_module.settings, "azure_openai_api_key", "key123")
    monkeypatch.setattr(llm_module.settings, "azure_openai_model", "gpt-4o")
    assert llm_module._model_name() == "azure/gpt-4o"


async def test_model_name_plain_openai(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "azure_openai_endpoint", "")
    monkeypatch.setattr(llm_module.settings, "azure_openai_api_key", "")
    monkeypatch.setattr(llm_module.settings, "azure_openai_model", "gpt-4o")
    assert llm_module._model_name() == "gpt-4o"
