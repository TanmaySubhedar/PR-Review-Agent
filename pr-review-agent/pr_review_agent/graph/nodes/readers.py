"""Readers node: intelligent dispatch then parallel LLM summarisation of context files."""

import asyncio
from pathlib import Path

from pr_review_agent._llm import complete_structured
from pr_review_agent.config import settings
from pr_review_agent.graph.state import PRReviewState
from pr_review_agent.models.domain import (
    BlastRadius,
    ContextFileSelection,
    FileDispatchDecision,
    FileFocusQuestion,
    FileSummary,
    Symbol,
)
from pr_review_agent.prompts import dispatch as dispatch_prompts
from pr_review_agent.prompts import file_reader as reader_prompts

_MAX_FILE_CHARS = reader_prompts.MAX_FILE_CHARS
_MAX_DISPATCH_FILES = 8


async def _dispatch_files(
    context_files: list[ContextFileSelection],
    blast_radius: BlastRadius,
    changed_symbols: list[Symbol],
) -> FileDispatchDecision:
    """Ask the LLM to select a focused subset of context files and assign focus questions."""
    user = dispatch_prompts.user_prompt(context_files, blast_radius, changed_symbols, _MAX_DISPATCH_FILES)
    decision: FileDispatchDecision = await complete_structured(
        FileDispatchDecision, dispatch_prompts.SYSTEM_PROMPT, user
    )
    # Always include directly changed files even if the dispatch LLM skips them.
    existing_paths = set(decision.files_to_read)
    changed_paths = {sel.file for sel in context_files if sel.selection_reason == "changed_file"}
    for path in changed_paths - existing_paths:
        decision.files_to_read.append(path)
        if not any(fq.file == path for fq in decision.focus_questions):
            decision.focus_questions.append(FileFocusQuestion(
                file=path,
                question="Summarize how this changed file relates to the PR.",
            ))
    return decision


async def _read_one(
    root: Path,
    selection: ContextFileSelection,
    pr_summary: str,
    focus_question: str,
) -> FileSummary:
    try:
        content = (root / selection.file).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""
    user = reader_prompts.user_prompt(
        pr_summary, selection.file, selection.selection_reason, content, focus_question
    )
    result: FileSummary = await complete_structured(FileSummary, reader_prompts.SYSTEM_PROMPT, user)
    return result.model_copy(update={"file": selection.file})


async def _read_all(
    root: Path,
    selections: list[ContextFileSelection],
    pr_summary: str,
    focus_by_file: dict[str, str],
) -> tuple[list[FileSummary], dict[str, str]]:
    semaphore = asyncio.Semaphore(settings.reader_concurrency)

    file_contents: dict[str, str] = {}
    for sel in selections:
        try:
            file_contents[sel.file] = (root / sel.file).read_text(
                encoding="utf-8", errors="ignore"
            )[:_MAX_FILE_CHARS]
        except OSError:
            file_contents[sel.file] = ""

    async def bounded(sel: ContextFileSelection) -> FileSummary:
        async with semaphore:
            focus = focus_by_file.get(
                sel.file, "Summarize this file's purpose and relationship to the PR."
            )
            return await _read_one(root, sel, pr_summary, focus)

    summaries = list(await asyncio.gather(*[bounded(s) for s in selections]))
    return summaries, file_contents


async def _run(
    root: Path,
    context_files: list[ContextFileSelection],
    blast_radius: BlastRadius,
    changed_symbols: list[Symbol],
    pr_summary: str,
) -> tuple[list[FileSummary], dict[str, str], FileDispatchDecision]:
    dispatch_decision = await _dispatch_files(context_files, blast_radius, changed_symbols)
    selected_paths = set(dispatch_decision.files_to_read)
    selected_files = [sel for sel in context_files if sel.file in selected_paths]
    focus_by_file = {fq.file: fq.question for fq in dispatch_decision.focus_questions}
    file_summaries, file_contents = await _read_all(
        root, selected_files, pr_summary, focus_by_file
    )
    return file_summaries, file_contents, dispatch_decision


def run(state: PRReviewState) -> PRReviewState:
    pr_meta = state["pr_metadata"]
    pr_summary = f"{pr_meta.title}\n{pr_meta.description}".strip()
    context_files = state.get("context_files", [])
    blast_radius: BlastRadius = state.get("blast_radius") or BlastRadius()
    changed_symbols: list[Symbol] = state.get("changed_symbols", [])

    file_summaries, file_contents, dispatch_decision = asyncio.run(
        _run(state["repo_path"], context_files, blast_radius, changed_symbols, pr_summary)
    )

    return {
        **state,
        "file_summaries": file_summaries,
        "context_file_contents": file_contents,
        "dispatch_decision": dispatch_decision,
        "phase_status": {**state.get("phase_status", {}), "readers": "done"},
    }
