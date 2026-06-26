from app.llm.azure_client import complete_structured
from app.llm.prompts import load_prompt
from app.pipeline.critic_agent import HEDGE_WORDS
from app.pipeline.diff_analysis import FileDiff
from app.schemas.diff_analysis import DiffAnalysis
from app.schemas.pr_event import PREvent
from app.schemas.repository_context import RepositoryContext
from app.schemas.review_finding import ReviewFinding, ReviewFindingsResponse

_MAX_PATCH_CHARS = 6000
_HEDGE_WORDS_LIST = ", ".join(f"'{w}'" for w in HEDGE_WORDS)

_SYSTEM_PROMPT = load_prompt("review_agent_system.md").replace("__HEDGE_WORDS__", _HEDGE_WORDS_LIST)

_RE_REVIEW_INSTRUCTIONS = (
    "\n\nThis PR was reviewed before. Previous findings are listed below. For "
    "EACH previous finding, you must explicitly decide one of: resolved (the "
    "code that caused it changed enough that it no longer applies), still "
    "present (you can point to the exact unchanged or insufficiently-changed "
    "code that still causes it), or unrelated (it's about a part of the diff "
    "that's no longer relevant). Only mark something 'still present' if you "
    "can cite the current code showing the issue remains - do not re-raise a "
    "finding just because it was raised last time without re-checking it "
    "against the current diff. Only include 'still present' and genuinely "
    "new findings in your output; do not include resolved or unrelated ones.\n\n"
    "The same evidence rules from the main prompt apply when deciding 'still present': "
    "do not re-raise a logging finding if a logger call already exists on that path; "
    "do not re-raise a correctness finding about callers if those callers are not in "
    "this diff; do not re-raise a finding whose only evidence is a hedge word like "
    "'may' or 'might' without a concrete failure trace. If a previous finding fails "
    "any of these checks, mark it resolved or unrelated — never still present."
)


def _format_diff_section(file_diffs: list[FileDiff]) -> str:
    parts = []
    for fd in file_diffs:
        parts.append(f"--- {fd.file} ({fd.status}) ---\n{fd.patch[:_MAX_PATCH_CHARS]}")
    return "\n\n".join(parts)


def _format_repository_context(repository_context: RepositoryContext) -> str:
    return (
        f"Affected components: {', '.join(repository_context.affected_components) or 'none identified'}\n"
        f"Affected services/modules: {', '.join(repository_context.affected_services) or 'none identified'}\n"
        f"Affected tests: {', '.join(repository_context.affected_tests) or 'none identified'}\n"
        f"Architecture constraints: {', '.join(repository_context.architecture_constraints) or 'none configured'}\n"
        f"Known risk areas:\n- " + "\n- ".join(repository_context.risk_areas or ["none identified"])
    )


def _format_previous_findings(previous_findings: list[ReviewFinding]) -> str:
    lines = []
    for f in previous_findings:
        location = f"{f.file}" + (f":{f.line}" if f.line is not None else "")
        lines.append(f"- [{f.dimension}/{f.severity}] {location}: {f.finding}\n  evidence: {f.evidence}")
    return "\n".join(lines)


async def generate_findings(
    pr_event: PREvent,
    file_diffs: list[FileDiff],
    diff_analysis: DiffAnalysis,
    repository_context: RepositoryContext,
    previous_findings: list[ReviewFinding] | None = None,
) -> ReviewFindingsResponse:
    user_prompt = (
        f"PR title: {pr_event.title}\n"
        f"PR description: {pr_event.description or '(none)'}\n\n"
        f"Risk level: {diff_analysis.risk_level}\n"
        f"Risk factors: {', '.join(diff_analysis.risk_factors) or 'none'}\n\n"
        f"Repository context:\n{_format_repository_context(repository_context)}\n\n"
        f"Diff:\n{_format_diff_section(file_diffs)}"
    )

    system_prompt = _SYSTEM_PROMPT
    if previous_findings:
        system_prompt += _RE_REVIEW_INSTRUCTIONS
        user_prompt += f"\n\nPrevious review's findings on this PR:\n{_format_previous_findings(previous_findings)}"

    return await complete_structured(ReviewFindingsResponse, system_prompt, user_prompt)
