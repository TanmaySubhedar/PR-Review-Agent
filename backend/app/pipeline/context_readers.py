import asyncio
from pathlib import Path

from app.config import settings
from app.llm.azure_client import complete_structured
from app.schemas.context_package import ContextFileSelection, ReaderOutput

_MAX_FILE_CHARS = 8000

_SYSTEM_PROMPT = (
    "You are a code-context reader for an autonomous PR review agent. You are "
    "given one file from a repository and the reason it was pulled into the "
    "review's context (e.g. it calls the changed code, or is called by it). "
    "Summarize the file's purpose, exactly how it relates to the pull request "
    "described below, and concrete risks a reviewer should be aware of given "
    "that relationship. Be concise and specific - do not restate the file "
    "contents verbatim."
)


async def _read_one(root: Path, selection: ContextFileSelection, pr_summary: str) -> ReaderOutput:
    try:
        content = (root / selection.file).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""

    user_prompt = (
        f"Pull request summary:\n{pr_summary}\n\n"
        f"File: {selection.file}\n"
        f"Why this file was selected: {selection.selection_reason}\n\n"
        f"File contents:\n{content[:_MAX_FILE_CHARS]}"
    )
    result = await complete_structured(ReaderOutput, _SYSTEM_PROMPT, user_prompt)
    result.file = selection.file
    return result


async def read_all_contexts(
    root: Path, selections: list[ContextFileSelection], pr_summary: str
) -> list[ReaderOutput]:
    semaphore = asyncio.Semaphore(settings.reader_concurrency)

    async def bounded(selection: ContextFileSelection) -> ReaderOutput:
        async with semaphore:
            return await _read_one(root, selection, pr_summary)

    return list(await asyncio.gather(*[bounded(s) for s in selections]))
