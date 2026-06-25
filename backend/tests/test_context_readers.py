from pathlib import Path

import pytest

from app.pipeline import context_readers
from app.schemas.context_package import ContextFileSelection, ReaderOutput

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


async def test_read_all_contexts_uses_mocked_llm_and_preserves_file_path(monkeypatch):
    calls = []

    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        calls.append(user_prompt)
        return ReaderOutput(file="placeholder", purpose="p", relevance="r", risks=[])

    monkeypatch.setattr(context_readers, "complete_structured", fake_complete_structured)

    selections = [
        ContextFileSelection(file="auth/utils.py", selection_reason="changed_file", score=100.0),
        ContextFileSelection(file="auth/middleware.py", selection_reason="direct_caller", score=80.0),
    ]

    results = await context_readers.read_all_contexts(FIXTURE_REPO, selections, "PR summary text")

    assert {r.file for r in results} == {"auth/utils.py", "auth/middleware.py"}
    assert len(calls) == 2
    assert "PR summary text" in calls[0]


async def test_read_all_contexts_handles_missing_file_gracefully(monkeypatch):
    async def fake_complete_structured(schema, system_prompt, user_prompt, **kwargs):
        assert "File contents:\n" in user_prompt
        return ReaderOutput(file="placeholder", purpose="p", relevance="r", risks=[])

    monkeypatch.setattr(context_readers, "complete_structured", fake_complete_structured)

    selections = [ContextFileSelection(file="does/not/exist.py", selection_reason="dependency_chain", score=40.0)]
    results = await context_readers.read_all_contexts(FIXTURE_REPO, selections, "summary")

    assert results[0].file == "does/not/exist.py"
