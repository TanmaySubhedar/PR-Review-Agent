"""System and user prompt templates for the file-dispatch decision."""

from pr_review_agent.models.domain import BlastRadius, ContextFileSelection, Symbol

SYSTEM_PROMPT = (
    "You are a read-budget manager for a PR review system. You are given a ranked "
    "list of context files relevant to a pull request and the blast radius of the "
    "changed symbols. Decide which files are worth reading deeply and assign each "
    "selected file a specific focus question.\n\n"
    "Selection criteria:\n"
    "- Always include directly changed files.\n"
    "- Prioritise files with caller or callee blast-radius entries — they are "
    "  the most likely places where the PR's changes will have side-effects.\n"
    "- Prefer test files that cover changed symbols — they reveal coverage gaps.\n"
    "- Skip generated files, lock files, pure-config files (*.toml, *.json with "
    "  no logic), vendored code, and files whose relevance is only cosmetic.\n"
    "- If the list exceeds the max_files budget, cut the lowest-scored, least "
    "  blast-radius-adjacent files first.\n\n"
    "Focus question guidance:\n"
    "- Make the question concrete and answerable from the file alone.\n"
    "- Bad: 'Summarize this file.' Good: 'Does this file guard against null "
    "  token values before calling authenticate()?'\n"
    "- Tie the question to the specific changed symbols where possible."
)


def user_prompt(
    context_files: list[ContextFileSelection],
    blast_radius: BlastRadius,
    changed_symbols: list[Symbol],
    max_files: int = 8,
) -> str:
    callers_by_file: dict[str, list[str]] = {}
    for entry in blast_radius.entries:
        for caller in entry.callers:
            if caller.file:
                callers_by_file.setdefault(caller.file, []).append(entry.symbol)

    file_lines = []
    for sel in context_files:
        notes = []
        if sel.file in callers_by_file:
            syms = callers_by_file[sel.file][:3]
            notes.append(f"calls: {', '.join(syms)}")
        if notes:
            note_str = " [" + "; ".join(notes) + "]"
        else:
            note_str = ""
        file_lines.append(
            f"  - {sel.file}  reason={sel.selection_reason}  score={sel.score:.0f}{note_str}"
        )

    sym_lines = [
        f"  - {s.name} ({s.symbol_type}) in {s.file}" for s in changed_symbols
    ]

    return (
        "Changed symbols:\n" + "\n".join(sym_lines) + "\n\n"
        f"Context files (select up to {max_files}):\n" + "\n".join(file_lines) + "\n\n"
        "Return: files_to_read (list of selected file paths), "
        "focus_questions (list of {file, question} objects — one per selected file), "
        "skipped_files (list of paths you are intentionally excluding), "
        "and reasoning (one sentence)."
    )
