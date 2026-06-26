"""System and user prompt templates for the file-reader LLM calls."""

SYSTEM_PROMPT = (
    "You are a code-context reader for an autonomous PR review agent. You are "
    "given one file from a repository and the reason it was pulled into the "
    "review's context (e.g. it calls the changed code, or is called by it). "
    "Summarize the file's purpose, exactly how it relates to the pull request "
    "described below, and concrete risks a reviewer should be aware of given "
    "that relationship. Be concise and specific - do not restate the file "
    "contents verbatim."
)

MAX_FILE_CHARS = 8000


def user_prompt(
    pr_summary: str,
    file_path: str,
    selection_reason: str,
    file_content: str,
    focus_question: str = "",
) -> str:
    focus_section = f"\nFocus question: {focus_question}\n" if focus_question else ""
    return (
        f"Pull request summary:\n{pr_summary}\n\n"
        f"File: {file_path}\n"
        f"Why this file was selected: {selection_reason}"
        f"{focus_section}\n\n"
        f"File contents:\n{file_content[:MAX_FILE_CHARS]}"
    )
